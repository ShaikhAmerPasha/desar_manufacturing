import frappe
from frappe.tests.utils import FrappeTestCase

from desar_manufacturing.install.defaults import seed_inspection_defaults
from desar_manufacturing.services import piece_order_service

PIECES = 100


def make_item(code: str, uom: str = "Nos") -> str:
    if not frappe.db.exists("Item", code):
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "All Item Groups",
                        "stock_uom": uom, "is_stock_item": 1,
                        "include_item_in_manufacturing": 1}).insert(ignore_permissions=True)
    return code


def receive(item: str, warehouse: str, qty: float, rate: float) -> None:
    entry = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
        "company": frappe.db.get_single_value("DESAR Settings", "default_company"),
        "items": [{"item_code": item, "t_warehouse": warehouse, "qty": qty, "basic_rate": rate}],
    })
    entry.insert(ignore_permissions=True)
    entry.submit()


class PieceBasedTestCase(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seed_inspection_defaults()
        settings = frappe.get_single("DESAR Settings")
        for row in settings.grade_configuration:
            row.is_scrap = 1 if row.grade_code == "C" else 0
            row.valuation_pct = {"A": 100, "B": 60, "C": 0}.get(row.grade_code, row.valuation_pct)
        settings.piece_wip_warehouse = settings.piece_wip_warehouse or settings.cutting_packing_warehouse
        settings.save(ignore_permissions=True)
        cls.settings = settings

    def setUp(self):
        for grade in ("A", "B", "C"):
            make_item(f"TEST-SHM-60-{grade}")
        self.yarn, self.box = make_item("TEST-YARN", "Kg"), make_item("TEST-BOX")
        receive(self.yarn, self.settings.yarn_warehouse, 1000, 10)
        receive(self.box, self.settings.accessories_warehouse, 1000, 2)
        recipe = frappe.get_doc({"doctype": "Warp Recipe", "recipe_name": "TEST", "planned_qty": PIECES,
                                 "yarn_items": [{"yarn_item": self.yarn, "rate_kg_per_piece": 0.2}]})
        recipe.insert(ignore_permissions=True)
        self.design = frappe.get_doc({
            "doctype": "Design Master", "design_no": "TEST-563", "article_name": "Test", "warp_recipe": recipe.name,
            "branded_box_item": self.box, "process_version": "Piece Based",
            "size_configuration": [{"size_code": "60", "warp_recipe": recipe.name,
                                    "finished_item_a": "TEST-SHM-60-A", "pieces_per_roll": 50}],
        }).insert(ignore_permissions=True)

    def make_order(self) -> str:
        return piece_order_service.create_work_order(self.design.name, "60", PIECES)
