import frappe

from desar_manufacturing.services import closing_service, piece_bom_service, piece_order_service
from desar_manufacturing.tests.piece_fixtures import PIECES, PieceBasedTestCase
from desar_manufacturing.tests.test_roll_inspection import make_inspection, set_closing


class TestPieceBasedCycle(PieceBasedTestCase):
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

    def test_material_flagged_out_of_manufacturing_on_the_item_is_still_issued(self):
        frappe.db.set_value("Item", self.box, "include_item_in_manufacturing", 0)
        order = self.make_order()
        entry = frappe.get_doc("Stock Entry", piece_order_service.issue_materials(order))
        self.assertIn(self.box, [row.item_code for row in entry.items])
