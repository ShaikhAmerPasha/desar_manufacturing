"""
Work Order — design context auto-fill must survive Production Plan's bulk
Work Order creation.

Production Plan.create_work_order() sets wo.flags.ignore_validate = True
before every insert() it makes, which skips validate() (and any hooks.py
"validate" handler) entirely. before_validate is NOT gated by that flag, so
design context/warehouse/skip_transfer auto-fill must live there to be
reliable for Work Orders created from a Production Plan — this is what
actually determines whether custom_design_master ends up set on a batch of
35 (or 3500) auto-created Work Orders with zero manual patching.
"""
import unittest
from unittest.mock import MagicMock, patch

import frappe
from desar_manufacturing.events import work_order


class TestDesignContextSurvivesIgnoreValidate(unittest.TestCase):
    """Calls the real before_validate() — not validate() — matching exactly
    what Production Plan's bulk creation actually invokes."""

    @patch("frappe.db.get_value", return_value=frappe._dict({
        "custom_design_no": "560", "custom_article_name": "Zephyr", "custom_design_master": "DM-2026-0014",
    }))
    @patch("frappe.db.has_column", return_value=True)
    @patch("frappe.get_cached_value", return_value=0)
    def test_before_validate_sets_design_context_from_bom(self, mock_cached, mock_has_col, mock_get_value):
        doc = MagicMock(bom_no="BOM-Shemagh-ZEP-55-A-001", stock_uom=None, qty=None,
                         custom_design_no=None, custom_article_name=None, custom_design_master=None)
        doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
        doc.flags.get.return_value = None

        with patch.object(work_order, "_autofill_warehouses"), patch.object(work_order, "_apply_skip_transfer"):
            work_order.before_validate(doc)

        self.assertEqual(doc.custom_design_master, "DM-2026-0014")
        self.assertEqual(doc.custom_design_no, "560")

    def test_before_insert_delegates_and_also_sets_design_context(self):
        """before_insert is what Production Plan's wo.insert() actually
        triggers — confirm it reaches the same design-context logic, not
        just qty rounding."""
        doc = MagicMock(bom_no=None, stock_uom=None, qty=None,
                         custom_design_no=None, custom_article_name=None, custom_design_master=None)
        doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)

        with patch.object(work_order, "_autofill_design_context") as mock_autofill, \
             patch.object(work_order, "_autofill_warehouses"), \
             patch.object(work_order, "_apply_skip_transfer"):
            work_order.before_insert(doc)

        mock_autofill.assert_called_once_with(doc)

    def test_validate_no_longer_the_only_place_design_context_runs(self):
        """Regression guard: if someone removes the before_validate calls
        (e.g. during a refactor) without noticing why they're there, this
        fails — validate() alone is not reachable from Production Plan's
        bulk creation path."""
        with patch.object(work_order, "_autofill_design_context") as mock_autofill, \
             patch.object(work_order, "_autofill_warehouses"), \
             patch.object(work_order, "_apply_skip_transfer"):
            doc = MagicMock(stock_uom=None, qty=None)
            doc.get.return_value = []
            work_order.before_validate(doc)
        mock_autofill.assert_called_once()
