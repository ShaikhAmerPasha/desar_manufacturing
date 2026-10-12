"""Work Order for one Design Master size, and the single material issue."""
import frappe
from frappe import _
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.services import piece_bom_service


def create_work_order(design_master: str, size_code: str, qty: int, sales_order: str = None) -> str:
    bom = piece_bom_service.create_bom(design_master, size_code)
    item = frappe.db.get_value("BOM", bom, "item")
    work_order = frappe.get_doc({
        "doctype": "Work Order", "production_item": item, "bom_no": bom, "qty": qty,
        "company": SettingsManager.get_company(), "sales_order": sales_order,
        "wip_warehouse": SettingsManager.get_warehouse("piece_wip_warehouse"),
        "fg_warehouse": SettingsManager.get_warehouse("fg_grade_a_warehouse"),
        "scrap_warehouse": SettingsManager.get_warehouse("scrap_warehouse"),
        "custom_design_master": design_master, "use_multi_level_bom": 0,
    })
    work_order.insert(ignore_permissions=True)
    work_order.submit()
    return work_order.name


def issue_materials(work_order: str) -> str:
    """Create and submit the one Material Transfer for the whole Work Order."""
    if frappe.db.exists("Stock Entry", {"work_order": work_order, "docstatus": 1,
                                         "purpose": "Material Transfer for Manufacture"}):
        frappe.throw(_("Materials were already issued for {0}.").format(work_order))
    work_order_doc = frappe.get_doc("Work Order", work_order)
    entry = frappe.get_doc(make_stock_entry(work_order, "Material Transfer for Manufacture",
                                            work_order_doc.qty))
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry.name
