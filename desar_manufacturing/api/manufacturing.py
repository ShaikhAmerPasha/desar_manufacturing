"""
DESAR Manufacturing — Public API v3.3

Whitelisted methods called from client JS.
Pattern: validate inputs → check permissions → delegate to services → return result.
Zero business logic here.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint

from desar_manufacturing.constants import QITemplates, GREY_ROLL, FINISHED_ROLL
from desar_manufacturing.repositories.work_order_repository import WorkOrderRepository
from desar_manufacturing.repositories.stock_entry_repository import StockEntryRepository
from desar_manufacturing.utils.grade_utils import get_final_stage_names

# Any authenticated DESAR desk role may read configuration/summary data;
# only MUTATE_ROLES (production_order.py) may create or change records.
READ_ROLES = ["System Manager", "DESAR Supervisor", "DESAR Operator", "DESAR QC Inspector", "DESAR Store Manager"]


@frappe.whitelist()
def create_quality_inspection(work_order: str, stage: str) -> str:
    if not work_order:
        frappe.throw(_("Work Order is required"))
    valid_stages = {"grey", "finishing", "final"}
    if stage not in valid_stages:
        frappe.throw(_("Invalid stage '{0}'. Valid values: {1}").format(stage, ", ".join(sorted(valid_stages))))
    frappe.has_permission("Quality Inspection", "create", throw=True)
    wo_docstatus = frappe.db.get_value("Work Order", work_order, "docstatus")
    if wo_docstatus is None:
        frappe.throw(_("Work Order <b>{0}</b> not found").format(work_order))
    if cint(wo_docstatus) != 1:
        frappe.throw(_("Work Order must be submitted before creating a Quality Inspection"))
    se_name = WorkOrderRepository.get_manufacture_se(work_order)
    if not se_name:
        frappe.throw(_("No submitted Manufacture entry found for <b>{0}</b>.<br>Please finish the Work Order first.").format(work_order))
    wo_context = WorkOrderRepository.get_design_context(work_order)
    config = _get_stage_config(stage, wo_context)
    if not config.get("item_code"):
        frappe.throw(_("Cannot determine item code for stage '{0}'.").format(stage))
    batch_no = StockEntryRepository.get_finished_item_batch(se_name, config["item_code"]) or ""
    roll_ticket = _find_roll_ticket_for_qi_creation(se_name, batch_no, stage)
    qi = frappe.get_doc({
        "doctype": "Quality Inspection",
        "inspection_type": "In Process",
        "reference_type": "Stock Entry",
        "reference_name": se_name,
        "item_code": config["item_code"],
        "batch_no": batch_no,
        "sample_size": config["sample_size"],
        "quality_inspection_template": config["template"],
        "inspected_by": frappe.session.user,
        "status": "Accepted",
        "custom_roll_ticket": roll_ticket or "",
    })
    _load_readings_from_template(qi, config["template"])
    qi.insert(ignore_permissions=True)
    frappe.msgprint(_("Quality Inspection <b>{0}</b> created — {1} stage").format(qi.name, stage), alert=True)
    return qi.name


def _get_stage_config(stage: str, wo_context: dict) -> dict:
    production_item = wo_context.get("production_item") or ""
    wo_qty = cint(wo_context.get("qty") or 1)
    return {
        "grey":     {"item_code": GREY_ROLL,       "template": QITemplates.GREY,     "sample_size": 1},
        "finishing":{"item_code": FINISHED_ROLL,    "template": QITemplates.FINISHING,"sample_size": 1},
        "final":    {"item_code": production_item,  "template": QITemplates.FINAL,    "sample_size": wo_qty},
    }[stage]


def _load_readings_from_template(qi, template_name: str):
    if not template_name:
        return
    if not frappe.db.exists("Quality Inspection Template", template_name):
        frappe.log_error(title=f"DESAR: QI Template not found — {template_name}", message=f"Template '{template_name}' does not exist.")
        return
    template = frappe.get_doc("Quality Inspection Template", template_name)
    for param in template.get("item_quality_inspection_parameter") or []:
        qi.append("readings", {
            "specification": param.specification,
            "numeric": param.get("numeric") or 0,
            "min_value": param.get("min_value") or 0,
            "max_value": param.get("max_value") or 0,
            "formula_based_criteria": param.get("formula_based_criteria") or 0,
            "acceptance_formula": param.get("acceptance_formula") or "",
            "reading_1": "",
            "status": "Accepted",
        })


@frappe.whitelist()
def create_boms_from_design(design_master: str) -> dict:
    if not design_master:
        frappe.throw(_("Design Master is required"))
    frappe.has_permission("BOM", "create", throw=True)
    from desar_manufacturing.services.bom_service import BOMService
    return BOMService.create_all_boms(design_master)


@frappe.whitelist(methods=["GET"])
def get_grade_summary(design_no: str = None, article: str = None) -> dict:
    frappe.only_for(READ_ROLES)
    filters = {"roll_status": "Completed"}
    if design_no: filters["design_no"] = design_no
    if article: filters["article_name"] = article
    tickets = frappe.get_all("Roll Ticket", filters=filters, pluck="name")
    final_stages = get_final_stage_names()
    grades = _sum_final_grades(tickets, final_stages) if tickets and final_stages else {"A": 0, "B": 0, "C": 0}
    total_a, total_b, total_c = grades["A"], grades["B"], grades["C"]
    grand = total_a + total_b + total_c
    return {
        "total_rolls": len(tickets), "grade_a": total_a, "grade_b": total_b, "grade_c": total_c, "grand_total": grand,
        "pct_a": round(total_a / grand * 100, 1) if grand else 0,
        "pct_b": round(total_b / grand * 100, 1) if grand else 0,
        "pct_c": round(total_c / grand * 100, 1) if grand else 0,
    }


def _sum_final_grades(ticket_names: list, final_stages: list) -> dict:
    rows = frappe.get_all(
        "DESAR Roll Ticket Stage Grade",
        filters={"parent": ["in", ticket_names], "stage_name": ["in", final_stages]},
        fields=["grade_code", "qty"],
    )
    totals = {"A": 0, "B": 0, "C": 0}
    for r in rows:
        if r.grade_code in totals:
            totals[r.grade_code] += flt(r.qty)
    return totals


def _find_roll_ticket_for_qi_creation(se_name: str, batch_no: str, stage: str) -> str:
    from desar_manufacturing.repositories.roll_ticket_repository import RollTicketRepository
    try:
        if stage == "grey":
            if batch_no:
                return RollTicketRepository.find_by_batch(batch_no) or ""
        elif stage == "finishing":
            grey_batch = _get_consumed_batch(se_name, GREY_ROLL)
            if grey_batch:
                return RollTicketRepository.find_by_batch(grey_batch) or ""
        elif stage == "final":
            finished_batch = _get_consumed_batch(se_name, FINISHED_ROLL)
            if not finished_batch:
                return ""
            producing_se = frappe.db.sql("""
                SELECT sle.voucher_no FROM `tabStock Ledger Entry` sle
                JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
                WHERE sbe.batch_no = %s AND sle.actual_qty > 0 AND sle.is_cancelled = 0 LIMIT 1
            """, (finished_batch,), as_dict=True)
            if not producing_se:
                se = frappe.db.get_value("Stock Ledger Entry",
                    {"item_code": FINISHED_ROLL, "batch_no": finished_batch, "actual_qty": [">", 0], "is_cancelled": 0}, "voucher_no")
                if se: producing_se = [{"voucher_no": se}]
            if producing_se:
                grey_batch = _get_consumed_batch(producing_se[0]["voucher_no"], GREY_ROLL)
                if grey_batch:
                    return RollTicketRepository.find_by_batch(grey_batch) or ""
    except Exception:
        frappe.log_error(title="DESAR: Roll Ticket lookup failed at QI creation", message=frappe.get_traceback())
    return ""


def _get_consumed_batch(se_name: str, item_code: str) -> str:
    result = frappe.db.get_value("Stock Ledger Entry",
        filters={"voucher_no": se_name, "item_code": item_code, "actual_qty": ["<", 0], "is_cancelled": 0},
        fieldname="batch_no")
    if result: return result
    bundle = frappe.db.get_value("Stock Ledger Entry",
        filters={"voucher_no": se_name, "item_code": item_code, "actual_qty": ["<", 0], "is_cancelled": 0},
        fieldname="serial_and_batch_bundle")
    if bundle:
        return frappe.db.get_value("Serial and Batch Entry", {"parent": bundle}, "batch_no") or ""
    return ""


@frappe.whitelist()
def create_quality_inspection_dynamic(work_order: str, stage_name: str) -> str:
    if not work_order or not stage_name:
        frappe.throw(_("Work Order and Stage Name are required"))
    frappe.has_permission("Quality Inspection", "create", throw=True)
    wo_docstatus = frappe.db.get_value("Work Order", work_order, "docstatus")
    if cint(wo_docstatus) != 1:
        frappe.throw(_("Work Order must be submitted"))
    se_name = WorkOrderRepository.get_manufacture_se(work_order)
    if not se_name:
        frappe.throw(_("No Manufacture entry found for {0}. Finish the Work Order first.").format(work_order))
    design_master = frappe.db.get_value("Work Order", work_order, "custom_design_master")
    stage_config = None
    if design_master:
        stage_config = frappe.db.get_value("DESAR Stage Configuration",
            filters={"parent": design_master, "stage_name": stage_name},
            fieldname=["stage_name", "output_item", "qi_template", "sample_size_formula", "is_final_stage"],
            as_dict=True)
    if not stage_config:
        return create_quality_inspection(work_order, _map_stage_name_to_legacy(stage_name))
    output_item = stage_config.output_item or ""
    batch_no = StockEntryRepository.get_finished_item_batch(se_name, output_item) or ""
    wo_context = WorkOrderRepository.get_design_context(work_order)
    wo_qty = cint(wo_context.get("qty") or 1)
    sample_size = _calculate_sample_size(stage_config.sample_size_formula or "1", wo_qty)
    stage_lower = stage_name.lower()
    if "weav" in stage_lower or "grey" in stage_lower:
        rt_stage = "grey"
    elif "finish" in stage_lower or "dye" in stage_lower:
        rt_stage = "finishing"
    else:
        rt_stage = "final"
    roll_ticket = _find_roll_ticket_for_qi_creation(se_name, batch_no, rt_stage)
    grade_readings = _build_grade_readings_from_config()
    qi = frappe.get_doc({
        "doctype": "Quality Inspection",
        "inspection_type": "In Process",
        "reference_type": "Stock Entry",
        "reference_name": se_name,
        "item_code": output_item,
        "batch_no": batch_no,
        "sample_size": sample_size,
        "quality_inspection_template": stage_config.qi_template or "",
        "inspected_by": frappe.session.user,
        "status": "Accepted",
        "custom_roll_ticket": roll_ticket or "",
        "custom_desar_stage_name": stage_name,
    })
    for reading in grade_readings:
        qi.append("custom_desar_grade_readings", reading)
    _load_readings_from_template(qi, stage_config.qi_template or "")
    qi.insert(ignore_permissions=True)
    frappe.msgprint(_("Quality Inspection <b>{0}</b> created — {1}").format(qi.name, stage_name), alert=True)
    return qi.name


def _build_grade_readings_from_config() -> list:
    from desar_manufacturing.config.settings_manager import SettingsManager
    grades = SettingsManager.get_grade_configuration()
    return [{"grade_code": g.grade_code, "grade_label": g.grade_label, "qty": 0} for g in grades]


def _calculate_sample_size(formula: str, wo_qty: int) -> float:
    try:
        if formula == "1": return 1
        elif formula == "wo_qty": return wo_qty
        elif formula.startswith("wo_qty *"):
            return max(1, int(wo_qty * float(formula.split("*")[1].strip())))
        return 1
    except Exception:
        return 1


def _map_stage_name_to_legacy(stage_name: str) -> str:
    name_lower = stage_name.lower()
    if "grey" in name_lower or "weaving" in name_lower: return "grey"
    elif "finishing" in name_lower or "chemical" in name_lower: return "finishing"
    return "final"


@frappe.whitelist()
def get_grade_configuration() -> list:
    frappe.only_for(READ_ROLES)
    from desar_manufacturing.config.settings_manager import SettingsManager
    return SettingsManager.get_grade_configuration()


@frappe.whitelist()
def get_stage_configuration(design_master: str) -> list:
    frappe.only_for(READ_ROLES)
    if not design_master: return []
    return frappe.get_all("DESAR Stage Configuration",
        filters={"parent": design_master, "parenttype": "Design Master"},
        fields=["stage_seq", "stage_name", "output_item", "qi_required", "qi_template",
                "is_final_stage", "roll_ticket_trigger", "can_split", "bom_no"],
        order_by="stage_seq asc")


@frappe.whitelist()
def get_job_card_qi_config(work_order: str) -> dict:
    frappe.only_for(READ_ROLES)
    if not work_order: return {}
    wo = frappe.get_doc("Work Order", work_order)
    if wo.docstatus != 1: return {}
    design_master = wo.get("custom_design_master")
    production_item = wo.production_item
    if not design_master or not production_item: return {}
    stage = frappe.db.get_value("DESAR Stage Configuration",
        filters={"parent": design_master, "output_item": production_item},
        fieldname=["stage_name", "qi_required", "is_final_stage"], as_dict=True)
    if not stage or not stage.qi_required: return {}
    se_name = frappe.db.get_value("Stock Entry",
        filters={"work_order": work_order, "stock_entry_type": "Manufacture", "docstatus": 1}, fieldname="name")
    if not se_name: return {}
    qi_exists = frappe.db.exists("Quality Inspection", {"reference_name": se_name, "docstatus": ["!=", 2]})
    if qi_exists: return {"qi_exists": True, "stage_name": stage.stage_name}
    return {"stage_name": stage.stage_name, "production_item": production_item, "qi_exists": False}


@frappe.whitelist()
def get_job_card_actions(work_order: str) -> dict:
    frappe.only_for(READ_ROLES)
    if not work_order: return {}
    try:
        wo = frappe.get_doc("Work Order", work_order)
        if wo.docstatus != 1: return {}
        manufacture_se = frappe.db.get_value("Stock Entry",
            {"work_order": work_order, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
        transfer_se = frappe.db.get_value("Stock Entry",
            {"work_order": work_order, "stock_entry_type": "Material Transfer for Manufacture", "docstatus": 1}, "name")
        open_jcs = frappe.db.count("Job Card", {"work_order": work_order, "docstatus": ["!=", 1]})
        all_jcs_done = (open_jcs == 0)
        result = {
            "can_transfer": bool(not manufacture_se and not wo.skip_transfer and all_jcs_done),
            "can_finish": bool(all_jcs_done and not manufacture_se and (transfer_se or wo.skip_transfer)),
        }
        design_master = wo.get("custom_design_master")
        production_item = wo.production_item
        if design_master and production_item:
            stage = frappe.db.get_value("DESAR Stage Configuration",
                {"parent": design_master, "output_item": production_item},
                ["stage_name", "qi_required", "is_final_stage"], as_dict=True)
            if stage and stage.qi_required and manufacture_se:
                qi_exists = bool(frappe.db.exists("Quality Inspection",
                    {"reference_name": manufacture_se, "docstatus": ["!=", 2]}))
                result["qi_config"] = {"stage_name": stage.stage_name, "production_item": production_item, "qi_exists": qi_exists}
        return result
    except Exception:
        frappe.log_error(title=f"DESAR: get_job_card_actions failed for {work_order}", message=frappe.get_traceback())
        return {}


@frappe.whitelist()
def finish_work_order(work_order: str) -> dict:
    from desar_manufacturing.api.production_order import MUTATE_ROLES
    frappe.only_for(MUTATE_ROLES)
    if not work_order: frappe.throw(_("Work Order required"))
    wo = frappe.get_doc("Work Order", work_order)
    if wo.docstatus != 1: frappe.throw(_("Work Order must be submitted"))
    if wo.status == "Completed": frappe.throw(_("Work Order is already completed"))
    open_jcs = frappe.db.count("Job Card", {"work_order": work_order, "docstatus": ["!=", 1]})
    if open_jcs > 0:
        frappe.throw(_("{0} Job Card(s) are not yet completed.").format(open_jcs))
    existing_se = frappe.db.get_value("Stock Entry",
        {"work_order": work_order, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
    if existing_se: frappe.throw(_("Manufacture Entry {0} already exists").format(existing_se))
    try:
        from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
        se = make_stock_entry(work_order, "Manufacture", wo.qty)
        se_doc = frappe.get_doc(se)
        se_doc.flags.ignore_permissions = True
        se_doc.insert()
        se_doc.submit()
        frappe.msgprint(_("Work Order {0} completed. Manufacture Entry {1} created.").format(work_order, se_doc.name), alert=True)
        return {"se_name": se_doc.name, "work_order": work_order}
    except Exception:
        frappe.log_error(title=f"DESAR: finish_work_order failed for {work_order}", message=frappe.get_traceback())
        frappe.throw(_("Failed to create Manufacture Entry. Please check error log."))


@frappe.whitelist()
def create_transfer_se(work_order: str) -> dict:
    from desar_manufacturing.api.production_order import MUTATE_ROLES
    frappe.only_for(MUTATE_ROLES)
    if not work_order: frappe.throw(_("Work Order required"))
    wo = frappe.get_doc("Work Order", work_order)
    if wo.docstatus != 1: frappe.throw(_("Work Order must be submitted"))
    existing = frappe.db.get_value("Stock Entry",
        {"work_order": work_order, "stock_entry_type": "Material Transfer for Manufacture", "docstatus": 1}, "name")
    if existing: frappe.throw(_("Transfer Entry {0} already exists").format(existing))
    try:
        from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
        se = make_stock_entry(work_order, "Material Transfer for Manufacture", wo.qty)
        se_doc = frappe.get_doc(se)
        se_doc.flags.ignore_permissions = True
        for item in se_doc.items:
            if frappe.db.get_value("Item", item.item_code, "has_batch_no"):
                batch = _get_input_batch_for_wo(work_order, item.item_code)
                if batch:
                    item.batch_no = batch
                    # Fix source warehouse — use where the batch actually is
                    actual_wh = _get_batch_warehouse(batch, item.item_code)
                    if actual_wh:
                        item.s_warehouse = actual_wh
        se_doc.insert()
        se_doc.submit()
        return {"se_name": se_doc.name, "submitted": True}
    except Exception:
        frappe.log_error(title=f"DESAR: create_transfer_se failed for {work_order}", message=frappe.get_traceback())
        frappe.throw(_("Failed to create Transfer Entry. Please check error log."))


def _get_batch_warehouse(batch_no: str, item_code: str) -> str:
    """Find the warehouse where a batch currently has positive stock."""
    result = frappe.db.sql("""
        SELECT warehouse FROM `tabStock Ledger Entry`
        WHERE batch_no = %s AND item_code = %s AND is_cancelled = 0
        GROUP BY warehouse
        HAVING SUM(actual_qty) > 0
        ORDER BY MAX(posting_date) DESC
        LIMIT 1
    """, (batch_no, item_code), as_dict=True)
    if result:
        return result[0].warehouse

    # Try via Serial and Batch Bundle
    result2 = frappe.db.sql("""
        SELECT sle.warehouse FROM `tabStock Ledger Entry` sle
        JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
        WHERE sbe.batch_no = %s AND sle.item_code = %s AND sle.is_cancelled = 0
        GROUP BY sle.warehouse
        HAVING SUM(sle.actual_qty) > 0
        ORDER BY MAX(sle.posting_date) DESC
        LIMIT 1
    """, (batch_no, item_code), as_dict=True)
    return result2[0].warehouse if result2 else ""


def _get_input_batch_for_wo(work_order: str, item_code: str) -> str:
    """
    Find correct input batch using Production Plan chain.
    All 4 WOs share the same Production Plan — works correctly
    with concurrent production plans.
    """
    # Use Production Plan as linking key (all 4 WOs share same PP)
    production_plan = frappe.db.get_value("Work Order", work_order, "production_plan")
    if production_plan:
        completed_wo = frappe.db.get_value("Work Order",
            {"production_plan": production_plan, "production_item": item_code,
             "status": "Completed", "docstatus": 1}, "name")
        if completed_wo:
            se_name = frappe.db.get_value("Stock Entry",
                {"work_order": completed_wo, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
            if se_name:
                return StockEntryRepository.get_finished_item_batch(se_name, item_code) or ""

    # Fallback: Sales Order chain (for WO-4 which has SO link)
    sales_order = frappe.db.get_value("Work Order", work_order, "sales_order")
    if sales_order:
        completed_wo = frappe.db.get_value("Work Order",
            {"sales_order": sales_order, "production_item": item_code,
             "status": "Completed", "docstatus": 1}, "name")
        if completed_wo:
            se_name = frappe.db.get_value("Stock Entry",
                {"work_order": completed_wo, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
            if se_name:
                return StockEntryRepository.get_finished_item_batch(se_name, item_code) or ""

    # Last resort: most recent completed WO for this item
    completed_wo = frappe.db.get_value("Work Order",
        {"production_item": item_code, "status": "Completed", "docstatus": 1},
        "name", order_by="modified desc")
    if not completed_wo:
        return ""
    se_name = frappe.db.get_value("Stock Entry",
        {"work_order": completed_wo, "stock_entry_type": "Manufacture", "docstatus": 1}, "name")
    if not se_name:
        return ""
    return StockEntryRepository.get_finished_item_batch(se_name, item_code) or ""


@frappe.whitelist()
def get_bom_design_context(bom_no: str) -> dict:
    frappe.only_for(READ_ROLES)
    if not bom_no: return {}
    return frappe.db.get_value("BOM", bom_no,
        ["custom_design_no", "custom_article_name", "custom_design_master"], as_dict=True) or {}


@frappe.whitelist()
def get_stage_skip_transfer(work_order: str = None, design_master: str = None, production_item: str = None) -> dict:
    frappe.only_for(READ_ROLES)
    if work_order and not design_master:
        result = frappe.db.get_value("Work Order", work_order, ["custom_design_master", "production_item"])
        if result:
            design_master, production_item = result
    if not design_master or not production_item: return {}
    stage = frappe.db.get_value("DESAR Stage Configuration",
        {"parent": design_master, "output_item": production_item},
        ["stage_name", "skip_transfer"], as_dict=True)
    if not stage: return {}
    should_skip = 0
    if stage.get("skip_transfer"):
        should_skip = 1
    else:
        stage_lower = (stage.get("stage_name") or "").lower()
        if "warp" in stage_lower:
            should_skip = 1
    return {"stage_name": stage.get("stage_name"), "skip_transfer": should_skip}


@frappe.whitelist()
def check_manufacture_se_exists(work_order: str) -> bool:
    frappe.only_for(READ_ROLES)
    if not work_order: return False
    return bool(frappe.db.exists("Stock Entry",
        {"work_order": work_order, "stock_entry_type": "Manufacture", "docstatus": 1}))
