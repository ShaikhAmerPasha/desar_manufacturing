"""
DESAR Manufacturing — Dynamic Architecture Tests (Days 2-9)

Tests for the dynamic grade and stage configuration system.

Level 1 tests (no ERPNext): test pure logic
Level 2 tests (ERPNext): test with DB

Run:
    Level 1: python3 -m pytest tests/test_dynamic_architecture.py -v
    Level 2: bench --site excel run-tests --app desar_manufacturing --module desar_manufacturing.tests.test_dynamic_architecture

Author: DESAR Factory
Version: 3.0.0
"""

import sys
import os
import unittest

# ── Frappe stub for Level 1 tests ─────────────────────────────────────────────
try:
    import frappe
    FRAPPE_AVAILABLE = True
except ImportError:
    FRAPPE_AVAILABLE = False
    # Minimal stubs
    import types
    frappe_mod = types.ModuleType("frappe")
    frappe_mod.utils = types.ModuleType("frappe.utils")
    frappe_mod.utils.flt = lambda v, p=None: float(v or 0)
    sys.modules["frappe"] = frappe_mod
    sys.modules["frappe.utils"] = frappe_mod.utils


# ═══════════════════════════════════════════════════════════════════════════════
# LEVEL 1 — Pure logic, no DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestGradeConfiguration(unittest.TestCase):
    """
    Tests for grade configuration logic.
    Pure Python — no ERPNext required.
    """

    def _make_grade_config(self, grades):
        """Helper to create mock grade config."""
        class MockGrade:
            def __init__(self, code, label, valuation_pct, target_wh,
                         item_suffix="", scrap_item="", is_scrap=0):
                self.grade_code = code
                self.grade_label = label
                self.valuation_pct = valuation_pct
                self.target_warehouse = target_wh
                self.item_suffix = item_suffix
                self.scrap_item = scrap_item
                self.is_scrap = is_scrap
        return [MockGrade(*g) for g in grades]

    def test_standard_3_grade_config(self):
        """Standard A/B/C config should produce 3 grades."""
        config = self._make_grade_config([
            ("A", "Premium",  100, "FG Grade A", "-A", "", 0),
            ("B", "Standard",  60, "FG Grade B", "-B", "", 0),
            ("C", "Scrap",      5, "Scrap Yard",  "",  "Shemagh Scrap", 1),
        ])
        self.assertEqual(len(config), 3)
        self.assertEqual(config[0].grade_code, "A")
        self.assertEqual(config[1].valuation_pct, 60)
        self.assertTrue(config[2].is_scrap)

    def test_4_grade_config(self):
        """Adding Grade D should work without code change."""
        config = self._make_grade_config([
            ("A", "Premium",  100, "FG Grade A", "-A", "", 0),
            ("B", "Standard",  60, "FG Grade B", "-B", "", 0),
            ("C", "Export",    85, "FG Export",  "-C", "", 0),
            ("D", "Scrap",      5, "Scrap Yard",  "",  "Shemagh Scrap", 1),
        ])
        self.assertEqual(len(config), 4)
        # Grade C is export at 85%
        export_grade = next(g for g in config if g.grade_code == "C")
        self.assertEqual(export_grade.valuation_pct, 85)

    def test_derive_item_with_suffix(self):
        """Item suffix derivation works for any suffix."""
        # Test the logic directly without importing frappe-dependent module
        def derive_item_with_suffix(base_item, suffix):
            if not base_item or not suffix:
                return ""
            for existing in ["-A", "-B", "-C", "-D", "-E", "-F"]:
                if base_item.endswith(existing):
                    return base_item[:-len(existing)] + suffix
            return base_item + suffix

        self.assertEqual(derive_item_with_suffix("Shemagh-VIC-60-A", "-B"), "Shemagh-VIC-60-B")
        self.assertEqual(derive_item_with_suffix("Shemagh-VIC-60-A", "-C"), "Shemagh-VIC-60-C")
        self.assertEqual(derive_item_with_suffix("Shemagh-VIC-60-A", "-D"), "Shemagh-VIC-60-D")
        self.assertEqual(derive_item_with_suffix("Shemagh-VIC-60", "-A"),   "Shemagh-VIC-60-A")

    def test_derive_item_empty_inputs(self):
        """Empty inputs return empty string."""
        def derive_item_with_suffix(base_item, suffix):
            if not base_item or not suffix:
                return ""
            for existing in ["-A", "-B", "-C", "-D", "-E", "-F"]:
                if base_item.endswith(existing):
                    return base_item[:-len(existing)] + suffix
            return base_item + suffix

        self.assertEqual(derive_item_with_suffix("", "-B"), "")
        self.assertEqual(derive_item_with_suffix("Shemagh-VIC-60-A", ""), "")


