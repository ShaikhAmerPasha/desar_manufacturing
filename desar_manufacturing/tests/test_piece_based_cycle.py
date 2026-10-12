import frappe
from frappe.tests.utils import FrappeTestCase

from desar_manufacturing.install.defaults import seed_inspection_defaults
from desar_manufacturing.services import closing_service, piece_bom_service, piece_order_service
from desar_manufacturing.tests.test_roll_inspection import make_inspection, set_closing

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


class TestPieceBasedCycle(FrappeTestCase):
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

    def make_roll(self, order: str, counts: dict) -> str:
        roll = frappe.get_doc({"doctype": "Roll Ticket", "design_no": "TEST-563", "size": "60",
                               "work_order": order}).insert(ignore_permissions=True).name
        gray = make_inspection(roll, "Gray")
        gray.insert(ignore_permissions=True)
        set_closing(gray, counts)
        gray.save(ignore_permissions=True)
        gray.submit()
        make_inspection(roll, "Finishing").insert(ignore_permissions=True).submit()
        final = make_inspection(roll, "Final")
        final.insert(ignore_permissions=True)
        set_closing(final, counts)
        final.save(ignore_permissions=True)
        final.submit()
        return roll

    def test_bom_holds_per_piece_materials_and_no_roll_items(self):
        bom = frappe.get_doc("BOM", piece_bom_service.create_bom(self.design.name, "60"))
        rows = {row.item_code: row.qty for row in bom.items}
        self.assertEqual(rows, {self.yarn: 0.2, self.box: 1})
        self.assertEqual(bom.quantity, 1)

    def test_work_order_of_100_pieces_needs_100_boxes_and_20_kg_yarn(self):
        order = frappe.get_doc("Work Order", self.make_order())
        required = {row.item_code: row.required_qty for row in order.required_items}
        self.assertEqual(required[self.box], PIECES)
        self.assertAlmostEqual(required[self.yarn], 20)

    def test_issue_materials_only_once(self):
        order = self.make_order()
        piece_order_service.issue_materials(order)
        with self.assertRaises(frappe.ValidationError):
            piece_order_service.issue_materials(order)

    def test_close_requires_issue_and_final_inspections(self):
        order = self.make_order()
        with self.assertRaises(frappe.ValidationError):
            closing_service.close_order(order)
        piece_order_service.issue_materials(order)
        with self.assertRaises(frappe.ValidationError):
            closing_service.close_order(order)

    def test_full_cycle_posts_two_stock_entries_with_graded_output(self):
        order = self.make_order()
        piece_order_service.issue_materials(order)
        self.make_roll(order, {"A": 40, "B": 6, "C": 4})
        self.make_roll(order, {"A": 40, "B": 4, "C": 6})
        entry = frappe.get_doc("Stock Entry", closing_service.close_order(order))
        entries = frappe.get_all("Stock Entry", {"work_order": order, "docstatus": 1}, pluck="purpose")
        self.assertEqual(sorted(entries), ["Manufacture", "Material Transfer for Manufacture"])
        produced = {row.item_code: row.qty for row in entry.items if row.t_warehouse}
        self.assertEqual(produced, {"TEST-SHM-60-A": 80, "TEST-SHM-60-B": 10, "TEST-SHM-60-C": 10})
        rate = {row.item_code: row.basic_rate for row in entry.items if row.t_warehouse}
        self.assertAlmostEqual(rate["TEST-SHM-60-B"], 0.6 * rate["TEST-SHM-60-A"], places=2)
        self.assertEqual(rate["TEST-SHM-60-C"], 0)
        value = sum(row.qty * row.basic_rate for row in entry.items if row.t_warehouse)
        self.assertAlmostEqual(value, 20 * 10 + PIECES * 2, places=1)
        self.assertEqual(frappe.db.get_value("Work Order", order, "status"), "Completed")
