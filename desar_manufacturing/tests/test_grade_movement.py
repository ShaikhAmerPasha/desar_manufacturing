import unittest

from desar_manufacturing.utils.grade_movement import (
    GradeMovementError,
    apply_adjustments,
    apply_movements,
    derive_adjustments,
    total,
)


class TestGradeMovement(unittest.TestCase):
    OPENING = {"A": 2, "B": 3, "C": 0}

    def test_upgrade_and_downgrade(self):
        moves = [
            {"from_grade": "B", "to_grade": "A", "qty": 1},
            {"from_grade": "A", "to_grade": "C", "qty": 1},
        ]
        self.assertEqual(apply_movements(self.OPENING, moves), {"A": 2, "B": 2, "C": 1})

    def test_opening_is_not_modified(self):
        apply_movements(self.OPENING, [{"from_grade": "B", "to_grade": "A", "qty": 1}])
        self.assertEqual(self.OPENING, {"A": 2, "B": 3, "C": 0})

    def test_any_grade_to_any_grade_including_from_scrap(self):
        moves = [{"from_grade": "C", "to_grade": "B", "qty": 1}]
        self.assertEqual(apply_movements({"A": 0, "B": 0, "C": 1}, moves)["B"], 1)

    def test_move_cannot_exceed_available(self):
        with self.assertRaises(GradeMovementError):
            apply_movements(self.OPENING, [{"from_grade": "C", "to_grade": "A", "qty": 1}])

    def test_sequential_moves_use_updated_counts(self):
        moves = [
            {"from_grade": "B", "to_grade": "C", "qty": 3},
            {"from_grade": "B", "to_grade": "A", "qty": 1},
        ]
        with self.assertRaises(GradeMovementError):
            apply_movements(self.OPENING, moves)

    def test_same_grade_rejected(self):
        with self.assertRaises(GradeMovementError):
            apply_movements(self.OPENING, [{"from_grade": "A", "to_grade": "A", "qty": 1}])

    def test_zero_quantity_rejected(self):
        with self.assertRaises(GradeMovementError):
            apply_movements(self.OPENING, [{"from_grade": "A", "to_grade": "B", "qty": 0}])

    def test_process_loss_reduces_total(self):
        after = apply_adjustments({"A": 2, "B": 2, "C": 1}, [{"grade_code": "B", "qty": -1}])
        self.assertEqual(total(after), 4)

    def test_adjustment_cannot_make_grade_negative(self):
        with self.assertRaises(GradeMovementError):
            apply_adjustments({"A": 1}, [{"grade_code": "A", "qty": -2}])

    def test_derive_adjustments_for_final_count(self):
        expected = {"A": 3, "B": 1, "C": 1}
        real = {"A": 3, "B": 2, "C": 1}
        self.assertEqual(derive_adjustments(expected, real), [{"grade_code": "B", "qty": 1}])

    def test_derive_adjustments_empty_when_equal(self):
        self.assertEqual(derive_adjustments({"A": 1}, {"A": 1}), [])
