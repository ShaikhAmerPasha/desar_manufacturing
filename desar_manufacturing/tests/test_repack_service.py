"""
Repack Service — source warehouse + explicit valuation on the outgoing row.

Reproduces the live bug: create_from_final_qi sourced the outgoing (consumed)
line from cutting_packing_warehouse — a WIP staging warehouse the Packing
Work Order's output is never actually placed in (it lands in
fg_grade_a_warehouse instead, per events/work_order.py's own stage-to-
warehouse mapping). Frappe couldn't find a valuation rate there, so the
whole Stock Entry failed to insert — silently caught, logged, and shown as
an orange "create it manually" message instead of a QI-submission failure.
"""
import unittest
from unittest.mock import patch, MagicMock

import frappe
from desar_manufacturing.services.repack_service import RepackService


class TestSourceWarehouseResolution(unittest.TestCase):
    @patch("desar_manufacturing.services.repack_service.SettingsManager.get_warehouse")
    @patch("desar_manufacturing.services.repack_service.SettingsManager.is_auto_repack_enabled", return_value=True)
    @patch("desar_manufacturing.services.repack_service.SettingsManager.get_company", return_value="Standardtouch")
    @patch("desar_manufacturing.services.repack_service.SettingsManager.get_grade_configuration", return_value=[])
    @patch.object(RepackService, "_build_items_legacy", return_value=([], 0))
    def test_wh_src_resolves_to_fg_grade_a_not_cutting_packing(
        self, mock_build, mock_grade_config, mock_company, mock_enabled, mock_get_warehouse
    ):
        qi_doc = MagicMock()
        RepackService.create_from_final_qi(qi_doc)
        mock_get_warehouse.assert_called_once_with("fg_grade_a_warehouse")
        self.assertNotIn(
            unittest.mock.call("cutting_packing_warehouse"),
            mock_get_warehouse.call_args_list,
        )


class TestSourceRowHasExplicitValuation(unittest.TestCase):
    """The outgoing row must never depend on Frappe's own stock-ledger
    valuation lookup — that dependency is exactly what threw
    'Valuation Rate ... is required' in production."""

    def test_dynamic_mode_source_row(self):
        with patch.object(RepackService, "_get_base_item", return_value="Shemagh-ZEP-55-A"), \
             patch("desar_manufacturing.services.repack_service.StockEntryRepository.get_valuation_rate", return_value=42.5), \
             patch.object(RepackService, "_read_grade_readings_from_qi", return_value=[{"grade_code": "A", "qty": 100}]), \
             patch.object(RepackService, "_stock_uom", return_value="Nos"), \
             patch("frappe.db.exists", return_value=True):
            grade_config = [frappe._dict({
                "grade_code": "A", "is_scrap": 0, "valuation_pct": 100,
                "item_suffix": "-A", "target_warehouse": "FG Grade A - ST",
            })]
            items, total = RepackService._build_items_dynamic(MagicMock(), grade_config, "FG Grade A - ST")

        source_row = items[0]
        self.assertEqual(source_row["basic_rate"], 42.5)
        self.assertEqual(source_row["set_basic_rate_manually"], 1)

    def test_legacy_mode_source_row(self):
        from desar_manufacturing.constants import QIFields

        qi_doc = frappe._dict({
            QIFields.FINAL_A: 24, QIFields.FINAL_B: 4, QIFields.FINAL_C: 2,
            "item_code": "Shemagh-ZEP-55-A",
        })
        with patch.object(RepackService, "_get_base_item", return_value="Shemagh-ZEP-55-A"), \
             patch("desar_manufacturing.services.repack_service.StockEntryRepository.get_valuation_rate", return_value=42.5), \
             patch("desar_manufacturing.services.repack_service.SettingsManager.get_warehouse", return_value="FG Grade A - ST"), \
             patch.object(RepackService, "_stock_uom", return_value="Nos"), \
             patch("frappe.db.exists", return_value=True):
            items, total = RepackService._build_items_legacy(qi_doc, "FG Grade A - ST")

        source_row = items[0]
        self.assertEqual(source_row["basic_rate"], 42.5)
        self.assertEqual(source_row["set_basic_rate_manually"], 1)

    def test_build_items_alias_source_row(self):
        """_build_items (kept for existing test compatibility) too."""
        items = RepackService._build_items(
            item_a="Shemagh-VIC-60-A", item_b="Shemagh-VIC-60-B",
            wh_src="Cutting - ST", wh_a="FG Grade A - ST", wh_b="FG Grade B - ST",
            total=50, grade_a=42, grade_b=6, val_rate=100.0,
        )
        source_row = items[0]
        self.assertEqual(source_row["basic_rate"], 100.0)
        self.assertEqual(source_row["set_basic_rate_manually"], 1)
