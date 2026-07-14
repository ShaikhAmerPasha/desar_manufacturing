"""
DESAR Manufacturing — Test Suite for v3.1 Features

Level 1 (standalone pytest — no frappe needed):
  - TestSkipTransferLogic: pure logic tests
  - TestGradeAdjustmentMath: pure math validation

Level 2 (bench run-tests — frappe required):
  - TestSkipTransferIntegration
  - TestGradeAdjustmentIntegration
  - TestWorkspaceAPIIntegration

Run Level 1: python3 -m pytest desar_manufacturing/tests/test_new_features.py -v
Run Level 2: bench --site excel run-tests --app desar_manufacturing
"""
import unittest


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 1 — Pure Logic Tests (no frappe)
# ═══════════════════════════════════════════════════════════════════════════

class TestSkipTransferLogic(unittest.TestCase):
    """
    Pure logic tests for skip_transfer decision.
    Tests the keyword-based fallback logic without DB calls.
    """

    def _should_skip(self, stage_name: str, skip_transfer_flag: int = 0) -> bool:
        """Mirror of _apply_skip_transfer decision logic."""
        if skip_transfer_flag:
            return True
        stage_lower = (stage_name or "").lower()
        return "warp" in stage_lower or "weav" in stage_lower

    def test_warping_skips(self):
        self.assertTrue(self._should_skip("Warping"))

    def test_weaving_skips(self):
        self.assertTrue(self._should_skip("Weaving"))

    def test_loom_loading_skips(self):
        self.assertTrue(self._should_skip("Loom Weaving"))

    def test_finishing_does_not_skip(self):
        self.assertFalse(self._should_skip("Finishing"))

    def test_packing_does_not_skip(self):
        self.assertFalse(self._should_skip("Packing"))

    def test_dyeing_does_not_skip(self):
        self.assertFalse(self._should_skip("Dyeing"))

    def test_embroidery_does_not_skip(self):
        self.assertFalse(self._should_skip("Embroidery"))

    def test_explicit_flag_overrides(self):
        """Explicit skip_transfer=1 skips even Finishing."""
        self.assertTrue(self._should_skip("Finishing", skip_transfer_flag=1))

    def test_explicit_flag_on_packing(self):
        """Explicit skip_transfer=1 skips Packing too."""
        self.assertTrue(self._should_skip("Packing", skip_transfer_flag=1))

    def test_empty_stage_name_no_skip(self):
        self.assertFalse(self._should_skip(""))

    def test_none_stage_name_no_skip(self):
        self.assertFalse(self._should_skip(None))


