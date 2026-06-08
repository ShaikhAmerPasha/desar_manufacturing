"""
Quality Inspection event handlers.
THIN layer — validates, delegates to services.
No business logic here.
"""
import frappe
from frappe import _
from frappe.utils import flt
from desar_manufacturing.constants import QIFields


def before_submit(doc, method):
    """
    Validate grade counts before QI is submitted.
    Delegates validation logic to validation_utils.
    """
    from desar_manufacturing.utils.validation_utils import (
        validate_final_grade_counts,
        validate_grey_estimate_reasonable,
        validate_finishing_estimate_reasonable,
    )

    # Final QI — strict validation
    is_valid, error_msg = validate_final_grade_counts(
        grade_a=flt(doc.get(QIFields.FINAL_A)),
        grade_b=flt(doc.get(QIFields.FINAL_B)),
        grade_c=flt(doc.get(QIFields.FINAL_C)),
        wo_qty=_get_wo_qty(doc),
    )
    if not is_valid:
        frappe.throw(_(error_msg))

    # Grey estimate — soft warning only
    grey_warning = validate_grey_estimate_reasonable(
        grey_a=flt(doc.get(QIFields.GREY_A)),
        grey_b=flt(doc.get(QIFields.GREY_B)),
        grey_c=flt(doc.get(QIFields.GREY_C)),
    )
    if grey_warning:
        frappe.msgprint(_(grey_warning), alert=True, indicator="orange")

    # Finishing estimate — soft warning only
    fin_warning = validate_finishing_estimate_reasonable(
        fin_a=flt(doc.get(QIFields.FIN_A)),
        fin_b=flt(doc.get(QIFields.FIN_B)),
        fin_c=flt(doc.get(QIFields.FIN_C)),
    )
    if fin_warning:
        frappe.msgprint(_(fin_warning), alert=True, indicator="orange")


def on_submit(doc, method):
    """
    On QI submit:
    1. Update Roll Ticket grades
    2. Auto-create Repack if this is a Final Packing QI
    """
    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    RollTicketService.update_from_qi(doc)

    # Only create Repack if final grades are filled
    final_total = (
        flt(doc.get(QIFields.FINAL_A))
        + flt(doc.get(QIFields.FINAL_B))
        + flt(doc.get(QIFields.FINAL_C))
    )
    if final_total > 0:
        from desar_manufacturing.services.repack_service import RepackService
        RepackService.create_from_final_qi(doc)


def _get_wo_qty(doc) -> float:
    """Extract Work Order qty from QI reference chain."""
    from frappe.utils import flt as _flt
    if doc.reference_type == "Stock Entry" and doc.reference_name:
        wo_name = frappe.db.get_value(
            "Stock Entry", doc.reference_name, "work_order"
        )
        if wo_name:
            return _flt(frappe.db.get_value("Work Order", wo_name, "qty"))
    return 0
