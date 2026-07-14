"""
DESAR Production Order API v6
"""
import frappe
from frappe import _

from desar_manufacturing.services import (
	warping_service,
	roll_service,
	production_plan_service,
)

# Matches DESAR Production Order's own doctype permissions: only System Manager
# and DESAR Supervisor can create a PO; DESAR Operator can write to an existing
# one (i.e. run stage transitions) but not create one. DESAR QC Inspector is
# read-only and gets neither.
CREATE_ROLES  = ["System Manager", "DESAR Supervisor"]
MUTATE_ROLES  = ["System Manager", "DESAR Supervisor", "DESAR Operator"]


@frappe.whitelist()
def preview_plan(production_plan: str) -> dict:
	frappe.only_for(CREATE_ROLES)
	return _safe(production_plan_service.preview_plan, production_plan)


@frappe.whitelist()
def create_desar_po(production_plan: str) -> dict:
	frappe.only_for(CREATE_ROLES)
	return _safe(production_plan_service.create_desar_po_from_plan, production_plan)


@frappe.whitelist()
def start_warping(production_order: str) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(warping_service.start_warping, production_order)


@frappe.whitelist()
def complete_warping(production_order: str) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(warping_service.complete_warping, production_order)


@frappe.whitelist()
def split_beam(production_order: str, rows) -> dict:
	frappe.only_for(MUTATE_ROLES)
	parsed = frappe.parse_json(rows) if isinstance(rows, str) else rows
	return _safe(warping_service.split_beam, production_order, parsed)


@frappe.whitelist()
def start_grey_roll(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.start_grey_roll, production_order, int(roll_no))


@frappe.whitelist()
def complete_grey_roll(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.complete_grey_roll, production_order, int(roll_no))


@frappe.whitelist()
def start_finished_roll(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.start_finished_roll, production_order, int(roll_no))


@frappe.whitelist()
def complete_finished_roll(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.complete_finished_roll, production_order, int(roll_no))


@frappe.whitelist()
def start_packing(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.start_packing, production_order, int(roll_no))


@frappe.whitelist()
def complete_packing(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.complete_packing, production_order, int(roll_no))


@frappe.whitelist()
def finalize_packing(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.finalize_packing, production_order, int(roll_no))


@frappe.whitelist()
def complete_roll(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.complete_roll, production_order, int(roll_no))


@frappe.whitelist()
def refresh_roll(production_order: str, roll_no: int) -> dict:
	frappe.only_for(MUTATE_ROLES)
	return _safe(roll_service.refresh_roll, production_order, int(roll_no))


def _safe(fn, *args):
	try:
		return fn(*args)
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.log_error(title=f"DESAR v6: {fn.__name__}", message=frappe.get_traceback())
		frappe.throw(_("Unexpected error. Check Error Log."))
