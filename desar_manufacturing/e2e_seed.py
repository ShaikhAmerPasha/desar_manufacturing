"""Test data for the Playwright suite. Run on a test site:
bench --site <site> execute desar_manufacturing.e2e_seed.setup
bench --site <site> execute desar_manufacturing.e2e_seed.teardown
"""
import json
import os
import secrets

import frappe
from frappe.utils.password import update_password

from desar_manufacturing.install.defaults import seed_factory_worker_role, seed_inspection_defaults
from desar_manufacturing.services import shop_floor_service

WORKER, SUPERVISOR = "e2e-worker@example.com", "e2e-supervisor@example.com"
CREDENTIALS_FILE = os.environ.get("E2E_CREDS", "/tmp/desar_e2e_creds.json")
DESIGN_NO = "E2E-DESIGN"


def setup():
    teardown()
    seed_inspection_defaults()
    seed_factory_worker_role()
    password = secrets.token_urlsafe(12)
    for email, role in ((WORKER, "DESAR Factory Worker"), (SUPERVISOR, "DESAR Supervisor")):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                        "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        update_password(email, password)
    assigned, open_roll = _make_roll(), _make_roll()
    frappe.set_user(SUPERVISOR)
    shop_floor_service.assign_inspection(assigned, "Gray", WORKER)
    frappe.set_user("Administrator")
    frappe.db.commit()
    with open(CREDENTIALS_FILE, "w") as handle:
        json.dump({"password": password, "worker": WORKER, "supervisor": SUPERVISOR,
                   "assigned_roll": assigned, "open_roll": open_roll,
                   "linked": bool(frappe.db.get_value("Work Order", {"docstatus": 1}))}, handle)
    print("e2e data ready")


def _make_roll() -> str:
    work_order = frappe.db.get_value("Work Order", {"docstatus": 1})
    roll = frappe.get_doc({"doctype": "Roll Ticket", "design_no": DESIGN_NO, "size": "60"}).insert(
        ignore_permissions=True)
    frappe.db.set_value("Roll Ticket", roll.name, "work_order", work_order)
    return roll.name


def teardown():
    frappe.set_user("Administrator")
    rolls = frappe.get_all("Roll Ticket", filters={"design_no": DESIGN_NO}, pluck="name")
    for name in frappe.get_all("Roll Inspection", filters={"roll_ticket": ["in", rolls or [""]]}, pluck="name"):
        _remove_inspection(name)
    for name in frappe.get_all("ToDo", filters={"allocated_to": ["in", [WORKER, SUPERVISOR]]}, pluck="name"):
        frappe.delete_doc("ToDo", name, force=True, ignore_permissions=True)
    for name in rolls:
        frappe.delete_doc("Roll Ticket", name, force=True, ignore_permissions=True)
    for email in (WORKER, SUPERVISOR):
        if frappe.db.exists("User", email):
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)
    frappe.db.commit()


def _remove_inspection(name: str) -> None:
    doc = frappe.get_doc("Roll Inspection", name)
    if doc.docstatus == 1:
        doc.cancel()
    frappe.delete_doc("Roll Inspection", name, force=True, ignore_permissions=True)
