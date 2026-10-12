"""Grade items (A, B, C) of a finished product and their selling prices."""
import frappe
from frappe.utils import flt

from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.services.repack_service import RepackService


def grade_items(item_a: str) -> dict:
    """{grade_code: item_code} derived from the Grade A item by the configured suffix."""
    return {grade.grade_code: RepackService._derive_item_with_suffix(item_a, grade.item_suffix)
            for grade in SettingsManager.get_grade_configuration()}


def ensure_grade_items(item_a: str) -> list:
    """Create any missing grade item as a plain stock item like Grade A. Returns created codes."""
    template = frappe.get_doc("Item", item_a)
    created = []
    for grade in SettingsManager.get_grade_configuration():
        code = RepackService._derive_item_with_suffix(item_a, grade.item_suffix)
        if code == item_a or frappe.db.exists("Item", code):
            continue
        frappe.get_doc({
            "doctype": "Item", "item_code": code, "item_name": f"{template.item_name} {grade.grade_code}",
            "item_group": template.item_group, "stock_uom": template.stock_uom, "is_stock_item": 1,
            "include_item_in_manufacturing": 1, "is_sales_item": 0 if grade.is_scrap else 1,
        }).insert(ignore_permissions=True)
        created.append(code)
    return created


def sync_grade_prices(item_a: str) -> list:
    """Price each sellable grade at its valuation percent of the Grade A selling price."""
    items = grade_items(item_a)
    updated = []
    prices = frappe.get_all("Item Price", filters={"item_code": item_a, "selling": 1},
                            fields=["price_list", "price_list_rate", "currency"])
    for grade in SettingsManager.get_grade_configuration():
        if grade.is_scrap or items[grade.grade_code] == item_a:
            continue
        for price in prices:
            _set_price(items[grade.grade_code], price, flt(price.price_list_rate) * flt(grade.valuation_pct) / 100)
            updated.append((items[grade.grade_code], price.price_list))
    return updated


def _set_price(item_code: str, source, rate: float) -> None:
    name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": source.price_list,
                                              "selling": 1})
    if name:
        frappe.db.set_value("Item Price", name, "price_list_rate", rate)
        return
    frappe.get_doc({"doctype": "Item Price", "item_code": item_code, "price_list": source.price_list,
                    "price_list_rate": rate, "currency": source.currency, "selling": 1}
                   ).insert(ignore_permissions=True)