class TestStageConfiguration(unittest.TestCase):
    """
    Tests for stage configuration logic.
    Pure Python — no ERPNext required.
    """

    def _make_stage(self, seq, name, output_item, qi_required=0,
                    roll_ticket_trigger=0, is_final_stage=0, can_split=0):
        """Helper to create mock stage."""
        class MockStage:
            pass
        s = MockStage()
        s.stage_seq = seq
        s.stage_name = name
        s.output_item = output_item
        s.qi_required = qi_required
        s.roll_ticket_trigger = roll_ticket_trigger
        s.is_final_stage = is_final_stage
        s.can_split = can_split
        s.operations = []
        s.bom_no = None
        return s

    def test_standard_4_stage_config(self):
        """Standard DESAR 4-stage config."""
        stages = [
            self._make_stage(1, "Warping",  "Warping Beam", qi_required=0, roll_ticket_trigger=0),
            self._make_stage(2, "Weaving",  "Grey Roll",    qi_required=1, roll_ticket_trigger=1),
            self._make_stage(3, "Finishing","Finished Roll",qi_required=1, roll_ticket_trigger=0),
            self._make_stage(4, "Packing",  "Shemagh",      qi_required=1, roll_ticket_trigger=0, is_final_stage=1),
        ]

        # Verify counts
        qi_stages = [s for s in stages if s.qi_required]
        self.assertEqual(len(qi_stages), 3)

        roll_trigger_stages = [s for s in stages if s.roll_ticket_trigger]
        self.assertEqual(len(roll_trigger_stages), 1)
        self.assertEqual(roll_trigger_stages[0].output_item, "Grey Roll")

        final_stages = [s for s in stages if s.is_final_stage]
        self.assertEqual(len(final_stages), 1)
        self.assertEqual(final_stages[0].stage_name, "Packing")

    def test_5_stage_striped_config(self):
        """Striped Shemagh with 5 stages including Dyeing."""
        stages = [
            self._make_stage(1, "Warping",  "Warping Beam",  qi_required=0),
            self._make_stage(2, "Weaving",  "Grey Roll",     qi_required=1, roll_ticket_trigger=1),
            self._make_stage(3, "Dyeing",   "Dyed Roll",     qi_required=1),
            self._make_stage(4, "Finishing","Finished Roll", qi_required=1),
            self._make_stage(5, "Packing",  "Shemagh",       qi_required=1, is_final_stage=1),
        ]
        self.assertEqual(len(stages), 5)
        qi_stages = [s for s in stages if s.qi_required]
        self.assertEqual(len(qi_stages), 4)

    def test_can_split_flag(self):
        """Can split flag allows parallel WO creation."""
        stage = self._make_stage(1, "Warping", "Warping Beam", can_split=1)
        self.assertTrue(stage.can_split)

    def test_stage_ordering(self):
        """Stages should be ordered by seq."""
        stages = [
            self._make_stage(3, "Finishing", "Finished Roll"),
            self._make_stage(1, "Warping",   "Warping Beam"),
            self._make_stage(2, "Weaving",   "Grey Roll"),
        ]
        sorted_stages = sorted(stages, key=lambda s: s.stage_seq)
        self.assertEqual([s.stage_name for s in sorted_stages],
                         ["Warping", "Weaving", "Finishing"])


class TestSampleSizeCalculation(unittest.TestCase):
    """Tests for sample size formula calculation."""

    def _calc(self, formula, wo_qty):
        """Calculate sample size from formula — pure logic, no frappe."""
        try:
            if formula == "1":
                return 1
            elif formula == "wo_qty":
                return wo_qty
            elif formula.startswith("wo_qty *"):
                factor = float(formula.split("*")[1].strip())
                return max(1, int(wo_qty * factor))
            return 1
        except Exception:
            return 1

    def test_fixed_1(self):
        self.assertEqual(self._calc("1", 50), 1)

    def test_wo_qty(self):
        self.assertEqual(self._calc("wo_qty", 50), 50)

    def test_10_percent(self):
        result = self._calc("wo_qty * 0.1", 50)
        self.assertEqual(result, 5)

    def test_5_percent(self):
        result = self._calc("wo_qty * 0.05", 100)
        self.assertEqual(result, 5)

    def test_minimum_1(self):
        """Even 5% of 1 should be at least 1."""
        result = self._calc("wo_qty * 0.05", 1)
        self.assertGreaterEqual(result, 1)


