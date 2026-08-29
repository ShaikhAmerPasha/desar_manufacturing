"""
DESAR Production Controller — Backend API

Single page that orchestrates the entire production cycle.
Each role sees a filtered view of the same page.

Key APIs:
  get_orders()         — list active production orders
  get_order_detail()   — full detail for one PP
  start_stage()        — submit WO for a stage
  get_stage_actions()  — what buttons to show for current user/stage
"""
import frappe
from frappe import _
from frappe.utils import flt, cint

from desar_manufacturing.constants import (
    ALL_DESAR_ROLES,
    SUPERVISOR_ROLES,
    JOB_CARD_ROLES,
    QC_ROLES,
    STORE_ROLES,
)


@frappe.whitelist()
def get_orders():
    """
    Returns active production orders for the controller list view.
    Grouped by Production Plan.
    """
    frappe.only_for(ALL_DESAR_ROLES)
    role = _get_desar_role()

    wos = frappe.get_all(
        "Work Order",
        filters={
            "docstatus": ["in", [0, 1]],
            "production_plan": ["!=", ""],
        },
        fields=[
            "name", "production_item", "qty", "status", "docstatus",
            "production_plan", "sales_order",
            "custom_design_no", "custom_article_name", "custom_design_master",
            "planned_start_date",
        ],
        order_by="planned_start_date asc",
        limit=200,
    )

    groups = {}
    for wo in wos:
        pp = wo.production_plan
        if pp not in groups:
            groups[pp] = {
                "production_plan": pp,
                "sales_order": wo.sales_order or "",
                "design_no": wo.custom_design_no or "",
                "article_name": wo.custom_article_name or "",
                "design_master": wo.custom_design_master or "",
                "planned_date": str(wo.planned_start_date or ""),
                "work_orders": [],
                "total_stages": 0,
                "completed_stages": 0,
            }

        stage_name = _get_stage_name(wo)
        groups[pp]["work_orders"].append({
            "name": wo.name,
            "production_item": wo.production_item,
            "stage_name": stage_name,
            "qty": wo.qty,
            "status": wo.status,
            "docstatus": wo.docstatus,
        })
        groups[pp]["total_stages"] += 1
        if wo.status == "Completed":
            groups[pp]["completed_stages"] += 1

    result = list(groups.values())
    # Sort: in-progress first, then not started, then completed
    result.sort(key=lambda g: (
        0 if 0 < g["completed_stages"] < g["total_stages"] else
        1 if g["completed_stages"] == 0 else 2
    ))
    return result


@frappe.whitelist()
def get_order_detail(production_plan: str):
    """
    Returns full detail for one production order.
    Includes stages, job cards, stock entries, QIs.
    """
    frappe.only_for(ALL_DESAR_ROLES)
    if not production_plan:
        frappe.throw(_("Production Plan required"))

    role = _get_desar_role()

    # Get all WOs for this PP ordered by planned_start_date
    wos = frappe.get_all(
        "Work Order",
        filters={"production_plan": production_plan, "docstatus": ["in", [0, 1]]},
        fields=[
            "name", "production_item", "qty", "status", "docstatus",
            "custom_design_no", "custom_article_name", "custom_design_master",
            "sales_order", "skip_transfer",
        ],
        order_by="creation asc",
    )

    if not wos:
        return {}

    first = wos[0]
    dm = first.custom_design_master or ""

    # Get stages from Stage Configuration (ordered)
    stages_config = []
    if dm:
        stages_config = frappe.get_all(
            "DESAR Stage Configuration",
            filters={"parent": dm},
            fields=["stage_seq", "stage_name", "output_item", "qi_required", "is_final_stage", "qi_template"],
            order_by="stage_seq asc",
        )

    # Map WOs to stages
    stages = []
    for idx, sc in enumerate(stages_config):
        # Find matching WO
        wo = next((w for w in wos if w.production_item == sc.output_item), None)
        stage = _build_stage_detail(sc, wo, idx, stages_config, role)
        stages.append(stage)

    # Visible stock entries
    se_visible = _get_visible_stock_entries(production_plan, wos, role)

    return {
        "production_plan": production_plan,
        "sales_order": first.sales_order or "",
        "design_no": first.custom_design_no or "",
        "article_name": first.custom_article_name or "",
        "design_master": dm,
        "stages": stages,
        "stock_entries": se_visible,
        "role": role,
    }


