"""Tasks for factory workers: Job Cards and Roll Inspections assigned to them."""
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import now_datetime

from desar_manufacturing.services import inspection_service

WORKER_ROLE = "DESAR Factory Worker"
SUPERVISOR_ROLES = {"System Manager", "DESAR Supervisor"}
JOB_CARD, INSPECTION = "Job Card", "Roll Inspection"


@contextmanager
def _as_system():
    """Workers hold no document permissions; their assigned task runs with system rights."""
    user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        yield
    finally:
        frappe.set_user(user)


def is_supervisor(user: str = None) -> bool:
    return bool(SUPERVISOR_ROLES & set(frappe.get_roles(user or frappe.session.user)))


def assigned_names(doctype: str, user: str) -> list:
    return frappe.get_all("ToDo", filters={"reference_type": doctype, "allocated_to": user, "status": "Open"},
                          pluck="reference_name")


def require_assignment(doctype: str, name: str) -> None:
    if is_supervisor() or name in assigned_names(doctype, frappe.session.user):
        return
    frappe.throw(_("This task is not assigned to you."), frappe.PermissionError)


def my_tasks() -> list:
    user = frappe.session.user
    cards = [_job_card_task(name) for name in assigned_names(JOB_CARD, user)]
    inspections = [_inspection_task(name) for name in assigned_names(INSPECTION, user)]
    return [task for task in cards + inspections if task]


def _job_card_task(name: str):
    card = frappe.db.get_value(JOB_CARD, name, ["operation", "workstation", "for_quantity", "docstatus",
                                                  "custom_production_beam", "custom_started_at"], as_dict=True)
    if not card or card.docstatus != 0:
        return None
    return {"kind": JOB_CARD, "name": name, "station": card.operation, "title": card.operation,
            "subtitle": f"{card.custom_production_beam or ''} · {card.workstation or ''} · {card.for_quantity:g}",
            "status": "In progress" if card.custom_started_at else "Waiting"}


def _inspection_task(name: str):
    doc = frappe.db.get_value(INSPECTION, name, ["roll_ticket", "stage", "docstatus"], as_dict=True)
    if not doc or doc.docstatus != 0:
        return None
    return {"kind": INSPECTION, "name": name, "station": doc.stage, "title": doc.roll_ticket,
            "subtitle": doc.stage, "status": "Waiting"}


def start_job(job_card: str) -> None:
    require_assignment(JOB_CARD, job_card)
    if frappe.db.get_value(JOB_CARD, job_card, "custom_started_at"):
        frappe.throw(_("This job is already started."))
    frappe.db.set_value(JOB_CARD, job_card, "custom_started_at", now_datetime())


def complete_job(job_card: str, completed_qty: float = None, consumption: list = None) -> None:
    require_assignment(JOB_CARD, job_card)
    card = frappe.get_doc(JOB_CARD, job_card)
    if not card.custom_started_at:
        frappe.throw(_("Start the job first."))
    card.append("time_logs", {"from_time": card.custom_started_at, "to_time": now_datetime(),
                              "completed_qty": completed_qty or card.for_quantity})
    for row in consumption or []:
        card.append("custom_actual_consumption", {"item_code": row["item_code"], "qty": row["qty"]})
    card.remarks = _("Completed by {0}").format(frappe.session.user)
    with _as_system():
        card.save()
        card.submit()


def get_inspection(name: str) -> dict:
    require_assignment(INSPECTION, name)
    doc = frappe.get_doc(INSPECTION, name)
    stage = frappe.get_cached_doc("Inspection Stage", doc.stage)
    reasons = frappe.get_all("Inspection Reason", filters={"is_active": 1}, fields=["name", "kind"])
    return {
        "name": doc.name, "roll_ticket": doc.roll_ticket, "stage": doc.stage, "entry_mode": stage.entry_mode,
        "opening": [_grade(row) for row in doc.opening], "closing": [_grade(row) for row in doc.closing],
        "movements": [row.as_dict() for row in doc.movements],
        "adjustments": [row.as_dict() for row in doc.adjustments],
        "reasons": reasons, "grades": [code for code, _label in inspection_service.configured_grades()],
        "docstatus": doc.docstatus,
    }


def _grade(row) -> dict:
    return {"grade_code": row.grade_code, "grade_label": row.grade_label, "qty": row.qty}


def save_inspection(name: str, closing: list = None, movements: list = None, adjustments: list = None):
    require_assignment(INSPECTION, name)
    doc = frappe.get_doc(INSPECTION, name)
    if doc.docstatus != 0:
        frappe.throw(_("This inspection is already submitted."))
    if closing is not None:
        doc.set("closing", [{"grade_code": r["grade_code"], "qty": r["qty"]} for r in closing])
    if movements is not None:
        doc.set("movements", movements)
    if adjustments is not None:
        doc.set("adjustments", adjustments)
    doc.save(ignore_permissions=True)
    return get_inspection(name)


def submit_inspection(name: str) -> None:
    require_assignment(INSPECTION, name)
    doc = frappe.get_doc(INSPECTION, name)
    with _as_system():
        doc.submit()
    _clear_assignments(INSPECTION, name)


# ── Supervisor ─────────────────────────────────────────────────────────────

def workers() -> list:
    users = frappe.get_all("Has Role", filters={"role": WORKER_ROLE, "parenttype": "User"}, pluck="parent")
    return frappe.get_all("User", filters={"name": ["in", users], "enabled": 1}, fields=["name", "full_name"])


def assign_job_card(job_card: str, user: str) -> None:
    _require_supervisor()
    _assign(JOB_CARD, job_card, user)


def assign_inspection(roll_ticket: str, stage: str, user: str) -> str:
    _require_supervisor()
    existing = frappe.db.get_value(INSPECTION, {"roll_ticket": roll_ticket, "stage": stage, "docstatus": 0})
    name = existing or frappe.get_doc({"doctype": INSPECTION, "roll_ticket": roll_ticket, "stage": stage}
                                      ).insert(ignore_permissions=True).name
    _assign(INSPECTION, name, user)
    return name


def _assign(doctype: str, name: str, user: str) -> None:
    if WORKER_ROLE not in frappe.get_roles(user):
        frappe.throw(_("{0} is not a factory worker.").format(user))
    _clear_assignments(doctype, name)
    frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "reference_type": doctype, "reference_name": name,
                    "assigned_by": frappe.session.user, "description": _("{0} {1}").format(doctype, name)}
                   ).insert(ignore_permissions=True)


def _clear_assignments(doctype: str, name: str) -> None:
    for todo in frappe.get_all("ToDo", filters={"reference_type": doctype, "reference_name": name,
                                                 "status": "Open"}, pluck="name"):
        frappe.get_doc("ToDo", todo).update({"status": "Cancelled"}).save(ignore_permissions=True)


def assigned_names_for(doctype: str, name: str) -> list:
    return frappe.get_all("ToDo", filters={"reference_type": doctype, "reference_name": name, "status": "Open"},
                          pluck="allocated_to")


def unassigned_tasks() -> list:
    _require_supervisor()
    cards = frappe.get_all(JOB_CARD, filters={"docstatus": 0}, fields=["name", "operation", "workstation",
                                                                         "custom_production_beam"])
    return [{"kind": JOB_CARD, "name": c.name, "title": c.operation,
             "subtitle": f"{c.custom_production_beam or ''} · {c.workstation or ''}",
             "assigned_to": assigned_names_for(JOB_CARD, c.name)} for c in cards]


def _require_supervisor() -> None:
    if not is_supervisor():
        frappe.throw(_("Only a supervisor can assign work."), frappe.PermissionError)
