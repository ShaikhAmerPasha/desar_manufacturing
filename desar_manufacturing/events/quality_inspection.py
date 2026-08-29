"""
Quality Inspection event handlers.
v3.3: Flexible stage matching with LIKE pattern for Finishing stage.
"""
import frappe
from frappe import _
from frappe.utils import flt

from desar_manufacturing.utils.grade_utils import (
    is_final_stage, get_design_master_from_qi, get_work_order_from_qi, get_stage_grades_from_rt,
)
from desar_manufacturing.utils.validation_utils import validate_grade_readings_total


def validate(doc, method):
    ctx = _final_stage_readings(doc)
    if not ctx:
        return
    stage_name, readings, total = ctx
    _guard_all_grades_zero(total)
    _validate_grade_adjustments(doc, stage_name, readings)


def before_submit(doc, method):
    ctx = _final_stage_readings(doc)
    if not ctx:
        return
    stage_name, readings, total = ctx
    _guard_all_grades_zero(total)
    wo_qty = _get_wo_qty(doc)
    valid, message = validate_grade_readings_total(total, wo_qty)
    if not valid:
        frappe.throw(_(message))


def _guard_all_grades_zero(total):
    """
    total==0 across every grade (A/B/C/...) on a final-stage inspection is
    never a legitimate result — it means nobody filled in the counted
    quantities, not that zero pieces were produced. Left unchecked, this
    silently submits a QI with no way to fix it short of cancelling and
    recreating the whole document.
    """
    if not total:
        frappe.throw(_(
            "Grade quantities cannot all be zero for the final inspection. "
            "Enter the actual counted quantities before saving."
        ))


def _final_stage_readings(doc):
    """
    (stage_name, readings, total) if this QI is at its Design Master's final
    stage and has a grade-readings child table at all, else None (not
    applicable to this QI — e.g. an intermediate-stage inspection with no
    grade concept). total may legitimately be 0 — that's for the caller to
    decide is an error, not this function to silently swallow.
    """
    readings = doc.get("custom_desar_grade_readings") or []
    if not readings:
        return None
    stage_name = doc.get("custom_desar_stage_name") or ""
    if not is_final_stage(stage_name, get_design_master_from_qi(doc)):
        return None
    total = sum(flt(r.get("qty") or 0) for r in readings)
    return stage_name, readings, total


def _validate_grade_adjustments(doc, stage_name, final_readings):
    rt_name = doc.get("custom_roll_ticket") or ""
    if not rt_name:
        return
    finishing_grades = get_stage_grades_from_rt(rt_name, "Finish")
    if not finishing_grades:
        return
    final_map = {r.get("grade_code"): flt(r.get("qty") or 0) for r in final_readings}
    has_changes = any(abs(final_map.get(gc, 0) - fq) > 0.01 for gc, fq in finishing_grades.items())
    if not has_changes:
        return
    adjustments = doc.get("custom_desar_grade_adjustments") or []
    if not adjustments:
        frappe.throw(_("Grade counts changed between Finishing and Final Packing inspection. Please fill the <b>Grade Adjustments During Packing</b> table."))
    _validate_adjustment_quantities(finishing_grades, final_map, adjustments)


def _validate_adjustment_quantities(finishing_map, final_map, adjustments):
    expected = dict(finishing_map)
    for adj in adjustments:
        from_grade = adj.get("from_grade") or ""
        to_grade = adj.get("to_grade") or ""
        qty = flt(adj.get("qty") or 0)
        if not from_grade or not to_grade or not qty:
            continue
        if from_grade == to_grade:
            frappe.throw(_("Row {0}: From Grade and To Grade cannot be the same.").format(adj.get("idx", "")))
        expected[from_grade] = expected.get(from_grade, 0) - qty
        expected[to_grade] = expected.get(to_grade, 0) + qty
    mismatches = [
        f"Grade {g}: expected {int(eq)} but got {int(final_map.get(g, 0))}"
        for g, eq in expected.items()
        if abs(final_map.get(g, 0) - eq) > 0.01
    ]
    if mismatches:
        frappe.throw(_("Grade Adjustment quantities do not reconcile:<br>{0}").format("<br>".join(mismatches)))


def on_submit(doc, method):
    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    RollTicketService.update_from_qi(doc)
    if is_final_stage(doc.get("custom_desar_stage_name") or "", get_design_master_from_qi(doc)):
        from desar_manufacturing.services.repack_service import RepackService
        RepackService.create_from_final_qi(doc)


def on_cancel(doc, method):
    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    from desar_manufacturing.services.roll_service import revert_qi_reference

    _guard_repack_se_not_submitted(doc)

    RollTicketService.revert_from_qi_cancel(doc)
    revert_qi_reference(doc.name)

    if is_final_stage(doc.get("custom_desar_stage_name") or "", get_design_master_from_qi(doc)):
        frappe.msgprint(
            _(
                "This was a Final Packing QI. If a Repack Stock Entry was auto-created "
                "from it, review and cancel it manually — it was not reversed automatically."
            ),
            alert=True, indicator="orange",
        )


def _guard_repack_se_not_submitted(doc):
    """
    Block cancelling a Final Packing QI while its auto-created Repack SE is
    still submitted — reversing the QI without also reversing that SE would
    leave a live Repack of stock produced under a now-cancelled inspection.
    """
    repack_se = frappe.db.get_value(
        "Stock Entry", {"custom_source_qi": doc.name, "docstatus": 1}, "name"
    )
    if repack_se:
        frappe.throw(
            _("Cancel Repack Stock Entry {0} first — it was created from this Quality Inspection.").format(repack_se)
        )


def _get_wo_qty(doc):
    wo_name = get_work_order_from_qi(doc)
    return flt(frappe.db.get_value("Work Order", wo_name, "qty")) if wo_name else 0