@frappe.whitelist()
def start_stage(production_plan: str, work_order: str):
    """
    Supervisor clicks Start Stage.
    Submits the Work Order and auto-fills warehouses via validate hook.
    """
    frappe.only_for(SUPERVISOR_ROLES)

    wo = frappe.get_doc("Work Order", work_order)
    if wo.docstatus == 1:
        frappe.throw(_("Work Order {0} is already submitted").format(work_order))

    # Auto-fill Design Master from BOM if not set
    if not wo.get("custom_design_master") and wo.bom_no:
        bom_data = frappe.db.get_value(
            "BOM", wo.bom_no,
            ["custom_design_no", "custom_article_name", "custom_design_master"],
            as_dict=True,
        )
        if bom_data:
            wo.custom_design_no = bom_data.custom_design_no or ""
            wo.custom_article_name = bom_data.custom_article_name or ""
            wo.custom_design_master = bom_data.custom_design_master or ""

    wo.flags.ignore_permissions = True
    wo.submit()

    frappe.msgprint(
        _("Stage started — Work Order {0} submitted").format(work_order),
        alert=True
    )
    return {"status": "ok", "work_order": work_order}


@frappe.whitelist()
def get_stage_job_cards(work_order: str):
    """
    Returns job cards for a Work Order.
    For operators: only job cards assigned to current user.
    For supervisor/QC: all job cards.
    """
    frappe.only_for(ALL_DESAR_ROLES)
    if not work_order:
        return []

    role = _get_desar_role()
    filters = {"work_order": work_order, "docstatus": ["in", [0, 1]]}

    # Operators see only their assigned job cards
    if role == "operator":
        filters["custom_assigned_to"] = frappe.session.user

    return frappe.get_all(
        "Job Card",
        filters=filters,
        fields=["name", "operation", "status", "docstatus",
                "custom_assigned_to", "workstation"],
        order_by="creation asc",
    )


@frappe.whitelist()
def assign_job_card(job_card: str, assign_to: str):
    """Supervisor assigns a job card to a specific user."""
    frappe.only_for(SUPERVISOR_ROLES)
    frappe.db.set_value("Job Card", job_card, "custom_assigned_to", assign_to)
    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def get_workers():
    """Returns list of users with DESAR Operator role for assignment."""
    frappe.only_for(SUPERVISOR_ROLES)
    users = frappe.get_all(
        "Has Role",
        filters={"role": "DESAR Operator", "parenttype": "User"},
        fields=["parent as user"],
    )
    result = []
    for u in users:
        name = frappe.db.get_value("User", u.user, "full_name")
        result.append({"user": u.user, "full_name": name or u.user})
    return result


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_desar_role() -> str:
    """Returns simplified role for current user."""
    user_roles = frappe.get_roles(frappe.session.user)
    if "DESAR Supervisor" in user_roles or "System Manager" in user_roles:
        return "supervisor"
    elif "DESAR Operator" in user_roles:
        return "operator"
    elif "DESAR QC Inspector" in user_roles:
        return "qc"
    elif "DESAR Store Manager" in user_roles:
        return "store"
    return "supervisor"  # Default for Administrator


def _guard_job_card_owner(jc) -> None:
    """Block a non-supervisor from starting/completing another user's Job Card."""
    if _get_desar_role() == "supervisor":
        return
    if jc.custom_assigned_to and jc.custom_assigned_to != frappe.session.user:
        frappe.throw(_("Job Card {0} is assigned to another user").format(jc.name))


