import frappe
from frappe.tests.utils import FrappeTestCase

from desar_manufacturing.desar_manufacturing.report.grade_yield_analysis import grade_yield_analysis
from desar_manufacturing.desar_manufacturing.report.roll_life_tracker import roll_life_tracker


class TestGradeReports(FrappeTestCase):
    def setUp(self):
        self.design_master = _make_design_master()
        self.roll_ticket = _make_roll_ticket(self.design_master)

    def test_grade_yield_analysis_reads_stage_grades(self):
        rows = grade_yield_analysis.get_data()
        row = next(r for r in rows if r.article == "Test Article")
        self.assertEqual(row.grade_a, 45)
        self.assertEqual(row.grade_b, 4)
        self.assertEqual(row.grade_c, 1)

    def test_roll_life_tracker_reads_stage_grades(self):
        rows = roll_life_tracker.get_data({"article_name": "Test Article"})
        row = next(r for r in rows if r["roll_ticket"] == self.roll_ticket.name)
        self.assertEqual(row["grey_a"], 42)
        self.assertEqual(row["cut_a"], 45)
        self.assertEqual(row["cut_total"], 50)


def _make_design_master():
    doc = frappe.get_doc({
        "doctype": "Design Master",
        "design_no": "TEST-GRADE-REPORTS",
        "article_name": "Test Article",
        "stage_configuration": [
            {"stage_seq": 1, "stage_name": "Test Weaving", "output_item": "Grey Roll", "output_qty": 1},
            {"stage_seq": 2, "stage_name": "Test Packing", "output_item": "Grey Roll", "output_qty": 1, "is_final_stage": 1},
        ],
    })
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc


def _make_roll_ticket(design_master):
    doc = frappe.get_doc({
        "doctype": "Roll Ticket",
        "design_no": design_master.design_no,
        "article_name": design_master.article_name,
        "roll_status": "Completed",
        "stage_grades": [
            {"stage_seq": 1, "stage_name": "Test Weaving", "grade_code": "A", "qty": 42},
            {"stage_seq": 1, "stage_name": "Test Weaving", "grade_code": "B", "qty": 6},
            {"stage_seq": 1, "stage_name": "Test Weaving", "grade_code": "C", "qty": 2},
            {"stage_seq": 2, "stage_name": "Test Packing", "grade_code": "A", "qty": 45},
            {"stage_seq": 2, "stage_name": "Test Packing", "grade_code": "B", "qty": 4},
            {"stage_seq": 2, "stage_name": "Test Packing", "grade_code": "C", "qty": 1},
        ],
    })
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc
