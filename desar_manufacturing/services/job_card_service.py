"""Job Cards of a piece based Work Order: one per beam per operation."""
import frappe
from frappe import _
from erpnext.manufacturing.doctype.work_order.work_order import create_job_card

from desar_manufacturing.services import beam_service


def create_beam_job_cards(work_order: str) -> list:
    """Replace the untouched whole-order Job Cards with one per leaf beam per operation."""
    order = frappe.get_doc("Work Order", work_order)
    beams = beam_service.leaf_beams(work_order)
    if not beams:
        frappe.throw(_("Create beams for {0} first.").format(work_order))
    if frappe.get_all("Job Card", filters={"work_order": work_order, "custom_production_beam": ["is", "set"]}, limit=1):
        frappe.throw(_("Beam Job Cards already exist for {0}.").format(work_order))
    _delete_untouched_job_cards(work_order)
    beam_operations = _beam_operations(order)
    return [_make_job_card(order, row, beam, row.operation in beam_operations)
            for row in order.operations for beam in beams]


def _beam_operations(order) -> set:
    process = frappe.db.get_value("Design Master", order.custom_design_master, "production_process")
    if not process:
        return set()
    steps = frappe.get_doc("Production Process", process).steps
    return {step.operation for step in steps if step.uses_beam_workstation}


def _delete_untouched_job_cards(work_order: str) -> None:
    for name in frappe.get_all("Job Card", filters={"work_order": work_order, "docstatus": 0}, pluck="name"):
        if not frappe.db.exists("Job Card Time Log", {"parent": name}):
            frappe.delete_doc("Job Card", name, ignore_permissions=True, force=True)


def _make_job_card(order, row, beam: dict, use_beam_workstation: bool) -> str:
    operation = frappe._dict(row.as_dict())
    operation.job_card_qty = beam.planned_pieces
    if use_beam_workstation and beam.workstation:
        operation.workstation = beam.workstation
    card = create_job_card(order, operation, auto_create=True)
    card.db_set("custom_production_beam", beam.name)
    return card.name
