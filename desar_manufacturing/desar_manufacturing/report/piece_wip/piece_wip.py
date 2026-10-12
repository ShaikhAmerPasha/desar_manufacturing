import frappe
from frappe import _


def execute(filters=None):
    return get_columns(), stage_rows() + operation_rows()


def get_columns() -> list:
    return [
        {"label": _("Position"), "fieldname": "position", "fieldtype": "Data", "width": 260},
        {"label": _("Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 140},
        {"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "width": 100},
    ]


def stage_rows() -> list:
    """Rolls grouped by the last inspection stage they completed."""
    stages = frappe.get_all("Inspection Stage", fields=["name", "sequence"], order_by="sequence")
    last_stage = {}
    for roll in frappe.get_all("Roll Ticket", filters={"work_order": ["is", "set"]}, pluck="name"):
        done = frappe.get_all("Roll Inspection", filters={"roll_ticket": roll, "docstatus": 1}, pluck="stage")
        ranks = [stage.sequence for stage in stages if stage.name in done]
        label = next((s.name for s in stages if s.sequence == max(ranks)), None) if ranks else None
        last_stage[label or _("Not inspected")] = last_stage.get(label or _("Not inspected"), 0) + 1
    return [{"position": _("After {0} inspection").format(name) if name != _("Not inspected") else name,
             "kind": _("Rolls"), "count": count} for name, count in last_stage.items()]


def operation_rows() -> list:
    rows = frappe.db.sql(
        """select operation, count(*) from `tabJob Card`
        where docstatus = 0 and custom_production_beam is not null group by operation""")
    return [{"position": operation, "kind": _("Open Job Cards"), "count": count} for operation, count in rows]
