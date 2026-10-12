import frappe
from frappe import _

from desar_manufacturing.utils import report_queries


def execute(filters=None):
    filters = filters or {}
    by_roll = filters.get("group_by") == "Roll"
    return get_columns(by_roll), build_rows(filters.get("work_order"), by_roll)


def get_columns(by_roll: bool) -> list:
    key = {"label": _("Roll Ticket" if by_roll else "Work Order"), "fieldname": "key",
           "fieldtype": "Link", "options": "Roll Ticket" if by_roll else "Work Order", "width": 180}
    numbers = [("total", "Total"), ("sellable", "Sellable (non scrap)"), ("scrap", "Scrap"),
               ("loss", "Process Loss"), ("gain", "Count Gain")]
    columns = [key] + [{"label": _(label), "fieldname": name, "fieldtype": "Int", "width": 120}
                       for name, label in numbers]
    columns += [{"label": _("Yield %"), "fieldname": "yield_pct", "fieldtype": "Percent", "width": 100},
                {"label": _("Scrap %"), "fieldname": "scrap_pct", "fieldtype": "Percent", "width": 100}]
    return columns


def build_rows(work_order: str, by_roll: bool) -> list:
    scrap = report_queries.scrap_grades()
    rows = {}
    for row in report_queries.final_grade_rows(work_order=work_order):
        entry = rows.setdefault(row.roll_ticket if by_roll else row.work_order, _blank())
        entry["total"] += row.qty
        entry["scrap" if row.grade_code in scrap else "sellable"] += row.qty
    for row in report_queries.adjustment_rows(work_order=work_order):
        entry = rows.setdefault(row.roll_ticket if by_roll else row.work_order, _blank())
        entry["loss" if row.qty < 0 else "gain"] += abs(row.qty)
    return [_finish(key, entry) for key, entry in sorted(rows.items(), key=lambda item: str(item[0]))]


def _blank() -> dict:
    return {"total": 0, "sellable": 0, "scrap": 0, "loss": 0, "gain": 0}


def _finish(key, entry: dict) -> dict:
    total = entry["total"]
    return {"key": key, **entry, "yield_pct": entry["sellable"] * 100 / total if total else 0,
            "scrap_pct": entry["scrap"] * 100 / total if total else 0}
