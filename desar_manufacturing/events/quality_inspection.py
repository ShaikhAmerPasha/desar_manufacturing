"""
Quality Inspection event handlers.
v3.0: Dynamic mode — reads from DESAR QI Grade Readings child table.
"""
import frappe
from frappe import _
from frappe.utils import flt


def before_submit(doc, method):
    """
    Validate grade totals before QI submit.

    ONLY validates on Final Stage QI — where grade counts must equal
    manufactured qty (every piece accounted for).

    Grey and Finishing QIs have ESTIMATES — no strict validation.
    A Grey Roll QI has grade A/B/C counts in pieces but WO qty = 1 roll.
    These are different units — cannot compare.
    """
    readings = doc.get("custom_desar_grade_readings") or []
    if not readings:
        return  # No dynamic grades — skip

    total = sum(flt(r.get("qty") or 0) for r in readings)
    if not total:
        return  # No grades filled — skip

    # Only validate strictly on Final Stage
    stage_name = doc.get("custom_desar_stage_name") or ""
    if not _is_final_stage(stage_name):
        return  # Grey and Finishing stages — estimates only, no strict check

    # Final stage — total must match WO manufactured qty
    wo_qty = _get_wo_qty(doc)
    if not wo_qty:
        return  # Cannot validate without WO qty

    if abs(total - flt(wo_qty)) > 0.01:
        if total > flt(wo_qty):
            frappe.throw(
                _("Final grade total ({0}) cannot exceed manufactured qty ({1}).").format(
                    int(total), int(wo_qty)
                )
            )
        else:
            diff = int(flt(wo_qty) - total)
            frappe.throw(
                _("Final grade total ({0}) is less than manufactured qty ({1}). "
                  "{2} piece(s) unaccounted.").format(int(total), int(wo_qty), diff)
            )


def _is_final_stage(stage_name: str) -> bool:
    """Check if this stage is marked as is_final_stage in Stage Configuration."""
    if not stage_name:
        return False
    return bool(frappe.db.get_value(
        "DESAR Stage Configuration",
        filters={"stage_name": stage_name, "is_final_stage": 1},
        fieldname="name",
    ))


def on_submit(doc, method):
    """On QI submit: update Roll Ticket, trigger Repack if final stage."""
    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    RollTicketService.update_from_qi(doc)

    if _is_final_stage(doc.get("custom_desar_stage_name") or ""):
        from desar_manufacturing.services.repack_service import RepackService
        RepackService.create_from_final_qi(doc)


def _get_wo_qty(doc) -> float:
    from frappe.utils import flt as _flt
    if doc.reference_type == "Stock Entry" and doc.reference_name:
        wo_name = frappe.db.get_value("Stock Entry", doc.reference_name, "work_order")
        if wo_name:
            return _flt(frappe.db.get_value("Work Order", wo_name, "qty"))
    return 0