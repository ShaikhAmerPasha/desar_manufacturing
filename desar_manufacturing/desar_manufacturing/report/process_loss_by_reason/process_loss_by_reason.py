from frappe import _

from desar_manufacturing.utils import report_queries


def execute(filters=None):
    work_order = (filters or {}).get("work_order")
    totals = {}
    for row in report_queries.adjustment_rows(work_order=work_order):
        key = (_("Process loss") if row.qty < 0 else _("Count gain"), row.reason)
        totals[key] = totals.get(key, 0) + abs(row.qty)
    data = [{"kind": kind, "reason": reason, "qty": qty} for (kind, reason), qty in sorted(totals.items())]
    return get_columns(), data


def get_columns() -> list:
    return [
        {"label": _("Type"), "fieldname": "kind", "fieldtype": "Data", "width": 140},
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Link", "options": "Inspection Reason", "width": 240},
        {"label": _("Pieces"), "fieldname": "qty", "fieldtype": "Int", "width": 100},
    ]
