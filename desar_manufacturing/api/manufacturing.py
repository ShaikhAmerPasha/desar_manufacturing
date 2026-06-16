"""
DESAR Manufacturing — Public API v2.3

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


# ── Quality Inspection Creation ───────────────────────────────────────────────

@frappe.whitelist()
def create_quality_inspection(work_order: str, stage: str) -> str:
    """
    Create a pre-filled Quality Inspection from a Work Order.
    Called from DESAR QC button group on Work Order form.

    Args:
        work_order: Work Order name
        stage: 'grey' | 'finishing' | 'final'

    Returns:
        Quality Inspection name (new document)

    Raises:
        frappe.ValidationError for bad inputs or missing prerequisites
    """
    # ── Validate inputs ───────────────────────────────────────────────────
    if not work_order:
        frappe.throw(_("Work Order is required"))

    valid_stages = {"grey", "finishing", "final"}
    if stage not in valid_stages:
        frappe.throw(
            _("Invalid stage '{0}'. Valid values: {1}").format(
                stage, ", ".join(sorted(valid_stages))
            )
        )

    # ── Permission ────────────────────────────────────────────────────────
    frappe.has_permission("Quality Inspection", "create", throw=True)

    # ── Work Order must exist and be submitted ────────────────────────────
    wo_docstatus = frappe.db.get_value("Work Order", work_order, "docstatus")
    if wo_docstatus is None:
        frappe.throw(_("Work Order <b>{0}</b> not found").format(work_order))
    if cint(wo_docstatus) != 1:
        frappe.throw(
            _("Work Order must be submitted before creating a Quality Inspection")
        )

    # ── Manufacture SE must exist (WO must be finished) ───────────────────
    se_name = WorkOrderRepository.get_manufacture_se(work_order)
    if not se_name:
        frappe.throw(
            _("No submitted Manufacture entry found for <b>{0}</b>.<br>"
              "Please finish the Work Order first (click <b>Finish</b>).").format(work_order)
        )

    # ── Build stage config ────────────────────────────────────────────────
    wo_context = WorkOrderRepository.get_design_context(work_order)
    config = _get_stage_config(stage, wo_context)

    # Validate stage-specific item exists
    if not config.get("item_code"):
        frappe.throw(
            _("Cannot determine item code for stage '{0}'. "
              "Check Work Order production item.").format(stage)
        )

    # ── Get batch from Manufacture SE ─────────────────────────────────────
    batch_no = (
        StockEntryRepository.get_finished_item_batch(se_name, config["item_code"])
        or ""
    )

    # ── Find Roll Ticket at creation time — store explicit link ───────────
    # This is Option 1 — explicit linking at creation time.
    # Eliminates complex chain traversal in update_from_qi.
    roll_ticket = _find_roll_ticket_for_qi_creation(se_name, batch_no, stage)

    # ── Build and insert QI ───────────────────────────────────────────────
    qi = frappe.get_doc({
        "doctype":                    "Quality Inspection",
        "inspection_type":            "In Process",
        "reference_type":             "Stock Entry",
        "reference_name":             se_name,
        "item_code":                  config["item_code"],
        "batch_no":                   batch_no,
        "sample_size":                config["sample_size"],
        "quality_inspection_template": config["template"],
        "inspected_by":               frappe.session.user,
        "status":                     "Accepted",
        "custom_roll_ticket":         roll_ticket or "",
    })

    _load_readings_from_template(qi, config["template"])

    qi.insert(ignore_permissions=True)

    frappe.msgprint(
        _("Quality Inspection <b>{0}</b> created — {1} stage").format(qi.name, stage),
        alert=True,
    )
    return qi.name


def _get_stage_config(stage: str, wo_context: dict) -> dict:
    """
    Map QI stage to item code, template name, and sample size.

    Grey:      item = Grey Roll,     sample = 1 roll
    Finishing: item = Finished Roll, sample = 1 roll
    Final:     item = production_item (the Shemagh variant), sample = WO qty
    """
    production_item = wo_context.get("production_item") or ""
    wo_qty = cint(wo_context.get("qty") or 1)

    configs = {
        "grey": {
            "item_code":   GREY_ROLL,
            "template":    QITemplates.GREY,
            "sample_size": 1,
        },
        "finishing": {
            "item_code":   FINISHED_ROLL,
            "template":    QITemplates.FINISHING,
            "sample_size": 1,
        },
        "final": {
            "item_code":   production_item,
            "template":    QITemplates.FINAL,
            "sample_size": wo_qty,
        },
    }
    return configs[stage]


def _load_readings_from_template(qi, template_name: str):
    """
    Load readings from QI template into the QI document.
    Handles missing template gracefully — logs error, QI created without readings.
    Uses .get() for all optional fields to handle v15 field name differences.
    """
    if not template_name:
        return

    if not frappe.db.exists("Quality Inspection Template", template_name):
        frappe.log_error(
            title=f"DESAR: QI Template not found — {template_name}",
            message=(
                f"Template '{template_name}' does not exist in ERPNext.\n"
                f"QI created without readings. Create the template and retry."
            ),
        )
        return

    template = frappe.get_doc("Quality Inspection Template", template_name)
    for param in template.get("item_quality_inspection_parameter") or []:
        qi.append("readings", {
            "specification":            param.specification,
            "numeric":                  param.get("numeric") or 0,
            "min_value":                param.get("min_value") or 0,
            "max_value":                param.get("max_value") or 0,
            "formula_based_criteria":   param.get("formula_based_criteria") or 0,
            "acceptance_formula":       param.get("acceptance_formula") or "",
            "reading_1":                "",
            "status":                   "Accepted",
        })


# ── BOM Creation ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def create_boms_from_design(design_master: str) -> dict:
    """
    Create all 4 BOMs from a Design Master.
    Called from Design Master form button.

    Args:
        design_master: Design Master document name

    Returns:
        Dict mapping bom_level_N to created BOM name
    """
    if not design_master:
        frappe.throw(_("Design Master is required"))

    frappe.has_permission("BOM", "create", throw=True)

    from desar_manufacturing.services.bom_service import BOMService
    return BOMService.create_all_boms(design_master)


# ── Grade Summary ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_grade_summary(design_no: str = None, article: str = None) -> dict:
    """
    Return aggregate grade yield across all completed Roll Tickets.
    Used by dashboard and external tools.

    Args:
        design_no: Filter by design number (optional)
        article:   Filter by article name (optional)

    Returns:
        Dict with total_rolls, grade_a/b/c counts and percentages
    """
    filters = {"roll_status": "Completed"}
    if design_no:
        filters["design_no"] = design_no
    if article:
        filters["article_name"] = article

    tickets = frappe.get_all(
        "Roll Ticket",
        filters=filters,
        fields=["cutted_qty_a", "cutted_qty_b", "cutted_qty_c"],
    )

    total_a = sum(flt(t.cutted_qty_a) for t in tickets)
    total_b = sum(flt(t.cutted_qty_b) for t in tickets)
    total_c = sum(flt(t.cutted_qty_c) for t in tickets)
    grand   = total_a + total_b + total_c

    return {
        "total_rolls": len(tickets),
        "grade_a":     total_a,
        "grade_b":     total_b,
        "grade_c":     total_c,
        "grand_total": grand,
        "pct_a":       round(total_a / grand * 100, 1) if grand else 0,
        "pct_b":       round(total_b / grand * 100, 1) if grand else 0,
        "pct_c":       round(total_c / grand * 100, 1) if grand else 0,
    }


def _find_roll_ticket_for_qi_creation(
    se_name: str, batch_no: str, stage: str
) -> str:
    """
    Find the Roll Ticket at QI creation time.
    Called once when QI is created — result stored on QI as custom_roll_ticket.
    This is Option 1 — explicit linking eliminates complex chain traversal later.

    Strategy by stage:
    - Grey:      batch_no is Grey Roll batch → direct lookup
    - Finishing: SE consumed Grey Roll → find by consumed batch
    - Final:     SE consumed Finished Roll → trace back to Grey Roll SE → batch
    """
    from desar_manufacturing.repositories.roll_ticket_repository import RollTicketRepository
    from desar_manufacturing.constants import GREY_ROLL, FINISHED_ROLL

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

            # Find SE that produced the Finished Roll batch
            producing_se = frappe.db.sql("""
                SELECT sle.voucher_no
                FROM `tabStock Ledger Entry` sle
                JOIN `tabSerial and Batch Entry` sbe
                    ON sbe.parent = sle.serial_and_batch_bundle
                WHERE sbe.batch_no = %s
                AND sle.actual_qty > 0
                AND sle.is_cancelled = 0
                LIMIT 1
            """, (finished_batch,), as_dict=True)

            if not producing_se:
                se = frappe.db.get_value(
                    "Stock Ledger Entry",
                    {"item_code": FINISHED_ROLL, "batch_no": finished_batch,
                     "actual_qty": [">", 0], "is_cancelled": 0},
                    "voucher_no"
                )
                if se:
                    producing_se = [{"voucher_no": se}]

            if producing_se:
                grey_batch = _get_consumed_batch(
                    producing_se[0]["voucher_no"], GREY_ROLL
                )
                if grey_batch:
                    return RollTicketRepository.find_by_batch(grey_batch) or ""

    except Exception:
        frappe.log_error(
            title="DESAR: Roll Ticket lookup failed at QI creation",
            message=frappe.get_traceback(),
        )

    return ""


def _get_consumed_batch(se_name: str, item_code: str) -> str:
    """
    Get batch of an item consumed (actual_qty < 0) in a Stock Entry.
    Checks both direct batch_no and Serial and Batch Bundle — v15 compatible.
    """
    result = frappe.db.get_value(
        "Stock Ledger Entry",
        filters={"voucher_no": se_name, "item_code": item_code,
                 "actual_qty": ["<", 0], "is_cancelled": 0},
        fieldname="batch_no",
    )
    if result:
        return result

    bundle = frappe.db.get_value(
        "Stock Ledger Entry",
        filters={"voucher_no": se_name, "item_code": item_code,
                 "actual_qty": ["<", 0], "is_cancelled": 0},
        fieldname="serial_and_batch_bundle",
    )
    if bundle:
        return frappe.db.get_value(
            "Serial and Batch Entry", {"parent": bundle}, "batch_no"
        ) or ""

    return ""

# ── Dynamic Stage-based QI Creation ──────────────────────────────────────────

@frappe.whitelist()
def create_quality_inspection_dynamic(work_order: str, stage_name: str) -> str:
    """
    Create a pre-filled Quality Inspection using Stage Configuration.
    Called from dynamic DESAR QC buttons on Work Order form.

    Args:
        work_order: Work Order name
        stage_name: Stage name from DESAR Stage Configuration

    Returns:
        Quality Inspection name
    """
    if not work_order or not stage_name:
        frappe.throw(_("Work Order and Stage Name are required"))

    frappe.has_permission("Quality Inspection", "create", throw=True)

    wo_docstatus = frappe.db.get_value("Work Order", work_order, "docstatus")
    if cint(wo_docstatus) != 1:
        frappe.throw(_("Work Order must be submitted"))

    se_name = WorkOrderRepository.get_manufacture_se(work_order)
    if not se_name:
        frappe.throw(
            _("No Manufacture entry found for {0}. Finish the Work Order first.").format(work_order)
        )

    # Get stage configuration
    design_master = frappe.db.get_value("Work Order", work_order, "custom_design_master")
    stage_config = None
    if design_master:
        stage_config = frappe.db.get_value(
            "DESAR Stage Configuration",
            filters={"parent": design_master, "stage_name": stage_name},
            fieldname=["stage_name", "output_item", "qi_template", "sample_size_formula", "is_final_stage"],
            as_dict=True,
        )

    if not stage_config:
        # Fallback to legacy
        return create_quality_inspection(work_order, _map_stage_name_to_legacy(stage_name))

    # Get output item and batch
    output_item = stage_config.output_item or ""
    batch_no = StockEntryRepository.get_finished_item_batch(se_name, output_item) or ""

    # Calculate sample size
    wo_context = WorkOrderRepository.get_design_context(work_order)
    wo_qty = cint(wo_context.get("qty") or 1)
    sample_size = _calculate_sample_size(stage_config.sample_size_formula or "1", wo_qty)

    # Find Roll Ticket
    roll_ticket = _find_roll_ticket_for_qi_creation(se_name, batch_no, "grey")  # Use chain lookup

    # Build grade readings from Grade Configuration
    grade_readings = _build_grade_readings_from_config()

    qi = frappe.get_doc({
        "doctype":                     "Quality Inspection",
        "inspection_type":             "In Process",
        "reference_type":              "Stock Entry",
        "reference_name":              se_name,
        "item_code":                   output_item,
        "batch_no":                    batch_no,
        "sample_size":                 sample_size,
        "quality_inspection_template": stage_config.qi_template or "",
        "inspected_by":                frappe.session.user,
        "status":                      "Accepted",
        "custom_roll_ticket":          roll_ticket or "",
        "custom_desar_stage_name":     stage_name,
    })

    # Add grade readings
    for reading in grade_readings:
        qi.append("custom_desar_grade_readings", reading)

    _load_readings_from_template(qi, stage_config.qi_template or "")
    qi.insert(ignore_permissions=True)

    frappe.msgprint(
        _("Quality Inspection <b>{0}</b> created — {1}").format(qi.name, stage_name),
        alert=True,
    )
    return qi.name


def _build_grade_readings_from_config() -> list:
    """
    Build initial grade reading rows from DESAR Grade Configuration.
    One row per active grade, qty=0 (inspector fills in).
    """
    from desar_manufacturing.config.settings_manager import SettingsManager
    grades = SettingsManager.get_grade_configuration()
    return [
        {
            "grade_code":  g.grade_code,
            "grade_label": g.grade_label,
            "qty":         0,
        }
        for g in grades
    ]


def _calculate_sample_size(formula: str, wo_qty: int) -> float:
    """Calculate sample size from formula string."""
    try:
        if formula == "1":
            return 1
        elif formula == "wo_qty":
            return wo_qty
        elif formula.startswith("wo_qty *"):
            factor = float(formula.split("*")[1].strip())
            return max(1, int(wo_qty * factor))
        return 1
    except Exception:
        return 1


def _map_stage_name_to_legacy(stage_name: str) -> str:
    """Map stage name to legacy stage identifier."""
    name_lower = stage_name.lower()
    if "grey" in name_lower or "weaving" in name_lower:
        return "grey"
    elif "finishing" in name_lower or "chemical" in name_lower:
        return "finishing"
    elif "packing" in name_lower or "cutting" in name_lower or "final" in name_lower:
        return "final"
    return "final"


# ── Grade Configuration API ───────────────────────────────────────────────────

@frappe.whitelist()
def get_grade_configuration() -> list:
    """
    Get active grade configuration for use in JS.
    Called from desar.js to build dynamic QI grade input forms.
    """
    from desar_manufacturing.config.settings_manager import SettingsManager
    return SettingsManager.get_grade_configuration()


@frappe.whitelist()
def get_stage_configuration(design_master: str) -> list:
    """
    Get stage configuration for a Design Master.
    Called from desar.js to build dynamic QI buttons on Work Order.
    """
    if not design_master:
        return []

    stages = frappe.get_all(
        "DESAR Stage Configuration",
        filters={"parent": design_master, "parenttype": "Design Master"},
        fields=[
            "stage_seq", "stage_name", "output_item",
            "qi_required", "qi_template", "is_final_stage",
            "roll_ticket_trigger", "can_split", "bom_no"
        ],
        order_by="stage_seq asc",
    )
    return stages