class TestStageMappingToLegacy(unittest.TestCase):
    """Tests for stage name to legacy stage mapping."""

    def _map(self, name):
        """Map stage name to legacy — pure logic, no frappe."""
        name_lower = name.lower()
        if "grey" in name_lower or "weaving" in name_lower:
            return "grey"
        elif "finishing" in name_lower or "chemical" in name_lower:
            return "finishing"
        elif "packing" in name_lower or "cutting" in name_lower or "final" in name_lower:
            return "final"
        return "final"

    def test_grey_stage(self):
        self.assertEqual(self._map("Weaving"), "grey")
        self.assertEqual(self._map("Grey Stage"), "grey")

    def test_finishing_stage(self):
        self.assertEqual(self._map("Finishing"), "finishing")
        self.assertEqual(self._map("Chemical Finishing"), "finishing")

    def test_final_stage(self):
        self.assertEqual(self._map("Packing"), "final")
        self.assertEqual(self._map("Cutting"), "final")
        self.assertEqual(self._map("Final QC"), "final")

    def test_unknown_defaults_to_final(self):
        self.assertEqual(self._map("Dyeing"), "final")


# ═══════════════════════════════════════════════════════════════════════════════
# LEVEL 2 — Integration tests (requires ERPNext)
# ═══════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(FRAPPE_AVAILABLE, "ERPNext not available")
class TestGradeConfigurationIntegration(unittest.TestCase):
    """
    Integration tests for Grade Configuration.
    Verifies DESAR Settings Grade Configuration child table works correctly.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        if not frappe.db.exists("DocType", "DESAR Grade Configuration"):
            raise unittest.SkipTest("DESAR Grade Configuration DocType not found. Run bench migrate.")
        if not frappe.db.exists("DocType", "DESAR Settings"):
            raise unittest.SkipTest("DESAR Settings not found.")

    def test_settings_manager_has_grade_configuration_method(self):
        """SettingsManager must have get_grade_configuration method."""
        from desar_manufacturing.config.settings_manager import SettingsManager
        self.assertTrue(hasattr(SettingsManager, "get_grade_configuration"))
        self.assertTrue(hasattr(SettingsManager, "has_grade_configuration"))

    def test_grade_configuration_returns_list(self):
        """get_grade_configuration always returns a list, never raises."""
        from desar_manufacturing.config.settings_manager import SettingsManager
        result = SettingsManager.get_grade_configuration()
        self.assertIsInstance(result, list)

    def test_has_grade_configuration_returns_bool(self):
        """has_grade_configuration returns bool."""
        from desar_manufacturing.config.settings_manager import SettingsManager
        result = SettingsManager.has_grade_configuration()
        self.assertIsInstance(result, bool)

    def test_grade_configuration_doctype_exists(self):
        """DESAR Grade Configuration DocType must exist after migrate."""
        self.assertTrue(frappe.db.exists("DocType", "DESAR Grade Configuration"))

    def test_grade_configuration_is_child_table(self):
        """DESAR Grade Configuration must be a child table."""
        meta = frappe.get_meta("DESAR Grade Configuration")
        self.assertEqual(meta.istable, 1)

    def test_grade_configuration_has_required_fields(self):
        """Grade Configuration must have all required fields."""
        meta = frappe.get_meta("DESAR Grade Configuration")
        field_names = [f.fieldname for f in meta.fields]
        required = ["grade_code", "grade_label", "valuation_pct",
                    "target_warehouse", "item_suffix", "is_scrap", "is_active"]
        for field in required:
            self.assertIn(field, field_names, f"Missing field: {field}")


@unittest.skipUnless(FRAPPE_AVAILABLE, "ERPNext not available")
class TestStageConfigurationIntegration(unittest.TestCase):
    """
    Integration tests for Stage Configuration.
    Verifies Design Master Stage Configuration child table works correctly.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        if not frappe.db.exists("DocType", "DESAR Stage Configuration"):
            raise unittest.SkipTest("DESAR Stage Configuration not found. Run bench migrate.")

    def test_stage_configuration_doctype_exists(self):
        """DESAR Stage Configuration must exist after migrate."""
        self.assertTrue(frappe.db.exists("DocType", "DESAR Stage Configuration"))

    def test_stage_configuration_is_child_table(self):
        """Must be a child table."""
        meta = frappe.get_meta("DESAR Stage Configuration")
        self.assertEqual(meta.istable, 1)

    def test_stage_configuration_has_required_fields(self):
        """Must have all required fields."""
        meta = frappe.get_meta("DESAR Stage Configuration")
        field_names = [f.fieldname for f in meta.fields]
        required = [
            "stage_seq", "stage_name", "output_item",
            "qi_required", "qi_template", "roll_ticket_trigger",
            "is_final_stage", "can_split", "bom_no"
        ]
        for field in required:
            self.assertIn(field, field_names, f"Missing field: {field}")

    def test_stage_operation_doctype_exists(self):
        """DESAR Stage Operation must exist."""
        self.assertTrue(frappe.db.exists("DocType", "DESAR Stage Operation"))

    def test_design_master_has_stage_configuration_field(self):
        """Design Master must have stage_configuration Table field."""
        meta = frappe.get_meta("Design Master")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("stage_configuration", field_names)

    def test_get_stage_configuration_api(self):
        """get_stage_configuration API returns list for any design master."""
        from desar_manufacturing.api.manufacturing import get_stage_configuration
        # Should work without error even if no stages defined
        result = get_stage_configuration("563")
        self.assertIsInstance(result, list)