def _get_stage_name(wo: dict) -> str:
    dm = wo.get("custom_design_master") or ""
    item = wo.get("production_item") or ""
    if not dm or not item:
        return item
    return frappe.db.get_value(
        "DESAR Stage Configuration",
        {"parent": dm, "output_item": item},
        "stage_name"
    ) or item


def _build_stage_detail(sc: dict, wo, idx: int, all_stages: list, role: str) -> dict:
    """Build complete stage detail including status and available actions."""
    stage = {
        "stage_seq": sc.stage_seq,
        "stage_name": sc.stage_name,
        "output_item": sc.output_item,
        "qi_required": sc.qi_required,
        "is_final_stage": sc.is_final_stage,
        "wo_name": wo.name if wo else None,
        "wo_status": wo.status if wo else "Not Created",
        "wo_docstatus": wo.docstatus if wo else 0,
        "can_start": False,
        "can_transfer": False,
        "can_finish": False,
        "can_create_qi": False,
        "qi_exists": False,
        "qi_name": None,
        "transfer_se": None,
        "manufacture_se": None,
        "is_locked": True,
    }

    if not wo:
        return stage

    # Check if this stage is unlocked (previous stage completed)
    if idx == 0:
        stage["is_locked"] = False
    else:
        prev_item = all_stages[idx - 1].output_item
        prev_wo = frappe.db.get_value(
            "Work Order",
            {"production_plan": frappe.db.get_value("Work Order", wo.name, "production_plan"),
             "production_item": prev_item, "docstatus": 1},
            ["name", "status"],
            as_dict=True
        )
        stage["is_locked"] = not (prev_wo and prev_wo.status == "Completed")

    # Stage actions based on WO state
    if wo.docstatus == 0:
        stage["can_start"] = (role == "supervisor") and not stage["is_locked"]
        return stage

    # WO is submitted — check SE states
    manufacture_se = frappe.db.get_value(
        "Stock Entry",
        {"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 1},
        "name"
    )
    transfer_se = frappe.db.get_value(
        "Stock Entry",
        {"work_order": wo.name, "stock_entry_type": "Material Transfer for Manufacture", "docstatus": 1},
        "name"
    )

    stage["manufacture_se"] = manufacture_se
    stage["transfer_se"] = transfer_se

    open_jcs = frappe.db.count("Job Card", {"work_order": wo.name, "docstatus": ["!=", 1]})
    all_jcs_done = (open_jcs == 0)

    # Transfer button (operator/supervisor)
    if not manufacture_se and not wo.skip_transfer and all_jcs_done and role in ["supervisor", "operator"]:
        stage["can_transfer"] = True

    # Finish button (operator/supervisor)
    transfer_ready = bool(transfer_se or wo.skip_transfer)
    if all_jcs_done and not manufacture_se and transfer_ready and role in ["supervisor", "operator"]:
        stage["can_finish"] = True

    # QI button (QC Inspector only, after manufacture SE)
    if sc.qi_required and manufacture_se and role == "qc":
        qi = frappe.db.get_value(
            "Quality Inspection",
            {"reference_name": manufacture_se, "docstatus": ["!=", 2]},
            "name"
        )
        stage["qi_exists"] = bool(qi)
        stage["qi_name"] = qi
        stage["can_create_qi"] = not bool(qi)

    return stage


def _get_visible_stock_entries(production_plan: str, wos: list, role: str) -> list:
    """
    Returns only SE-1 (yarn Transfer) and SE-2 (Repack) for client.
    Supervisor/Store Manager see these 2.
    Others see nothing.
    """
    if role not in ["supervisor", "store"]:
        return []

    result = []

    # SE-1: First WO Transfer SE (raw material issue)
    if wos:
        first_wo = wos[0]
        se1 = frappe.db.get_value(
            "Stock Entry",
            {"work_order": first_wo.name,
             "stock_entry_type": "Material Transfer for Manufacture",
             "docstatus": 1},
            ["name", "posting_date", "docstatus"],
            as_dict=True
        )
        if se1:
            result.append({
                "label": "SE-1: Raw Material Issued",
                "name": se1.name,
                "date": str(se1.posting_date),
                "status": "Submitted",
                "type": "se1"
            })

    # SE-2: Repack SE (final grade split)
    last_wo = wos[-1] if wos else None
    if last_wo:
        mfg_se = frappe.db.get_value(
            "Stock Entry",
            {"work_order": last_wo.name, "stock_entry_type": "Manufacture", "docstatus": 1},
            "name"
        )
        if mfg_se:
            repack = frappe.db.get_value(
                "Stock Entry",
                {"custom_source_qi": ["!=", ""], "docstatus": ["in", [0, 1]]},
                ["name", "posting_date", "docstatus"],
                as_dict=True
            )
            if repack:
                result.append({
                    "label": "SE-2: Final Grade Split",
                    "name": repack.name,
                    "date": str(repack.posting_date),
                    "status": "Draft — needs review" if repack.docstatus == 0 else "Submitted",
                    "type": "se2",
                    "needs_action": repack.docstatus == 0
                })

    return result


@frappe.whitelist()
def get_current_role() -> str:
    """Returns simplified role for current user."""
    return _get_desar_role()


@frappe.whitelist()
def get_my_job_cards() -> list:
    """
    Returns job cards assigned to current user.
    Includes WO action states (can_transfer, can_finish).
    """
    frappe.only_for(ALL_DESAR_ROLES)
    user = frappe.session.user
    jcs = frappe.get_all(
        "Job Card",
        filters={
            "custom_assigned_to": user,
            "docstatus": ["in", [0, 1]],
        },
        fields=["name", "operation", "status", "docstatus",
                "work_order", "workstation"],
        order_by="creation asc",
        limit=20,
    )

    result = []
    for jc in jcs:
        wo = jc.work_order
        entry = dict(jc)

        # Get stage/article info from WO
        if wo:
            wo_doc = frappe.db.get_value(
                "Work Order", wo,
                ["production_item", "custom_article_name", "custom_design_master",
                 "skip_transfer", "status"],
                as_dict=True
            )
            if wo_doc:
                entry["production_item"] = wo_doc.production_item
                entry["article_name"] = wo_doc.custom_article_name or ""
                entry["stage_name"] = _get_stage_name_from_wo(wo_doc)

                # Check if operator can do Transfer/Finish after JC done
                if jc.status == "Completed" or jc.docstatus == 1:
                    mfg_se = frappe.db.get_value("Stock Entry",
                        {"work_order": wo, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
                    transfer_se = frappe.db.get_value("Stock Entry",
                        {"work_order": wo, "stock_entry_type": "Material Transfer for Manufacture", "docstatus": 1}, "name")
                    open_jcs = frappe.db.count("Job Card", {"work_order": wo, "docstatus": ["!=", 1]})

                    entry["can_transfer"] = bool(
                        not mfg_se and not wo_doc.skip_transfer and
                        open_jcs == 0 and not transfer_se
                    )
                    entry["can_finish"] = bool(
                        open_jcs == 0 and not mfg_se and
                        (transfer_se or wo_doc.skip_transfer)
                    )
                else:
                    entry["can_transfer"] = False
                    entry["can_finish"] = False

        result.append(entry)

    return result


@frappe.whitelist()
def start_job_card(job_card: str) -> dict:
    """Start a Job Card — sets status to Work In Progress."""
    frappe.only_for(JOB_CARD_ROLES)
    jc = frappe.get_doc("Job Card", job_card)
    _guard_job_card_owner(jc)
    if jc.status == "Work In Progress":
        return {"status": "already_started"}

    jc.append("time_logs", {
        "from_time": frappe.utils.now_datetime(),
        "employee": frappe.db.get_value("Employee",
            {"user_id": frappe.session.user}, "name") or ""
    })
    jc.flags.ignore_permissions = True
    jc.save()
    return {"status": "started"}


@frappe.whitelist()
def complete_job_card(job_card: str, scrap_qty=None, actual_yarn_kg=None) -> dict:
    """
    Complete and submit a Job Card.

    scrap_qty: optional — if given, appends one row to the Job Card's own
    native `scrap_items` table using this stage's default scrap item
    (resolved below). ERPNext core then automatically pulls this into the
    Work Order's Manufacture Stock Entry as a real, valued is_scrap_item row
    the moment it's created (Stock Entry.get_scrap_items_from_job_card()) —
    no extra plumbing needed here beyond populating this native table.

    actual_yarn_kg: optional, Warping stage only — records what was actually
    weighed/issued, for comparison against the Warp Recipe's planned kg
    (yarn can stretch/waste during warping; nothing upstream currently
    captures that variance).
    """
    frappe.only_for(JOB_CARD_ROLES)
    jc = frappe.get_doc("Job Card", job_card)
    _guard_job_card_owner(jc)
    if jc.docstatus == 1:
        return {"status": "already_done"}

    # Close any open time logs
    for tl in jc.time_logs:
        if not tl.to_time:
            tl.to_time = frappe.utils.now_datetime()
            tl.time_in_mins = frappe.utils.time_diff_in_seconds(
                tl.to_time, tl.from_time) / 60

    stage_lower = _get_job_card_stage_lower(jc)

    if flt(scrap_qty):
        _append_scrap_row(jc, stage_lower, flt(scrap_qty))

    if "warp" in stage_lower and actual_yarn_kg not in (None, ""):
        _set_actual_yarn_kg(jc, flt(actual_yarn_kg))

    jc.flags.ignore_permissions = True
    jc.save()
    jc.submit()
    return {"status": "completed"}


def _get_job_card_stage_lower(jc) -> str:
    if not jc.work_order:
        return ""
    wo_doc = frappe.db.get_value(
        "Work Order", jc.work_order,
        ["custom_design_master", "production_item"], as_dict=True,
    ) or {}
    return (_get_stage_name_from_wo(wo_doc) or "").lower()


def _resolve_scrap_item(jc, stage_lower: str) -> str:
    """Default scrap Item for this Job Card's stage — "" if unconfigured or
    unresolvable. Never guess an item into existence; callers treat "" as
    "no default, entry skipped" rather than erroring, since scrap is optional."""
    from desar_manufacturing.config.settings_manager import SettingsManager

    if "pack" in stage_lower:
        grade = SettingsManager.get_scrap_grade()
        if not grade:
            return ""
        scrap_item = grade.get("scrap_item")
        if scrap_item and frappe.db.exists("Item", scrap_item):
            return scrap_item
        if grade.get("item_suffix") and jc.production_item:
            from desar_manufacturing.services.repack_service import RepackService
            item_code = RepackService._derive_item_with_suffix(jc.production_item, grade["item_suffix"])
            if item_code and frappe.db.exists("Item", item_code):
                return item_code
        return ""

    item_code = SettingsManager.get_stage_scrap_item(stage_lower)
    if item_code and frappe.db.exists("Item", item_code):
        return item_code
    return ""


def _append_scrap_row(jc, stage_lower: str, qty: float) -> None:
    item_code = _resolve_scrap_item(jc, stage_lower)
    if not item_code:
        frappe.msgprint(
            _("No scrap item configured for this stage — scrap quantity was NOT recorded. "
              "Configure it in DESAR Settings, or (Packing) flag a grade as scrap."),
            indicator="orange",
        )
        return
    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
    jc.append("scrap_items", {
        "item_code": item_code,
        "stock_qty": qty,
        "stock_uom": stock_uom,
    })


def _set_actual_yarn_kg(jc, actual_kg: float) -> None:
    planned_kg = 0.0
    wo_doc = frappe.db.get_value(
        "Work Order", jc.work_order, "custom_design_master"
    ) if jc.work_order else None
    if wo_doc:
        recipe = frappe.db.get_value("Design Master", wo_doc, "warp_recipe")
        if recipe:
            planned_kg = flt(frappe.db.get_value("Warp Recipe", recipe, "total_yarn_kg"))

    jc.custom_actual_yarn_kg = actual_kg
    jc.custom_planned_yarn_kg = planned_kg
    jc.custom_yarn_loss_kg = actual_kg - planned_kg if planned_kg else 0


@frappe.whitelist()
def get_pending_inspections() -> list:
    """
    Returns list of WOs that have Manufacture SE but no QI yet.
    For QC Inspector view.
    """
    frappe.only_for(QC_ROLES)
    # Get all submitted WOs with Manufacture SE
    wos = frappe.get_all(
        "Work Order",
        filters={"docstatus": 1, "status": ["in", ["Completed", "In Process"]]},
        fields=["name", "production_item", "custom_design_master",
                "custom_article_name", "production_plan"],
        limit=100,
    )

    result = []
    for wo in wos:
        dm = wo.custom_design_master
        if not dm:
            continue

        # Check stage requires QI
        stage = frappe.db.get_value(
            "DESAR Stage Configuration",
            {"parent": dm, "output_item": wo.production_item},
            ["stage_name", "qi_required"],
            as_dict=True
        )
        if not stage or not stage.qi_required:
            continue

        # Check Manufacture SE exists
        se = frappe.db.get_value("Stock Entry",
            {"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
        if not se:
            continue

        # Check QI not already created
        qi = frappe.db.exists("Quality Inspection",
            {"reference_name": se, "docstatus": ["!=", 2]})
        if qi:
            continue

        # Get batch
        batch = frappe.db.get_value("Stock Entry Detail",
            {"parent": se, "is_finished_item": 1}, "batch_no") or ""

        result.append({
            "work_order": wo.name,
            "stage_name": stage.stage_name,
            "output_item": wo.production_item,
            "article_name": wo.custom_article_name or "",
            "batch_no": batch,
        })

    return result


@frappe.whitelist()
def get_pending_repack() -> list:
    """
    Returns draft Repack SEs for Store Manager.
    Shows grade quantities per SE.
    """
    frappe.only_for(STORE_ROLES)
    ses = frappe.get_all(
        "Stock Entry",
        filters={"stock_entry_type": "Repack", "docstatus": 0},
        fields=["name", "posting_date"],
        order_by="creation desc",
        limit=20,
    )

    result = []
    for se in ses:
        items = frappe.get_all(
            "Stock Entry Detail",
            filters={"parent": se.name, "is_finished_item": 1},
            fields=["item_code", "qty", "t_warehouse"],
        )

        grade_a = sum(i.qty for i in items if "Grade A" in (i.t_warehouse or "") or i.item_code.endswith("-A"))
        grade_b = sum(i.qty for i in items if "Grade B" in (i.t_warehouse or "") or i.item_code.endswith("-B"))
        grade_c = sum(i.qty for i in items if "Scrap" in (i.t_warehouse or "") or "Scrap" in i.item_code)

        result.append({
            "name": se.name,
            "date": str(se.posting_date),
            "grade_a": int(grade_a),
            "grade_b": int(grade_b),
            "grade_c": int(grade_c),
        })

    return result


def _get_stage_name_from_wo(wo_doc) -> str:
    """Get stage name from WO's design master and production item."""
    dm = wo_doc.get("custom_design_master") or ""
    item = wo_doc.get("production_item") or ""
    if not dm or not item:
        return item
    return frappe.db.get_value(
        "DESAR Stage Configuration",
        {"parent": dm, "output_item": item},
        "stage_name"
    ) or item
