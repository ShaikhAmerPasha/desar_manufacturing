import frappe
from frappe import _

from desar_manufacturing.utils import report_queries


def execute(filters=None):
    sales_order = (filters or {}).get("sales_order")
    if not sales_order:
        return get_columns(), []
    return get_columns(), [_row(order, report_queries.final_grade_rows(work_order=order.name))
                           for order in _orders(sales_order)]


def get_columns() -> list:
    columns = [
        {"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 160},
        {"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Planned"), "fieldname": "qty", "fieldtype": "Int", "width": 90},
        {"label": _("Beams"), "fieldname": "beams", "fieldtype": "Int", "width": 80},
        {"label": _("Rolls"), "fieldname": "rolls", "fieldtype": "Int", "width": 80},
        {"label": _("Finished Pieces"), "fieldname": "finished", "fieldtype": "Int", "width": 120},
        {"label": _("Sellable"), "fieldname": "sellable", "fieldtype": "Int", "width": 100},
        {"label": _("Scrap"), "fieldname": "scrap", "fieldtype": "Int", "width": 90},
    ]
    return columns


def _orders(sales_order: str) -> list:
    return frappe.get_all("Work Order", filters={"sales_order": sales_order, "docstatus": 1},
                          fields=["name", "production_item", "status", "qty"], order_by="creation")


def _row(order, grades: list) -> dict:
    scrap_codes = report_queries.scrap_grades()
    total = sum(row.qty for row in grades)
    scrap = sum(row.qty for row in grades if row.grade_code in scrap_codes)
    return {"work_order": order.name, "item": order.production_item, "status": order.status, "qty": order.qty,
            "beams": frappe.db.count("Production Beam", {"work_order": order.name, "is_group": 0}),
            "rolls": frappe.db.count("Roll Ticket", {"work_order": order.name}),
            "finished": total, "sellable": total - scrap, "scrap": scrap}