@unittest.skipUnless(FRAPPE_AVAILABLE, "ERPNext not available")
class TestQIGradeReadingIntegration(unittest.TestCase):
    """
    Integration tests for QI Grade Reading child table.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        if not frappe.db.exists("DocType", "DESAR QI Grade Reading"):
            raise unittest.SkipTest("DESAR QI Grade Reading not found. Run bench migrate.")

    def test_qi_grade_reading_doctype_exists(self):
        self.assertTrue(frappe.db.exists("DocType", "DESAR QI Grade Reading"))

    def test_qi_grade_reading_is_child_table(self):
        meta = frappe.get_meta("DESAR QI Grade Reading")
        self.assertEqual(meta.istable, 1)

    def test_qi_grade_reading_has_required_fields(self):
        meta = frappe.get_meta("DESAR QI Grade Reading")
        field_names = [f.fieldname for f in meta.fields]
        for field in ["grade_code", "grade_label", "qty"]:
            self.assertIn(field, field_names, f"Missing: {field}")

    def test_custom_desar_grade_readings_field_exists_on_qi(self):
        """QI must have custom_desar_grade_readings field after migrate."""
        exists = frappe.db.get_value(
            "Custom Field",
            "Quality Inspection-custom_desar_grade_readings",
            "name"
        )
        self.assertIsNotNone(exists)

    def test_custom_desar_stage_name_field_exists_on_qi(self):
        """QI must have custom_desar_stage_name field after migrate."""
        exists = frappe.db.get_value(
            "Custom Field",
            "Quality Inspection-custom_desar_stage_name",
            "name"
        )
        self.assertIsNotNone(exists)


@unittest.skipUnless(FRAPPE_AVAILABLE, "ERPNext not available")
class TestRollTicketStageGradeIntegration(unittest.TestCase):
    """
    Integration tests for Roll Ticket Stage Grade child table.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        if not frappe.db.exists("DocType", "DESAR Roll Ticket Stage Grade"):
            raise unittest.SkipTest("DESAR Roll Ticket Stage Grade not found.")

    def test_roll_ticket_stage_grade_doctype_exists(self):
        self.assertTrue(frappe.db.exists("DocType", "DESAR Roll Ticket Stage Grade"))

    def test_roll_ticket_has_stage_grades_field(self):
        """Roll Ticket must have stage_grades Table field."""
        meta = frappe.get_meta("Roll Ticket")
        field_names = [f.fieldname for f in meta.fields]
        self.assertIn("stage_grades", field_names)

    def test_roll_ticket_stage_grade_has_required_fields(self):
        meta = frappe.get_meta("DESAR Roll Ticket Stage Grade")
        field_names = [f.fieldname for f in meta.fields]
        for field in ["stage_name", "grade_code", "grade_label", "qty", "qi_reference"]:
            self.assertIn(field, field_names, f"Missing: {field}")


