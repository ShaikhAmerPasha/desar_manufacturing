"""
Quality Inspection event handlers.
v3.3: Flexible stage matching with LIKE pattern for Finishing stage.
"""
import frappe
from frappe import _
from frappe.utils import flt


def before_submit(doc, method):
    readings = doc.get("custom_desar_grade_readings") or []
    if not readings:
        return
    total = sum(flt(r.get("qty") or 0) for r in readings)
    if not total:
        return
    stage_name = doc.get("custom_desar_stage_name") or ""
    if not _is_final_stage(stage_name):
        return
    wo_qty = _get_wo_qty(doc)
    if wo_qty and abs(total - flt(wo_qty)) > 0.01:
        if total > flt(wo_qty):
            frappe.throw(_("Final grade total ({0}) cannot exceed manufactured qty ({1}).").format(int(total), int(wo_qty)))
        else:
            frappe.throw(_("Final grade total ({0}) is less than manufactured qty ({1}). {2} piece(s) unaccounted.").format(int(total), int(wo_qty), int(flt(wo_qty) - total)))
    _validate_grade_adjustments(doc, stage_name, readings)


def _validate_grade_adjustments(doc, stage_name, final_readings):
    rt_name = doc.get("custom_roll_ticket") or ""
    if not rt_name:
        return
    finishing_grades = _get_stage_grades_from_rt(rt_name, "Finish")
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


def _get_stage_grades_from_rt(rt_name, stage_name_pattern):
    """Use LIKE pattern for flexible stage name matching."""
    actual_stage = frappe.db.get_value(
        "DESAR Roll Ticket Stage Grade",
        {"parent": rt_name, "stage_name": ["like", f"%{stage_name_pattern}%"]},
        "stage_name"
    )
    if not actual_stage:
        return {}
    rows = frappe.get_all(
        "DESAR Roll Ticket Stage Grade",
        filters={"parent": rt_name, "stage_name": actual_stage},
        fields=["grade_code", "qty"],
    )
    return {r.grade_code: flt(r.qty) for r in rows}


def _is_final_stage(stage_name):
    if not stage_name:
        return False
    return bool(frappe.db.get_value(
        "DESAR Stage Configuration",
        filters={"stage_name": stage_name, "is_final_stage": 1},
        fieldname="name",
    ))


def on_submit(doc, method):
    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    RollTicketService.update_from_qi(doc)
    if _is_final_stage(doc.get("custom_desar_stage_name") or ""):
        from desar_manufacturing.services.repack_service import RepackService
        RepackService.create_from_final_qi(doc)


def _get_wo_qty(doc):
    from frappe.utils import flt as _flt
    if doc.reference_type == "Stock Entry" and doc.reference_name:
        wo_name = frappe.db.get_value("Stock Entry", doc.reference_name, "work_order")
        if wo_name:
            return _flt(frappe.db.get_value("Work Order", wo_name, "qty"))
    return 0
