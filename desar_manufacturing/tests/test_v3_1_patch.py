"""
Unit tests for patches/v3_1_fix_weaving_stage_and_placeholder_warehouses.py —
fully mocked, no real DB writes, since this patch runs unsupervised on a
client's production site and must be verified without touching live data.
"""
import unittest
from unittest.mock import patch, MagicMock

import frappe
from desar_manufacturing.patches import v3_1_fix_weaving_stage_and_placeholder_warehouses as patch_module


class TestFixWeavingStageName(unittest.TestCase):
    @patch("frappe.db.commit")
    @patch("frappe.logger")
    @patch("frappe.db.set_value")
    @patch("frappe.get_all")
    def test_corrects_mislabeled_rows(self, mock_get_all, mock_set_value, mock_logger, mock_commit):
        mock_get_all.return_value = ["row-1", "row-2"]
        patch_module._fix_weaving_stage_name()

        mock_get_all.assert_called_once_with(
            "DESAR Stage Configuration",
            filters={"output_item": "Grey Roll", "stage_name": ["!=", "Weaving"]},
            pluck="name",
        )
        self.assertEqual(mock_set_value.call_count, 2)
        mock_set_value.assert_any_call("DESAR Stage Configuration", "row-1", "stage_name", "Weaving", update_modified=False)
        mock_set_value.assert_any_call("DESAR Stage Configuration", "row-2", "stage_name", "Weaving", update_modified=False)
        mock_commit.assert_called_once()

    @patch("frappe.db.commit")
    @patch("frappe.db.set_value")
    @patch("frappe.get_all")
    def test_noop_when_nothing_mislabeled(self, mock_get_all, mock_set_value, mock_commit):
        mock_get_all.return_value = []
        patch_module._fix_weaving_stage_name()

        mock_set_value.assert_not_called()
        mock_commit.assert_not_called()