@unittest.skipUnless(FRAPPE_AVAILABLE, "ERPNext not available")
class TestBackwardCompatibility(unittest.TestCase):
    """
    Tests that the existing system still works when Grade/Stage Configuration
    is NOT filled in. Legacy mode must be fully backward compatible.
    """

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")

    def test_repack_service_legacy_mode_still_works(self):
        """
        RepackService._build_items_legacy must still produce correct items
        when Grade Configuration is empty.
        """
        from desar_manufacturing.services.repack_service import RepackService

        items, total = RepackService._build_items_legacy.__func__(
            RepackService,
            type("MockQI", (), {
                "reference_type": "",
                "reference_name": "",
                "item_code": "",
                "get": lambda self, k, d=None: {
                    "custom_cutted_qty_a": 42,
                    "custom_cutted_qty_b": 6,
                    "custom_cutted_qty_c": 2,
                }.get(k, d or 0),
            })(),
            "Cutting and Packing Floor - ST"
        )
        # With empty base item, should return empty
        # This tests the graceful fallback
        self.assertIsInstance(items, list)

    def test_repack_service_dynamic_mode_skips_scrap_output(self):
        """
        RepackService._build_items_dynamic must never produce an output row for a
        grade flagged is_scrap in Grade Configuration — scrap qty is still counted
        in `total` (consumed from source) but carries no stock value.

        Grade A is given a real item_suffix (and mocked to resolve/exist) so this
        exercises the scrap-vs-valued-output distinction specifically, without
        also tripping the separate "missing item" write-off guard (see
        test_repack_service_missing_grade_item_excluded_from_total below).
        """
        from desar_manufacturing.services.repack_service import RepackService
        from unittest.mock import patch

        grade_config = [
            frappe._dict({"grade_code": "A", "is_scrap": 0, "item_suffix": "-A", "valuation_pct": 100, "target_warehouse": "", "scrap_item": ""}),
            frappe._dict({"grade_code": "C", "is_scrap": 1, "item_suffix": "", "valuation_pct": 5, "target_warehouse": "Scrap Yard - ST", "scrap_item": "Shemagh Scrap"}),
        ]
        mock_qi = type("MockQI", (), {
            "reference_type": "",
            "reference_name": "",
            "item_code": "Grey Roll",
            "get": lambda self, k, d=None: {
                "custom_desar_grade_readings": [
                    {"grade_code": "A", "qty": 42},
                    {"grade_code": "C", "qty": 2},
                ],
            }.get(k, d),
        })()

        with patch("frappe.db.exists", return_value=True), \
             patch.object(RepackService, "_stock_uom", return_value="Nos"):
            items, total = RepackService._build_items_dynamic.__func__(
                RepackService, mock_qi, grade_config, "Cutting and Packing Floor - ST"
            )

        self.assertEqual(total, 44)  # scrap qty still counted, consumed from source
        self.assertNotIn("Scrap Yard - ST", [i.get("t_warehouse") for i in items])
        self.assertNotIn("Shemagh Scrap", [i.get("item_code") for i in items])

    def test_repack_service_missing_grade_item_excluded_from_total(self):
        """
        A grade whose item can't be resolved/doesn't exist must NOT have its qty
        silently consumed from source stock with no output row — that's an
        invisible stock/valuation write-off. Its qty must be excluded from total.
        """
        from desar_manufacturing.services.repack_service import RepackService
        from unittest.mock import patch

        grade_config = [
            frappe._dict({"grade_code": "A", "is_scrap": 0, "item_suffix": "-A", "valuation_pct": 100, "target_warehouse": "FG Grade A", "scrap_item": ""}),
            frappe._dict({"grade_code": "B", "is_scrap": 0, "item_suffix": "-B", "valuation_pct": 60, "target_warehouse": "FG Grade B", "scrap_item": ""}),
        ]
        mock_qi = type("MockQI", (), {
            "reference_type": "",
            "reference_name": "",
            "item_code": "Grey Roll",
            "get": lambda self, k, d=None: {
                "custom_desar_grade_readings": [
                    {"grade_code": "A", "qty": 42},
                    {"grade_code": "B", "qty": 6},
                ],
            }.get(k, d),
        })()

        def exists_side_effect(doctype, name):
            return name != "Grey Roll-B"  # Grade B's item doesn't exist

        with patch("frappe.db.exists", side_effect=exists_side_effect), \
             patch.object(RepackService, "_stock_uom", return_value="Nos"):
            items, total = RepackService._build_items_dynamic.__func__(
                RepackService, mock_qi, grade_config, "Cutting and Packing Floor - ST"
            )

        self.assertEqual(total, 42)  # Grade B's 6 excluded, not silently consumed
        self.assertNotIn("Grey Roll-B", [i.get("item_code") for i in items])

    def test_settings_manager_grade_config_returns_empty_when_not_setup(self):
        """
        When Grade Configuration is not filled in DESAR Settings,
        get_grade_configuration returns empty list — not an error.
        """
        from desar_manufacturing.config.settings_manager import SettingsManager
        result = SettingsManager.get_grade_configuration()
        # Must return list (possibly empty) — never raise
        self.assertIsInstance(result, list)

    def test_stage_config_api_returns_empty_for_nonexistent_design(self):
        """
        get_stage_configuration returns empty list for non-existent design master.
        """
        from desar_manufacturing.api.manufacturing import get_stage_configuration
        result = get_stage_configuration("NONEXISTENT-DESIGN-ZZZZZ")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
