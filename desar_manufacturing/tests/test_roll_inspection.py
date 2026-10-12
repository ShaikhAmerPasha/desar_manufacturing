import frappe
from frappe.tests.utils import FrappeTestCase

from desar_manufacturing.install.defaults import seed_inspection_defaults


def make_roll_ticket() -> str:
    return frappe.get_doc({"doctype": "Roll Ticket", "design_no": "TEST-563", "size": "60"}).insert(
        ignore_permissions=True).name


def make_inspection(roll_ticket: str, stage: str, **values):
    return frappe.get_doc({"doctype": "Roll Inspection", "roll_ticket": roll_ticket, "stage": stage, **values})


def set_closing(doc, counts: dict) -> None:
    doc.set("closing", [])
    for grade, qty in counts.items():
        doc.append("closing", {"grade_code": grade, "qty": qty})


class TestRollInspection(FrappeTestCase):
    def setUp(self):
        seed_inspection_defaults()
        self.roll = make_roll_ticket()

    def submit_gray(self, counts=None):
        doc = make_inspection(self.roll, "Gray")
        doc.insert(ignore_permissions=True)
        set_closing(doc, counts or {"A": 2, "B": 3, "C": 0})
        doc.save(ignore_permissions=True)
        doc.submit()
        return doc

    def start_finishing(self, moves, losses=None):
        doc = make_inspection(self.roll, "Finishing")
        doc.insert(ignore_permissions=True)
        for move in moves:
            doc.append("movements", move)
        for loss in losses or []:
            doc.append("adjustments", loss)
        doc.save(ignore_permissions=True)
        return doc

    def closing_of(self, doc) -> dict:
        return {row.grade_code: row.qty for row in doc.closing}

    def test_gray_takes_counts_and_publishes_to_roll_ticket(self):
        doc = self.submit_gray()
        self.assertEqual(doc.total_pieces, 5)
        ticket = frappe.get_doc("Roll Ticket", self.roll)
        self.assertEqual({r.grade_code: r.qty for r in ticket.stage_grades if r.stage_name == "Gray"},
                         {"A": 2, "B": 3, "C": 0})

    def test_finishing_opening_is_fetched_and_moves_are_computed(self):
        self.submit_gray()
        doc = self.start_finishing([
            {"from_grade": "B", "to_grade": "A", "qty": 1, "reason": "Chemical finishing improved"},
            {"from_grade": "A", "to_grade": "C", "qty": 1, "reason": "Stain or burn"},
        ])
        self.assertEqual({r.grade_code: r.qty for r in doc.opening}, {"A": 2, "B": 3, "C": 0})
        self.assertEqual(self.closing_of(doc), {"A": 2, "B": 2, "C": 1})

    def test_finishing_requires_previous_inspection(self):
        with self.assertRaises(frappe.ValidationError):
            self.start_finishing([])

    def test_move_more_than_available_is_rejected(self):
        self.submit_gray()
        with self.assertRaises(frappe.ValidationError):
            self.start_finishing([{"from_grade": "C", "to_grade": "A", "qty": 1,
                                   "reason": "Chemical finishing improved"}])

    def test_movement_requires_a_reason(self):
        self.submit_gray()
        with self.assertRaises(frappe.MandatoryError):
            self.start_finishing([{"from_grade": "B", "to_grade": "A", "qty": 1}])

    def test_final_difference_requires_a_reason_to_submit(self):
        self.submit_gray()
        self.start_finishing([]).submit()
        final = make_inspection(self.roll, "Final")
        final.insert(ignore_permissions=True)
        set_closing(final, {"A": 2, "B": 4, "C": 0})
        final.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            final.submit()

    def test_reason_kind_must_match(self):
        self.submit_gray()
        doc = self.start_finishing([{"from_grade": "B", "to_grade": "A", "qty": 1, "reason": "Shrinkage"}])
        with self.assertRaises(frappe.ValidationError):
            doc.submit()

    def test_process_loss_reduces_closing_total(self):
        self.submit_gray()
        doc = self.start_finishing([], [{"grade_code": "B", "qty": -1, "reason": "Shrinkage"}])
        self.assertEqual(self.closing_of(doc), {"A": 2, "B": 2, "C": 0})
        self.assertEqual(doc.total_pieces, 4)

    def test_final_derives_difference_rows_from_real_counts(self):
        self.submit_gray()
        finishing = self.start_finishing([])
        finishing.submit()
        final = make_inspection(self.roll, "Final")
        final.insert(ignore_permissions=True)
        set_closing(final, {"A": 2, "B": 4, "C": 0})
        final.save(ignore_permissions=True)
        self.assertEqual([(r.grade_code, r.qty) for r in final.adjustments], [("B", 1)])

    def test_second_submitted_inspection_for_same_stage_is_rejected(self):
        self.submit_gray()
        duplicate = make_inspection(self.roll, "Gray")
        duplicate.insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            duplicate.submit()

    def test_cancel_blocked_while_later_inspection_is_submitted(self):
        gray = self.submit_gray()
        self.start_finishing([]).submit()
        with self.assertRaises(frappe.ValidationError):
            gray.cancel()

    def test_cancel_removes_rows_from_roll_ticket(self):
        gray = self.submit_gray()
        gray.cancel()
        ticket = frappe.get_doc("Roll Ticket", self.roll)
        self.assertFalse([r for r in ticket.stage_grades if r.stage_name == "Gray"])


class TestGradeRowsApi(FrappeTestCase):
    def setUp(self):
        seed_inspection_defaults()
        self.roll = make_roll_ticket()

    def test_count_stage_returns_empty_opening_and_zero_closing(self):
        from desar_manufacturing.services.inspection_service import get_grade_rows
        rows = get_grade_rows(self.roll, "Gray")
        self.assertEqual(rows["opening"], [])
        self.assertEqual([r["qty"] for r in rows["closing"]], [0, 0, 0])

    def test_movement_stage_without_previous_inspection_is_rejected(self):
        from desar_manufacturing.services.inspection_service import get_grade_rows
        with self.assertRaises(frappe.ValidationError):
            get_grade_rows(self.roll, "Finishing")

    def test_grades_are_listed_best_first(self):
        from desar_manufacturing.services.inspection_service import configured_grades
        self.assertEqual([code for code, _label in configured_grades()][:1], ["A"])
