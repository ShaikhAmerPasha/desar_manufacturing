"""Whitelisted endpoints for the factory tablet app. Logic lives in shop_floor_service."""
import frappe

from desar_manufacturing.services import shop_floor_service as service

ROLES = [service.WORKER_ROLE, "DESAR Supervisor", "System Manager"]


def _allowed() -> None:
    """Role gate. frappe.only_for is skipped while tests run, so check the roles directly."""
    if frappe.session.user != "Administrator" and set(ROLES).isdisjoint(frappe.get_roles()):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def my_tasks() -> list:
    _allowed()
    return service.my_tasks()


@frappe.whitelist()
def start_job(job_card: str) -> None:
    _allowed()
    service.start_job(job_card)


@frappe.whitelist()
def complete_job(job_card: str, completed_qty: float = None, consumption: str = None) -> None:
    _allowed()
    service.complete_job(job_card, completed_qty, frappe.parse_json(consumption) if consumption else None)


@frappe.whitelist()
def get_inspection(name: str) -> dict:
    _allowed()
    return service.get_inspection(name)


@frappe.whitelist()
def save_inspection(name: str, closing: str = None, movements: str = None, adjustments: str = None) -> dict:
    _allowed()
    return service.save_inspection(name, *(frappe.parse_json(v) if v else None for v in (closing, movements, adjustments)))


@frappe.whitelist()
def submit_inspection(name: str) -> None:
    _allowed()
    service.submit_inspection(name)


@frappe.whitelist()
def workers() -> list:
    _allowed()
    return service.workers()


@frappe.whitelist()
def unassigned_tasks() -> list:
    _allowed()
    return service.unassigned_tasks()


@frappe.whitelist()
def assign_job_card(job_card: str, user: str) -> None:
    _allowed()
    service.assign_job_card(job_card, user)


@frappe.whitelist()
def assign_inspection(roll_ticket: str, stage: str, user: str) -> str:
    _allowed()
    return service.assign_inspection(roll_ticket, stage, user)
