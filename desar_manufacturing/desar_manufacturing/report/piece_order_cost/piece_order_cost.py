import frappe
from frappe import _
from frappe.utils import flt

from desar_manufacturing.services import closing_service

UNASSIGNED = _("Not tied to an operation")


def execute(filters=None):
    work_order = (filters or {}).get("work_order")
    if not work_order:
        return get_columns(), []
    material = material_cost_by_operation(work_order)
    labour = labour_cost_by_operation(work_order)
    operations = sorted(set(material) | set(labour), key=lambda name: (name == UNASSIGNED, name))
    data = [_row(operation, material.get(operation, 0), labour.get(operation, 0)) for operation in operations]
    data.append(_row(_("Total"), sum(material.values()), sum(labour.values())))
    return get_columns(), data


def get_columns() -> list:
    return [
        {"label": _("Operation"), "fieldname": "operation", "fieldtype": "Data", "width": 220},
        {"label": _("Material Cost"), "fieldname": "material_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Labour and Machine Cost"), "fieldname": "labour_cost", "fieldtype": "Currency", "width": 180},
        {"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 140},
    ]


def _row(operation: str, material: float, labour: float) -> dict:
    return {"operation": operation, "material_cost": material, "labour_cost": labour, "total": material + labour}


def material_cost_by_operation(work_order: str) -> dict:
    rates = closing_service.transfer_rates(work_order) if _issued(work_order) else {}
    usage = closing_service.actual_usage(work_order)
    costs = {}
    for item in frappe.get_doc("Work Order", work_order).required_items:
        qty = usage.get(item.item_code, item.required_qty)
        rate = rates.get(item.item_code) or flt(frappe.db.get_value("Item", item.item_code, "valuation_rate"))
        key = item.operation or UNASSIGNED
        costs[key] = costs.get(key, 0) + flt(qty) * rate
    return costs


def _issued(work_order: str) -> bool:
    return bool(closing_service._transfer_entries(work_order))


def labour_cost_by_operation(work_order: str) -> dict:
    rows = frappe.db.sql(
        """select operation, sum(total_time_in_mins * hour_rate / 60) from `tabJob Card`
        where work_order = %s and docstatus = 1 group by operation""", work_order)
    return {operation: flt(cost) for operation, cost in rows}