class TestFixPlaceholderWarehouses(unittest.TestCase):
    def _settings(self, **overrides):
        base = {
            "yarn_warehouse": "Yarn Store - TAC",
            "chemical_warehouse": "Chemical Store - TAC",
            "accessories_warehouse": "Accessories Store - TAC",
            "warping_wip_warehouse": "Warping WIP - TAC",
            "loom_floor_warehouse": "Loom Floor - TAC",
            "grey_roll_warehouse": "Grey Roll Store - TAC",
            "finishing_wip_warehouse": "Finishing WIP - TAC",
            "finished_roll_warehouse": "Finished Roll Store - TAC",
            "cutting_packing_warehouse": "Cutting and Packing Floor - TAC",
            "fg_grade_a_warehouse": "Finished Goods Grade A - TAC",
            "scrap_warehouse": "Scrap Yard - TAC",
        }
        base.update(overrides)
        return base

    @patch("frappe.log_error")
    @patch("frappe.db.commit")
    @patch("frappe.db.set_value")
    @patch("frappe.db.exists")
    @patch("frappe.get_all")
    @patch("frappe.db.get_single_value")
    @patch("frappe.db.get_singles_dict")
    def test_fixes_named_placeholder_and_generic_fallback(
        self, mock_singles, mock_single_value, mock_get_all, mock_exists, mock_set_value, mock_commit, mock_log_error
    ):
        mock_singles.return_value = self._settings()
        mock_single_value.return_value = "Work In Progress - TAC"  # Manufacturing Settings default_wip_warehouse
        mock_get_all.return_value = [
            frappe._dict({"name": "MFG-WO-0001", "wip_warehouse": "Loom Floor - ST",
             "source_warehouse": None, "fg_warehouse": None, "scrap_warehouse": None}),
            frappe._dict({"name": "MFG-WO-0002", "wip_warehouse": None,
             "source_warehouse": "Warping WIP - ST", "fg_warehouse": None,
             "scrap_warehouse": "Work In Progress - ST"}),
        ]
        # frappe.db.exists("DocType", "DESAR Settings") -> True; frappe.db.exists("Warehouse", ...) -> True
        mock_exists.return_value = True

        patch_module._fix_placeholder_warehouses()

        mock_set_value.assert_any_call("Work Order", "MFG-WO-0001", "wip_warehouse", "Loom Floor - TAC", update_modified=False)
        mock_set_value.assert_any_call("Work Order", "MFG-WO-0002", "source_warehouse", "Warping WIP - TAC", update_modified=False)
        mock_set_value.assert_any_call("Work Order", "MFG-WO-0002", "scrap_warehouse", "Work In Progress - TAC", update_modified=False)
        mock_commit.assert_called_once()
        mock_log_error.assert_called_once()
        self.assertIn("Corrected 2 Draft Work Order(s)", mock_log_error.call_args.kwargs["message"])

    @patch("frappe.log_error")
    @patch("frappe.db.commit")
    @patch("frappe.db.set_value")
    @patch("frappe.db.exists")
    @patch("frappe.get_all")
    @patch("frappe.db.get_single_value")
    @patch("frappe.db.get_singles_dict")
    def test_leaves_healthy_fields_untouched(
        self, mock_singles, mock_single_value, mock_get_all, mock_exists, mock_set_value, mock_commit, mock_log_error
    ):
        """A Work Order matched by the OR-filter (one field broken) must not
        have its OTHER, already-correct fields touched."""
        mock_singles.return_value = self._settings()
        mock_single_value.return_value = "Work In Progress - TAC"
        mock_get_all.return_value = [
            frappe._dict({"name": "MFG-WO-0003", "wip_warehouse": "Loom Floor - ST",
             "source_warehouse": "Warping WIP - TAC",  # already correct — must not change
             "fg_warehouse": "Loom Floor - TAC", "scrap_warehouse": "Scrap Yard - TAC"}),
        ]
        mock_exists.return_value = True

        patch_module._fix_placeholder_warehouses()

        set_fields = {call.args[2] for call in mock_set_value.call_args_list}
        self.assertEqual(set_fields, {"wip_warehouse"})

    @patch("frappe.log_error")
    @patch("frappe.db.commit")
    @patch("frappe.db.set_value")
    @patch("frappe.db.exists")
    @patch("frappe.get_all")
    @patch("frappe.db.get_single_value")
    @patch("frappe.db.get_singles_dict")
    def test_skips_and_reports_when_settings_field_itself_blank(
        self, mock_singles, mock_single_value, mock_get_all, mock_exists, mock_set_value, mock_commit, mock_log_error
    ):
        """If DESAR Settings' own field for that warehouse is blank, don't
        guess — leave it and report it for manual follow-up."""
        mock_singles.return_value = self._settings(loom_floor_warehouse="")  # blank on this site
        mock_single_value.return_value = "Work In Progress - TAC"
        mock_get_all.return_value = [
            frappe._dict({"name": "MFG-WO-0004", "wip_warehouse": "Loom Floor - ST",
             "source_warehouse": None, "fg_warehouse": None, "scrap_warehouse": None}),
        ]
        mock_exists.return_value = True

        patch_module._fix_placeholder_warehouses()

        mock_set_value.assert_not_called()
        mock_log_error.assert_called_once()
        message = mock_log_error.call_args.kwargs["message"]
        self.assertIn("Could NOT auto-resolve", message)
        self.assertIn("MFG-WO-0004", message)

    @patch("frappe.log_error")
    @patch("frappe.db.commit")
    @patch("frappe.db.set_value")
    @patch("frappe.get_all")
    @patch("frappe.db.get_single_value")
    @patch("frappe.db.get_singles_dict")
    @patch("frappe.db.exists")
    def test_noop_when_nothing_broken(
        self, mock_exists, mock_singles, mock_single_value, mock_get_all, mock_set_value, mock_commit, mock_log_error
    ):
        mock_exists.return_value = True
        mock_singles.return_value = self._settings()
        mock_single_value.return_value = "Work In Progress - TAC"
        mock_get_all.return_value = []

        patch_module._fix_placeholder_warehouses()

        mock_set_value.assert_not_called()
        mock_commit.assert_not_called()
        mock_log_error.assert_not_called()


class TestExecuteGuards(unittest.TestCase):
    @patch("desar_manufacturing.patches.v3_1_fix_weaving_stage_and_placeholder_warehouses._fix_weaving_stage_name")
    @patch("desar_manufacturing.patches.v3_1_fix_weaving_stage_and_placeholder_warehouses._fix_placeholder_warehouses")
    @patch("frappe.db.exists")
    def test_skips_entirely_if_app_doctypes_missing(self, mock_exists, mock_fix_wh, mock_fix_stage):
        mock_exists.return_value = False
        patch_module.execute()
        mock_fix_stage.assert_not_called()
        mock_fix_wh.assert_not_called()

    @patch("desar_manufacturing.patches.v3_1_fix_weaving_stage_and_placeholder_warehouses._fix_weaving_stage_name")
    @patch("desar_manufacturing.patches.v3_1_fix_weaving_stage_and_placeholder_warehouses._fix_placeholder_warehouses")
    @patch("frappe.db.exists")
    def test_runs_both_fixes_when_doctypes_present(self, mock_exists, mock_fix_wh, mock_fix_stage):
        mock_exists.return_value = True
        patch_module.execute()
        mock_fix_stage.assert_called_once()
        mock_fix_wh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
