"""One BOM per Design Master size. Quantities are per finished piece."""
import frappe
from frappe import _
from frappe.utils import flt

from desar_manufacturing.config.settings_manager import SettingsManager


def create_bom(design_master: str, size_code: str) -> str:
    design = frappe.get_doc("Design Master", design_master)
    size = _size_row(design, size_code)
    operations = _operation_rows(design)
    existing = frappe.db.get_value(
        "BOM",
        {"item": size.finished_item_a, "custom_design_master": design.name, "docstatus": 1, "is_active": 1},
    )
    if existing:
        return existing
    bom = frappe.get_doc({
        "doctype": "BOM", "item": size.finished_item_a, "quantity": 1,
        "is_default": 1, "is_active": 1, "with_operations": 1 if operations else 0,
        "operations": operations,
        "company": SettingsManager.get_company(),
        "custom_design_master": design.name, "custom_design_no": design.design_no,
        "custom_article_name": design.article_name,
        "items": _yarn_rows(size) + _accessory_rows(design),
    })
    bom.insert(ignore_permissions=True)
    bom.submit()
    return bom.name


def _size_row(design, size_code: str):
    for row in design.size_configuration:
        if row.size_code == size_code:
            if not row.finished_item_a:
                frappe.throw(_("Size {0} has no Grade A finished item.").format(size_code))
            return row
    frappe.throw(_("Design {0} has no size {1}.").format(design.name, size_code))


def _yarn_rows(size) -> list:
    if not size.warp_recipe:
        frappe.throw(_("Size {0} has no Warp Recipe.").format(size.size_code))
    recipe = frappe.get_doc("Warp Recipe", size.warp_recipe)
    warehouse = SettingsManager.get_warehouse("yarn_warehouse")
    return [_bom_row(item.yarn_item, _kilograms_per_piece(item, recipe), warehouse)
            for item in recipe.yarn_items]


def _kilograms_per_piece(item, recipe) -> float:
    if flt(item.rate_kg_per_piece):
        return flt(item.rate_kg_per_piece)
    if flt(item.qty_kg) and flt(recipe.planned_qty):
        return flt(item.qty_kg) / flt(recipe.planned_qty)
    frappe.throw(_("Warp Recipe {0}: {1} needs a Rate (Kg/Piece).").format(recipe.name, item.yarn_item))


def _accessory_rows(design) -> list:
    warehouse = SettingsManager.get_warehouse("accessories_warehouse")
    items = [design.branded_box_item, design.label_item, design.sticker_item]
    return [_bom_row(code, 1, warehouse) for code in items if code]


def _bom_row(item_code: str, qty: float, warehouse: str) -> dict:
    return {"item_code": item_code, "qty": qty, "source_warehouse": warehouse,
            "uom": frappe.db.get_value("Item", item_code, "stock_uom")}


def _operation_rows(design) -> list:
    if not design.production_process:
        return []
    steps = frappe.get_doc("Production Process", design.production_process).steps
    return [{"operation": step.operation, "workstation": step.workstation,
             "time_in_mins": step.time_in_mins} for step in sorted(steps, key=lambda step: step.sequence)]
