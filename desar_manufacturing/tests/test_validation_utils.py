"""
DESAR Manufacturing — Level 1 Unit Tests
Tests for validation_utils.py

These tests have ZERO external dependencies.
No ERPNext, no database, no fixtures required.
Run with: python3 -m pytest tests/test_validation_utils.py -v

Author: DESAR Factory
Version: 2.3.0
"""

import sys
import os
import unittest

# Allow running without bench context
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub frappe.utils.flt so we can run without frappe installed
try:
    from frappe.utils import flt
except ImportError:
    def flt(val, precision=None):
        try:
            return float(val or 0)
        except (ValueError, TypeError):
            return 0.0
    # Inject stub into module namespace so imports work
    import types
    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.flt = flt
    frappe_module = types.ModuleType("frappe")
    frappe_module.utils = frappe_utils
    sys.modules.setdefault("frappe", frappe_module)
    sys.modules.setdefault("frappe.utils", frappe_utils)

from desar_manufacturing.utils.validation_utils import (
    validate_final_grade_counts,
    validate_grey_estimate_reasonable,
    validate_finishing_estimate_reasonable,
    derive_grade_b_item,
)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_final_grade_counts
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateFinalGradeCounts(unittest.TestCase):
    """
    STRICT validation: A + B + C must equal WO qty exactly.
    Every piece must be accounted for.
    """

    # ── Passing cases ─────────────────────────────────────────────────────────

    def test_exact_match_passes(self):
        """42 + 6 + 2 = 50 == WO qty 50"""
        valid, msg = validate_final_grade_counts(42, 6, 2, 50)
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_all_grade_a_passes(self):
        """Perfect roll — all 50 pieces are Grade A"""
        valid, msg = validate_final_grade_counts(50, 0, 0, 50)
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_all_scrap_passes(self):
        """Bad roll — all 50 pieces are scrap"""
        valid, msg = validate_final_grade_counts(0, 0, 50, 50)
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_no_final_grades_passes(self):
        """All zeros = not a final QI — skip validation"""
        valid, msg = validate_final_grade_counts(0, 0, 0, 50)
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_no_wo_qty_passes_silently(self):
        """WO qty unknown — cannot validate, pass silently"""
        valid, msg = validate_final_grade_counts(42, 6, 2, 0)
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_float_inputs_pass(self):
        """Inputs come as floats from frappe.utils.flt"""
        valid, msg = validate_final_grade_counts(42.0, 6.0, 2.0, 50.0)
        self.assertTrue(valid)

    # ── Failing cases ─────────────────────────────────────────────────────────

    def test_total_exceeds_wo_qty_fails(self):
        """51 > 50 — inspector counted wrong"""
        valid, msg = validate_final_grade_counts(43, 6, 2, 50)
        self.assertFalse(valid)
        self.assertIn("51", msg)
        self.assertIn("50", msg)

    def test_total_less_than_wo_qty_fails(self):
        """48 < 50 — 2 pieces unaccounted"""
        valid, msg = validate_final_grade_counts(40, 6, 2, 50)
        self.assertFalse(valid)
        self.assertIn("2", msg)
        self.assertIn("unaccounted", msg.lower())

    def test_error_message_contains_diff(self):
        """Error message must show exactly how many pieces are missing"""
        valid, msg = validate_final_grade_counts(44, 0, 0, 50)
        self.assertFalse(valid)
        self.assertIn("6", msg)  # diff = 6

    def test_by_one_over_fails(self):
        """Off by one over — must not pass"""
        valid, msg = validate_final_grade_counts(42, 6, 3, 50)
        self.assertFalse(valid)

    def test_by_one_under_fails(self):
        """Off by one under — must not pass"""
        valid, msg = validate_final_grade_counts(42, 6, 1, 50)
        self.assertFalse(valid)

    def test_string_inputs_coerced(self):
        """ERPNext sometimes passes field values as strings"""
        valid, msg = validate_final_grade_counts("42", "6", "2", "50")
        self.assertTrue(valid)


