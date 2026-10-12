import frappe
from frappe.utils import add_to_date, now_datetime

from desar_manufacturing.desar_manufacturing.report.piece_order_cost import piece_order_cost
from desar_manufacturing.services import (
    beam_service, closing_service, grade_item_service, job_card_service, piece_bom_service, piece_order_service,
)
from desar_manufacturing.tests.piece_fixtures import PIECES, PieceBasedTestCase, make_item, receive
from desar_manufacturing.tests.test_beams_and_job_cards import make_operation, make_workstation
from desar_manufacturing.tests.test_roll_inspection import make_inspection, set_closing


class TestMaterialsCostAndGrades(PieceBasedTestCase):
    def setUp(self):
        super().setUp()
        self.tag = frappe.generate_hash(length=5)
        self.weft = make_item("TEST-WEFT", "Kg")
        self.chemical = make_item("TEST-CHEM", "Kg")
        receive(self.weft, self.settings.yarn_warehouse, 500, 8)
        receive(self.chemical, self.settings.chemical_warehouse, 500, 5)
        recipe = frappe.get_doc({"doctype": "Weft Recipe", "recipe_name": "TEST-WEFT",
                                 "weft_items": [{"yarn_item": self.weft, "rate_kg_per_piece": 0.05}]}
                                ).insert(ignore_permissions=True)
        self.design.size_configuration[0].weft_recipe = recipe.name
        self.design.append("chemicals", {"item_code": self.chemical, "qty_per_piece": 0.1})
        self.design.production_process = self.make_process().name
        self.design.save(ignore_permissions=True)

    def make_process(self):
        steps = [("Warping", "Warp Yarn"), ("Weaving", "Weft Yarn"), ("Chemical Finishing", "Chemicals"),
                 ("Boxing", "Packing")]
        rows = [{"sequence": number, "operation": make_operation(f"TEST-{name}"),
                 "workstation": make_workstation(f"TEST-WS-{name}-{self.tag}"), "time_in_mins": 60, "material_group": group}
                for number, (name, group) in enumerate(steps, start=1)]
        return frappe.get_doc({"doctype": "Production Process",
                               "process_name": "TEST-%s" % frappe.generate_hash(length=6), "steps": rows}
                              ).insert(ignore_permissions=True)

    def test_bom_rows_are_tagged_to_the_operation_that_uses_them(self):
        bom = frappe.get_doc("BOM", piece_bom_service.create_bom(self.design.name, "60"))
        operation_of = {row.item_code: row.operation for row in bom.items}
        self.assertEqual(operation_of, {
            self.yarn: "TEST-Warping", self.weft: "TEST-Weaving",
            self.chemical: "TEST-Chemical Finishing", self.box: "TEST-Boxing"})
        quantities = {row.item_code: row.qty for row in bom.items}
        self.assertEqual((quantities[self.weft], quantities[self.chemical]), (0.05, 0.1))

    def test_weft_row_without_rate_is_rejected(self):
        recipe = frappe.get_doc("Weft Recipe", self.design.size_configuration[0].weft_recipe)
        recipe.weft_items[0].rate_kg_per_piece = 0
        recipe.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            piece_bom_service.create_bom(self.design.name, "60")

    def test_grade_items_are_created_once_and_priced_from_grade_a(self):
        for grade in "BC":
            if frappe.db.exists("Item", f"TEST-SHM-60-{grade}"):
                frappe.delete_doc("Item", f"TEST-SHM-60-{grade}", force=True)
        created = grade_item_service.ensure_grade_items("TEST-SHM-60-A")
        self.assertEqual(sorted(created), ["TEST-SHM-60-B", "TEST-SHM-60-C"])
        self.assertEqual(grade_item_service.ensure_grade_items("TEST-SHM-60-A"), [])
        price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1})
        frappe.get_doc({"doctype": "Item Price", "item_code": "TEST-SHM-60-A", "price_list": price_list,
                        "price_list_rate": 100, "selling": 1}).insert(ignore_permissions=True)
        grade_item_service.sync_grade_prices("TEST-SHM-60-A")
        rate = frappe.db.get_value("Item Price", {"item_code": "TEST-SHM-60-B", "price_list": price_list},
                                   "price_list_rate")
        self.assertAlmostEqual(rate, 60)

    def run_to_close(self, consumption: dict = None):
        order = self.make_order()
        beam, = beam_service.create_beams(order, [{"length_m": 1000, "workstation": make_workstation(f"TEST-L-{self.tag}"),
                                                   "planned_pieces": PIECES}])
        piece_order_service.issue_materials(order)
        job_card_service.create_beam_job_cards(order)
        for roll in beam_service.create_rolls(beam, 1):
            self.inspect(roll, {"A": 90, "B": 6, "C": 4})
        self.complete_job_cards(order, consumption or {})
        return order

    def inspect(self, roll: str, counts: dict) -> None:
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

    def complete_job_cards(self, order: str, consumption: dict) -> None:
        names = frappe.get_all("Job Card", filters={"work_order": order}, pluck="name",
                               order_by="creation asc, name asc")
        for index, name in enumerate(names):
            card = frappe.get_doc("Job Card", name)
            start = add_to_date(now_datetime(), hours=-3 * (len(names) - index))
            card.append("time_logs", {"from_time": start, "to_time": add_to_date(start, hours=1),
                                      "completed_qty": card.for_quantity})
            for item, qty in consumption.get(card.operation, {}).items():
                card.append("custom_actual_consumption", {"item_code": item, "qty": qty})
            card.save(ignore_permissions=True)
            card.submit()

    def consumed(self, entry_name: str) -> dict:
        entry = frappe.get_doc("Stock Entry", entry_name)
        return {row.item_code: row.qty for row in entry.items if row.s_warehouse}

    def test_close_without_recorded_usage_consumes_the_standard_quantities(self):
        entry = closing_service.close_order(self.run_to_close())
        self.assertEqual(self.consumed(entry), {self.yarn: 20, self.weft: 5, self.chemical: 10, self.box: 100})

    def test_close_consumes_recorded_usage_and_values_output_on_it(self):
        usage = {"TEST-Chemical Finishing": {self.chemical: 7}}
        entry_name = closing_service.close_order(self.run_to_close(usage))
        self.assertEqual(self.consumed(entry_name)[self.chemical], 7)
        entry = frappe.get_doc("Stock Entry", entry_name)
        value = sum(row.qty * row.basic_rate for row in entry.items if row.t_warehouse)
        self.assertAlmostEqual(value, 20 * 10 + 5 * 8 + 7 * 5 + 100 * 2, places=1)

    def test_usage_above_issued_quantity_is_rejected(self):
        usage = {"TEST-Chemical Finishing": {self.chemical: 11}}
        with self.assertRaises(frappe.ValidationError):
            closing_service.close_order(self.run_to_close(usage))

    def test_cost_report_splits_material_and_labour_by_operation(self):
        order = self.run_to_close()
        columns, data = piece_order_cost.execute({"work_order": order})
        by_operation = {row["operation"]: row for row in data}
        self.assertAlmostEqual(by_operation["TEST-Warping"]["material_cost"], 20 * 10)
        self.assertAlmostEqual(by_operation["TEST-Weaving"]["material_cost"], 5 * 8)
        self.assertAlmostEqual(by_operation["TEST-Chemical Finishing"]["material_cost"], 10 * 5)
        self.assertAlmostEqual(by_operation["TEST-Boxing"]["material_cost"], 100 * 2)
        self.assertAlmostEqual(by_operation["TEST-Boxing"]["labour_cost"], 10)
        self.assertEqual(data[-1]["operation"], "Total")