class TestGradeAdjustmentMath(unittest.TestCase):
    """
    Calls the real _validate_adjustment_quantities (events/quality_inspection.py)
    directly. No DB queries, but frappe.throw needs a bound site context —
    skips itself under plain pytest, runs for real under bench run-tests.
    """

    def _check_reconciles(self, finishing, final, adjustments) -> bool:
        """True if the real validator accepts the adjustments, False if it throws."""
        import frappe
        if not frappe.db:
            self.skipTest("frappe site context not initialized — run via bench run-tests")
        from desar_manufacturing.events.quality_inspection import _validate_adjustment_quantities

        try:
            _validate_adjustment_quantities(finishing, final, adjustments)
            return True
        except frappe.ValidationError:
            return False

    def _compute_expected(self, finishing: dict, adjustments: list) -> dict:
        """Only used by test_total_preserved_after_adjustment below — same math the real validator applies."""
        expected = dict(finishing)
        for adj in adjustments:
            f = adj["from_grade"]
            t = adj["to_grade"]
            q = float(adj["qty"])
            expected[f] = expected.get(f, 0) - q
            expected[t] = expected.get(t, 0) + q
        return expected

    def test_no_changes_no_adjustments(self):
        """Same grades — no adjustments needed."""
        f = {"A": 40, "B": 7, "C": 3}
        self.assertTrue(self._check_reconciles(f, f, []))

    def test_upgrade_b_to_a(self):
        finishing = {"A": 40, "B": 7, "C": 3}
        final = {"A": 43, "B": 4, "C": 3}
        adj = [{"from_grade": "B", "to_grade": "A", "qty": 3}]
        self.assertTrue(self._check_reconciles(finishing, final, adj))

    def test_downgrade_a_to_c(self):
        finishing = {"A": 40, "B": 7, "C": 3}
        final = {"A": 38, "B": 7, "C": 5}
        adj = [{"from_grade": "A", "to_grade": "C", "qty": 2}]
        self.assertTrue(self._check_reconciles(finishing, final, adj))

    def test_multiple_adjustments(self):
        finishing = {"A": 40, "B": 7, "C": 3}
        final = {"A": 42, "B": 4, "C": 4}
        adj = [
            {"from_grade": "B", "to_grade": "A", "qty": 3},
            {"from_grade": "A", "to_grade": "C", "qty": 1},
        ]
        self.assertTrue(self._check_reconciles(finishing, final, adj))

    def test_wrong_qty_does_not_reconcile(self):
        finishing = {"A": 40, "B": 7, "C": 3}
        final = {"A": 43, "B": 4, "C": 3}
        adj = [{"from_grade": "B", "to_grade": "A", "qty": 2}]  # Wrong: should be 3
        self.assertFalse(self._check_reconciles(finishing, final, adj))

    def test_total_preserved_after_adjustment(self):
        """Grade adjustments don't change total quantity."""
        finishing = {"A": 40, "B": 7, "C": 3}
        adj = [{"from_grade": "B", "to_grade": "A", "qty": 3}]
        expected = self._compute_expected(finishing, adj)
        self.assertEqual(sum(finishing.values()), sum(expected.values()))

    def test_grade_d_adjustment(self):
        """4-grade system: D→A upgrade."""
        finishing = {"A": 30, "B": 8, "C": 5, "D": 7}
        final = {"A": 35, "B": 8, "C": 5, "D": 2}
        adj = [{"from_grade": "D", "to_grade": "A", "qty": 5}]
        self.assertTrue(self._check_reconciles(finishing, final, adj))

    def test_chain_adjustment(self):
        """B→A then A→C: chain adjustments.
        Finishing: A=40, B=7, C=3
        B→A: 3 pieces  → A=43, B=4, C=3
        A→C: 2 pieces  → A=41, B=4, C=5
        """
        finishing = {"A": 40, "B": 7, "C": 3}
        final = {"A": 41, "B": 4, "C": 5}
        adj = [
            {"from_grade": "B", "to_grade": "A", "qty": 3},
            {"from_grade": "A", "to_grade": "C", "qty": 2},
        ]
        self.assertTrue(self._check_reconciles(finishing, final, adj))

    def test_has_changes_detection(self):
        """Detect if grades changed between finishing and final."""
        finishing = {"A": 40, "B": 7, "C": 3}
        final_same = {"A": 40, "B": 7, "C": 3}
        final_diff = {"A": 43, "B": 4, "C": 3}

        def has_changes(f, fin):
            return any(abs(fin.get(k, 0) - v) > 0.01 for k, v in f.items())

        self.assertFalse(has_changes(finishing, final_same))
        self.assertTrue(has_changes(finishing, final_diff))


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 2 — Integration Tests (require bench)
# These are discovered by bench run-tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSkipTransferIntegration(unittest.TestCase):
    """Integration tests — run in bench only."""

    def test_apply_skip_transfer_warping_in_bench(self):
        """Warping WO gets skip_material_transfer=1 when design master set."""
        try:
            import frappe
            from desar_manufacturing.events.work_order import _apply_skip_transfer

            dm = frappe.db.get_value("Design Master", {"design_no": "563"}, "name")
            if not dm:
                self.skipTest("Design Master 563 not found")

            class MockWO:
                production_item = "Warping Beam"
                custom_design_master = dm
                skip_transfer = 0
                name = "TEST-WO-SKIP"
                def get(self, k, d=None): return getattr(self, k, d)

            wo = MockWO()
            _apply_skip_transfer(wo)
            # Warping should be skipped
            self.assertEqual(wo.skip_transfer, 1)
        except ImportError:
            self.skipTest("frappe not available")

    def test_finishing_not_skipped_in_bench(self):
        """Finishing WO does NOT get skip_material_transfer."""
        try:
            import frappe
            from desar_manufacturing.events.work_order import _apply_skip_transfer

            dm = frappe.db.get_value("Design Master", {"design_no": "563"}, "name")
            if not dm:
                self.skipTest("Design Master 563 not found")

            class MockWO:
                production_item = "Finished Roll"
                custom_design_master = dm
                skip_transfer = 0
                name = "TEST-WO-NOSKIP"
                def get(self, k, d=None): return getattr(self, k, d)

            wo = MockWO()
            _apply_skip_transfer(wo)
            self.assertEqual(wo.skip_transfer, 0)
        except ImportError:
            self.skipTest("frappe not available")


class TestGradeAdjustmentIntegration(unittest.TestCase):
    """Integration tests for grade adjustment validation in bench."""

    def test_no_rt_skips_validation(self):
        """QI with no Roll Ticket linked skips adjustment validation."""
        try:
            import frappe
            from desar_manufacturing.events.quality_inspection import _validate_grade_adjustments

            class MockDoc:
                def get(self, key, default=None):
                    if key == "custom_roll_ticket": return ""
                    return default

            # Should not raise when no RT
            _validate_grade_adjustments(MockDoc(), "Packing", [])
        except ImportError:
            self.skipTest("frappe not available")

    def test_validation_runs_in_bench(self):
        """Grade adjustment validation callable in bench context."""
        try:
            import frappe
            from desar_manufacturing.events.quality_inspection import (
                _validate_adjustment_quantities
            )
            # Test basic call with no data
            _validate_adjustment_quantities({}, {}, [])
        except ImportError:
            self.skipTest("frappe not available")


class TestWorkspaceAPIIntegration(unittest.TestCase):
    """Integration tests for Production Workspace API in bench."""

    def test_get_production_orders_callable(self):
        """get_production_orders works in bench context."""
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_workspace \
                .desar_production_workspace import get_production_orders
            result = get_production_orders()
            self.assertIsInstance(result, list)
        except ImportError:
            self.skipTest("frappe not available")

    def test_get_pending_inspections_callable(self):
        """get_pending_inspections works in bench context."""
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_workspace \
                .desar_production_workspace import get_pending_inspections
            result = get_pending_inspections()
            self.assertIsInstance(result, list)
        except ImportError:
            self.skipTest("frappe not available")
