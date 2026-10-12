"""Close a piece based Work Order: one Manufacture Stock Entry from the final inspections."""
import frappe
from frappe import _
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from frappe.utils import flt

from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.services.repack_service import RepackService
from desar_manufacturing.utils.cost_split import split_cost


def close_order(work_order: str) -> str:
    order = frappe.get_doc("Work Order", work_order)
    _guard_closable(order)
    totals = final_grade_totals(work_order)
    entry = _build_manufacture_entry(order, totals)
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry.name


def _guard_closable(order) -> None:
    if order.docstatus != 1:
        frappe.throw(_("Submit {0} first.").format(order.name))
    if not _transfer_entries(order.name):
        frappe.throw(_("Issue materials for {0} first.").format(order.name))
    _guard_job_cards_done(order.name)
    if frappe.db.exists("Stock Entry", {"work_order": order.name, "purpose": "Manufacture", "docstatus": 1}):
        frappe.throw(_("{0} is already closed.").format(order.name))


def _guard_job_cards_done(work_order: str) -> None:
    open_cards = frappe.get_all("Job Card", filters={"work_order": work_order, "docstatus": 0}, pluck="name")
    if open_cards:
        frappe.throw(_("Complete Job Cards first: {0}").format(", ".join(open_cards[:5])))


def _transfer_entries(work_order: str) -> list:
    return frappe.get_all("Stock Entry", {"work_order": work_order, "docstatus": 1,
                                          "purpose": "Material Transfer for Manufacture"}, pluck="name")


def final_grade_totals(work_order: str) -> dict:
    rolls = frappe.get_all("Roll Ticket", {"work_order": work_order}, pluck="name")
    if not rolls:
        frappe.throw(_("{0} has no rolls.").format(work_order))
    totals, missing = {}, []
    for roll in rolls:
        closing = _final_closing(roll)
        if closing is None:
            missing.append(roll)
            continue
        for grade, qty in closing.items():
            totals[grade] = totals.get(grade, 0) + qty
    if missing:
        frappe.throw(_("Final inspection is not submitted for: {0}").format(", ".join(missing)))
    return totals


def _final_closing(roll: str):
    for name in frappe.get_all("Roll Inspection", {"roll_ticket": roll, "docstatus": 1}, pluck="name"):
        inspection = frappe.get_doc("Roll Inspection", name)
        if frappe.db.get_value("Inspection Stage", inspection.stage, "is_final"):
            return {row.grade_code: int(row.qty or 0) for row in inspection.closing}
    return None


def _build_manufacture_entry(order, totals: dict):
    entry = frappe.get_doc(make_stock_entry(order.name, "Manufacture", order.qty))
    entry.items = [row for row in entry.items if row.s_warehouse]
    _apply_actual_usage(entry.items, order.name)
    for row in entry.items:
        row.set_basic_rate_manually = 0
    cost = _consumed_cost(order.name, entry.items)
    for row in _grade_rows(order, totals, cost):
        entry.append("items", row)
    entry.fg_completed_qty = order.qty
    return entry


def actual_usage(work_order: str) -> dict:
    """Quantities recorded on submitted Job Cards, per item."""
    rows = frappe.db.sql(
        """select c.item_code, sum(c.qty) from `tabJob Card Consumption` c
        join `tabJob Card` j on j.name = c.parent
        where j.work_order = %s and j.docstatus = 1 group by c.item_code""", work_order)
    return {item: flt(qty) for item, qty in rows}


def _apply_actual_usage(rows, work_order: str) -> None:
    usage = actual_usage(work_order)
    for row in rows:
        if row.item_code not in usage:
            continue
        used = usage[row.item_code]
        if used > flt(row.qty) + 0.0001:
            frappe.throw(_("{0}: {1} used but only {2} issued. Issue the extra quantity first.").format(
                row.item_code, used, row.qty))
        row.qty = used
        row.transfer_qty = used * flt(row.conversion_factor or 1)


def transfer_rates(work_order: str) -> dict:
    """Average issue rate per item over the Work Order's material transfers."""
    entries = _transfer_entries(work_order)
    rows = frappe.db.sql(
        """select item_code, sum(basic_amount) / sum(qty) from `tabStock Entry Detail`
        where parent in %s group by item_code""", [entries])
    return {item: flt(rate) for item, rate in rows}


def _consumed_cost(work_order: str, rows) -> float:
    rates = transfer_rates(work_order)
    return sum(flt(row.qty) * rates.get(row.item_code, 0) for row in rows)


def _grade_rows(order, totals: dict, cost: float) -> list:
    grades = {grade.grade_code: grade for grade in SettingsManager.get_grade_configuration()}
    quantities = {code: qty for code, qty in totals.items() if qty}
    weights = {code: 0 if grades[code].is_scrap else flt(grades[code].valuation_pct) / 100
               for code in quantities}
    rates = split_cost(cost, quantities, weights)
    return [_grade_row(order, grades[code], quantities[code], rates[code]) for code in quantities]


def _grade_row(order, grade, qty: int, rate: float) -> dict:
    item = RepackService._derive_item_with_suffix(order.production_item, grade.item_suffix)
    if not frappe.db.exists("Item", item):
        frappe.throw(_("Item {0} for grade {1} does not exist.").format(item, grade.grade_code))
    return {
        "item_code": item, "qty": qty, "uom": frappe.db.get_value("Item", item, "stock_uom"),
        "t_warehouse": grade.target_warehouse or order.fg_warehouse,
        "is_finished_item": 1 if item == order.production_item else 0,
        "is_scrap_item": 0 if item == order.production_item else 1,
        "set_basic_rate_manually": 1, "basic_rate": rate,
    }
