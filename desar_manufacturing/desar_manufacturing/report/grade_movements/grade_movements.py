import frappe
from frappe import _

from desar_manufacturing.utils import report_queries


def execute(filters=None):
    work_order = (filters or {}).get("work_order")
    totals = {}
    for row in report_queries.movement_rows(work_order=work_order):
        key = (row.stage, row.from_grade, row.to_grade, row.reason)
        totals[key] = totals.get(key, 0) + row.qty
    data = [{"stage": stage, "from_grade": source, "to_grade": target, "reason": reason, "qty": qty,
             "direction": _direction(source, target)} for (stage, source, target, reason), qty in sorted(totals.items())]
    return get_columns(), data


def get_columns() -> list:
    return [
        {"label": _("Stage"), "fieldname": "stage", "fieldtype": "Link", "options": "Inspection Stage", "width": 120},
        {"label": _("From Grade"), "fieldname": "from_grade", "fieldtype": "Data", "width": 100},
        {"label": _("To Grade"), "fieldname": "to_grade", "fieldtype": "Data", "width": 100},
        {"label": _("Direction"), "fieldname": "direction", "fieldtype": "Data", "width": 100},
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Link", "options": "Inspection Reason", "width": 220},
        {"label": _("Pieces"), "fieldname": "qty", "fieldtype": "Int", "width": 90},
    ]


def _direction(source: str, target: str) -> str:
    """Upgrade when the target grade is valued higher than the source."""
    rates = {row.grade_code: row.valuation_pct or 0 for row in frappe.get_all(
        "DESAR Grade Configuration", filters={"parent": "DESAR Settings"}, fields=["grade_code", "valuation_pct"])}
    return _("Upgrade") if rates.get(target, 0) > rates.get(source, 0) else _("Downgrade")