# ═══════════════════════════════════════════════════════════════════════════════
# derive_grade_b_item
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeriveGradeBItem(unittest.TestCase):
    """
    Derives Grade B item code from Grade A.
    Replaces LAST occurrence of -A with -B.
    """

    def test_standard_60_size(self):
        self.assertEqual(
            derive_grade_b_item("Shemagh-VIC-60-A"),
            "Shemagh-VIC-60-B"
        )

    def test_58_size(self):
        self.assertEqual(
            derive_grade_b_item("Shemagh-VIC-58-A"),
            "Shemagh-VIC-58-B"
        )

    def test_62_size(self):
        self.assertEqual(
            derive_grade_b_item("Shemagh-VIC-62-A"),
            "Shemagh-VIC-62-B"
        )

    def test_different_article(self):
        self.assertEqual(
            derive_grade_b_item("Shemagh-MAD-60-A"),
            "Shemagh-MAD-60-B"
        )

    def test_replaces_last_a_only(self):
        """
        Item: Shemagh-VIC-A1-60-A
        The -A in A1 must NOT be replaced — only the trailing -A
        """
        result = derive_grade_b_item("Shemagh-VIC-A1-60-A")
        self.assertEqual(result, "Shemagh-VIC-A1-60-B")
        # This is wrong — must NOT produce this:
        self.assertNotEqual(result, "Shemagh-VIC-B1-60-A")

    def test_no_grade_suffix_returns_none(self):
        """Item without -A suffix cannot be derived"""
        self.assertIsNone(derive_grade_b_item("Shemagh-VIC-60"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(derive_grade_b_item(""))

    def test_none_returns_none(self):
        self.assertIsNone(derive_grade_b_item(None))

    def test_non_shemagh_item_with_a_suffix(self):
        """Any item ending in -A should work"""
        self.assertEqual(derive_grade_b_item("SomeItem-60-A"), "SomeItem-60-B")


# ═══════════════════════════════════════════════════════════════════════════════
# validate_grey_estimate_reasonable
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateGreyEstimateReasonable(unittest.TestCase):
    """
    SOFT warning: grey estimate totals that look unusual.
    Does NOT block submission — only returns warning string.
    """

    def test_normal_range_no_warning(self):
        """42 + 6 + 2 = 50 — normal, no warning"""
        self.assertIsNone(validate_grey_estimate_reasonable(42, 6, 2))

    def test_exactly_at_max_no_warning(self):
        """At exactly 80 — boundary, no warning"""
        self.assertIsNone(validate_grey_estimate_reasonable(70, 8, 2))

    def test_above_max_warns(self):
        """85 total > 80 max — warn"""
        warning = validate_grey_estimate_reasonable(75, 5, 5)
        self.assertIsNotNone(warning)
        self.assertIsInstance(warning, str)
        self.assertGreater(len(warning), 0)

    def test_below_min_warns(self):
        """8 total < 10 min — warn"""
        warning = validate_grey_estimate_reasonable(5, 2, 1)
        self.assertIsNotNone(warning)

    def test_zero_totals_no_warning(self):
        """Not a grey QI — no grades filled — no warning"""
        self.assertIsNone(validate_grey_estimate_reasonable(0, 0, 0))

    def test_custom_thresholds(self):
        """Custom thresholds passed by caller"""
        # total=30, max=25 → should warn
        warning = validate_grey_estimate_reasonable(
            20, 5, 5, max_expected=25, min_expected=5
        )
        self.assertIsNotNone(warning)

    def test_warning_is_string_not_exception(self):
        """Warning must be a string, not raise an exception"""
        result = validate_grey_estimate_reasonable(90, 0, 0)
        self.assertIsInstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_finishing_estimate_reasonable (same logic as grey)
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateFinishingEstimateReasonable(unittest.TestCase):

    def test_normal_range_no_warning(self):
        self.assertIsNone(validate_finishing_estimate_reasonable(40, 7, 3))

    def test_high_total_warns(self):
        warning = validate_finishing_estimate_reasonable(80, 0, 5)
        self.assertIsNotNone(warning)

    def test_zero_totals_no_warning(self):
        self.assertIsNone(validate_finishing_estimate_reasonable(0, 0, 0))


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestValidateFinalGradeCounts))
    suite.addTests(loader.loadTestsFromTestCase(TestDeriveGradeBItem))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateGreyEstimateReasonable))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateFinishingEstimateReasonable))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
