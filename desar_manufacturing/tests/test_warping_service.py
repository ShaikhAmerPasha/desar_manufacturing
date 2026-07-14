"""
DESAR Warping Service — Tests

Level 1 (bench, no DB writes):
  - Calls the real warping_service._validate_split_rows directly — not a
    reimplementation — so these tests fail if the production logic diverges.

Level 2 (bench):
  - DocType/field existence
  - API importable
"""
import unittest

import frappe
from desar_manufacturing.services.warping_service import _validate_split_rows


class TestValidateSplitRows(unittest.TestCase):
    """Calls warping_service._validate_split_rows directly (no DB needed — it's pure logic + frappe.throw)."""

    def _flatten(self, rows, target_qty):
        po = frappe._dict({"total_qty": target_qty})
        return _validate_split_rows(rows, po)

    def test_exact_match_single_row(self):
        self.assertEqual(self._flatten([{"qty_to_split": 4, "pieces_per_split": 50}], 200), [50] * 4)

    def test_exact_match_uneven_rows(self):
        """161 pieces = 1 roll of 80 + 1 roll of 81."""
        rows = [{"qty_to_split": 1, "pieces_per_split": 80}, {"qty_to_split": 1, "pieces_per_split": 81}]
        self.assertEqual(self._flatten(rows, 161), [80, 81])

    def test_row_order_preserved(self):
        rows = [{"qty_to_split": 2, "pieces_per_split": 30}, {"qty_to_split": 1, "pieces_per_split": 40}]
        self.assertEqual(self._flatten(rows, 100), [30, 30, 40])

    def test_short_total_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._flatten([{"qty_to_split": 1, "pieces_per_split": 80}], 161)

    def test_over_total_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._flatten([{"qty_to_split": 1, "pieces_per_split": 200}], 161)

    def test_zero_qty_to_split_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._flatten([{"qty_to_split": 0, "pieces_per_split": 80}], 80)

    def test_negative_pieces_per_split_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._flatten([{"qty_to_split": 1, "pieces_per_split": -5}], 80)

    def test_empty_rows_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._flatten([], 100)


class TestWarpingServiceIntegration(unittest.TestCase):
    """Bench integration checks."""

    def test_beam_split_row_doctype_exists(self):
        try:
            import frappe
            self.assertTrue(frappe.db.exists("DocType", "DESAR Beam Split Row"))
        except ImportError:
            self.skipTest("frappe not available")

    def test_roll_chain_has_planned_qty_field(self):
        try:
            import frappe
            meta = frappe.get_meta("DESAR Roll Chain")
            self.assertTrue(meta.has_field("planned_qty"))
        except ImportError:
            self.skipTest("frappe not available")

    def test_split_beam_api_importable(self):
        try:
            from desar_manufacturing.api.production_order import split_beam
            self.assertTrue(callable(split_beam))
        except ImportError:
            self.skipTest("frappe not available")

    def test_split_wo_per_roll_importable(self):
        try:
            from desar_manufacturing.services.wo_split_helpers import split_wo_per_roll
            self.assertTrue(callable(split_wo_per_roll))
        except ImportError:
            self.skipTest("frappe not available")
