"""One BOM per Design Master size. Quantities are per finished piece."""
import frappe
from frappe import _
from frappe.utils import flt

from desar_manufacturing.config.settings_manager import SettingsManager

WARP_YARN, WEFT_YARN, CHEMICALS, PACKING = "Warp Yarn", "Weft Yarn", "Chemicals", "Packing"


def create_bom(design_master: str, size_code: str) -> str:
    design = frappe.get_doc("Design Master", design_master)
    size = _size_row(design, size_code)
    existing = frappe.db.get_value(
        "BOM",
        {"item": size.finished_item_a, "custom_design_master": design.name, "docstatus": 1, "is_active": 1},
    )
    if existing:
        return existing
    steps = _steps(design)
    operations = [{"operation": step.operation, "workstation": step.workstation,
                   "time_in_mins": step.time_in_mins} for step in steps]
    bom = frappe.get_doc({
        "doctype": "BOM", "item": size.finished_item_a, "quantity": 1,
        "is_default": 1, "is_active": 1, "with_operations": 1 if operations else 0,
        "operations": operations, "company": SettingsManager.get_company(),
        "custom_design_master": design.name, "custom_design_no": design.design_no,
        "custom_article_name": design.article_name,
        "items": _material_rows(design, size, {s.material_group: s.operation for s in steps if s.material_group}),
    })
    bom.insert(ignore_permissions=True)
    bom.submit()
    return bom.name


def _steps(design) -> list:
    if not design.production_process:
        return []
    steps = frappe.get_doc("Production Process", design.production_process).steps
    return sorted(steps, key=lambda step: step.sequence)


def _size_row(design, size_code: str):
    for row in design.size_configuration:
        if row.size_code == size_code:
            if not row.finished_item_a:
                frappe.throw(_("Size {0} has no Grade A finished item.").format(size_code))
            return row
    frappe.throw(_("Design {0} has no size {1}.").format(design.name, size_code))


def _material_rows(design, size, operation_of_group: dict) -> list:
    groups = {
        WARP_YARN: _warp_rows(size), WEFT_YARN: _weft_rows(size),
        CHEMICALS: _chemical_rows(design, size), PACKING: _packing_rows(design),
    }
    rows = []
    for group, group_rows in groups.items():
        for row in group_rows:
            if operation_of_group.get(group):
                row["operation"] = operation_of_group[group]
            rows.append(row)
    return rows


def _warp_rows(size) -> list:
    if not size.warp_recipe:
        frappe.throw(_("Size {0} has no Warp Recipe.").format(size.size_code))
    recipe = frappe.get_doc("Warp Recipe", size.warp_recipe)
    warehouse = SettingsManager.get_warehouse("yarn_warehouse")
    return [_bom_row(item.yarn_item, _warp_kilograms_per_piece(item, recipe), warehouse)
            for item in recipe.yarn_items]


def _warp_kilograms_per_piece(item, recipe) -> float:
    if flt(item.rate_kg_per_piece):
        return flt(item.rate_kg_per_piece)
    if flt(item.qty_kg) and flt(recipe.planned_qty):
        return flt(item.qty_kg) / flt(recipe.planned_qty)
    frappe.throw(_("Warp Recipe {0}: {1} needs a Rate (Kg/Piece).").format(recipe.name, item.yarn_item))


def _weft_rows(size) -> list:
    if not size.weft_recipe:
        return []
    recipe = frappe.get_doc("Weft Recipe", size.weft_recipe)
    warehouse = SettingsManager.get_warehouse("yarn_warehouse")
    rows = []
    for item in recipe.weft_items:
        if not flt(item.rate_kg_per_piece):
            frappe.throw(_("Weft Recipe {0}: {1} needs a Rate (Kg/Piece).").format(recipe.name, item.yarn_item))
        rows.append(_bom_row(item.yarn_item, flt(item.rate_kg_per_piece), warehouse))
    return rows


def _chemical_rows(design, size) -> list:
    chemicals = [row for row in design.chemicals if not row.size_code or row.size_code == size.size_code]
    if not chemicals:
        return []
    warehouse = SettingsManager.get_warehouse("chemical_warehouse")
    return [_bom_row(row.item_code, flt(row.qty_per_piece), warehouse) for row in chemicals]


def _packing_rows(design) -> list:
    items = [code for code in (design.branded_box_item, design.label_item, design.sticker_item) if code]
    if not items:
        return []
    warehouse = SettingsManager.get_warehouse("accessories_warehouse")
    return [_bom_row(code, 1, warehouse) for code in items]


def _bom_row(item_code: str, qty: float, warehouse: str) -> dict:
    return {"item_code": item_code, "qty": qty, "source_warehouse": warehouse,
            "uom": frappe.db.get_value("Item", item_code, "stock_uom")}
