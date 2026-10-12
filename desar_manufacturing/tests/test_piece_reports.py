import frappe

from desar_manufacturing.desar_manufacturing.report.grade_movements import grade_movements
from desar_manufacturing.desar_manufacturing.report.piece_order_yield import piece_order_yield
from desar_manufacturing.desar_manufacturing.report.piece_wip import piece_wip
from desar_manufacturing.desar_manufacturing.report.process_loss_by_reason import process_loss_by_reason
from desar_manufacturing.desar_manufacturing.report.sales_order_production import sales_order_production
from desar_manufacturing.services import beam_service
from desar_manufacturing.tests.piece_fixtures import PIECES, PieceBasedTestCase
from desar_manufacturing.tests.test_roll_inspection import make_inspection, set_closing


class TestPieceReports(PieceBasedTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.make_order()
        beam, = beam_service.create_beams(self.order, [{"length_m": 900, "planned_pieces": PIECES}])
        self.first, self.second = beam_service.create_rolls(beam, 2)
        self.inspect_first_roll()
        self.inspect_second_roll()

    def submit(self, roll: str, stage: str, closing: dict = None, movements=(), adjustments=()):
        doc = make_inspection(roll, stage)
        doc.insert(ignore_permissions=True)
        for row in movements:
            doc.append("movements", row)
        for row in adjustments:
            doc.append("adjustments", row)
        if closing:
            set_closing(doc, closing)
        doc.save(ignore_permissions=True)
        doc.submit()

    def inspect_first_roll(self):
        self.submit(self.first, "Gray", {"A": 50, "B": 6, "C": 4})
        self.submit(self.first, "Finishing",
                    movements=[{"from_grade": "B", "to_grade": "A", "qty": 2, "reason": "Chemical finishing improved"}],
                    adjustments=[{"grade_code": "B", "qty": -1, "reason": "Shrinkage"}])
        final = make_inspection(self.first, "Final")
        final.insert(ignore_permissions=True)
        set_closing(final, {"A": 52, "B": 4, "C": 4})
        final.save(ignore_permissions=True)
        final.adjustments[0].reason = "Cutting gave extra piece"
        final.save(ignore_permissions=True)
        final.submit()

    def inspect_second_roll(self):
        self.submit(self.second, "Gray", {"A": 30, "B": 5, "C": 5})
        self.submit(self.second, "Finishing")
        self.submit(self.second, "Final", {"A": 30, "B": 5, "C": 5})

    def test_yield_by_work_order(self):
        _columns, data = piece_order_yield.execute({"work_order": self.order})
        row, = data
        self.assertEqual((row["key"], row["total"], row["sellable"], row["scrap"]), (self.order, 100, 91, 9))
        self.assertEqual((row["loss"], row["gain"]), (1, 1))
        self.assertAlmostEqual(row["yield_pct"], 91)
        self.assertAlmostEqual(row["scrap_pct"], 9)

    def test_yield_by_roll(self):
        _columns, data = piece_order_yield.execute({"work_order": self.order, "group_by": "Roll"})
        by_roll = {row["key"]: row["total"] for row in data}
        self.assertEqual(by_roll, {self.first: 60, self.second: 40})

    def test_grade_movements_report_marks_upgrades(self):
        _columns, data = grade_movements.execute({"work_order": self.order})
        row, = data
        self.assertEqual((row["stage"], row["from_grade"], row["to_grade"], row["qty"]), ("Finishing", "B", "A", 2))
        self.assertEqual(row["direction"], "Upgrade")

    def test_process_loss_and_gain_by_reason(self):
        _columns, data = process_loss_by_reason.execute({"work_order": self.order})
        found = {(row["kind"], row["reason"]): row["qty"] for row in data}
        self.assertEqual(found, {("Process loss", "Shrinkage"): 1, ("Count gain", "Cutting gave extra piece"): 1})

    def test_wip_counts_rolls_by_last_inspection_stage(self):
        _columns, data = piece_wip.execute()
        mine = {row["position"]: row["count"] for row in data if row["kind"] == "Rolls"}
        self.assertGreaterEqual(mine["After Final inspection"], 2)

    def test_sales_order_summary_lists_work_orders(self):
        sales_order = frappe.db.get_value("Sales Order", {"docstatus": 1})
        if not sales_order:
            self.skipTest("No Sales Order on this site to link.")
        frappe.db.set_value("Work Order", self.order, "sales_order", sales_order)
        _columns, data = sales_order_production.execute({"sales_order": sales_order})
        row = next(r for r in data if r["work_order"] == self.order)
        self.assertEqual((row["rolls"], row["beams"], row["finished"], row["sellable"], row["scrap"]),
                         (2, 1, 100, 91, 9))
