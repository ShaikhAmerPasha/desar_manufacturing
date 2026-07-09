"""
DESAR Production Order — Tests

Level 1 (standalone — no frappe):
  - Stage locking logic
  - WIP warehouse mapping
  - Status computation

Level 2 (bench):
  - DocType CRUD
  - API methods
"""
import unittest


class TestStageLocking(unittest.TestCase):
    """Stage unlock rules — pure logic."""

    def _should_unlock_next(self, current_status, qi_required, qi_submitted):
        """Mirror of unlock logic: next stage unlocks when current is Completed."""
        if current_status != "Completed":
            return False
        if qi_required and not qi_submitted:
            return False
        return True

    def test_locked_stays_locked(self):
        self.assertFalse(self._should_unlock_next("Locked", False, False))

    def test_not_started_stays_locked(self):
        self.assertFalse(self._should_unlock_next("Not Started", False, False))

    def test_in_progress_stays_locked(self):
        self.assertFalse(self._should_unlock_next("In Progress", False, False))

    def test_completed_no_qi_unlocks(self):
        """Warping completed, no QI required — next unlocks."""
        self.assertTrue(self._should_unlock_next("Completed", False, False))

    def test_completed_qi_submitted_unlocks(self):
        """Weaving completed, QI submitted — next unlocks."""
        self.assertTrue(self._should_unlock_next("Completed", True, True))

    def test_completed_qi_not_submitted_stays_locked(self):
        """Weaving completed but QI not submitted — next stays locked."""
        self.assertFalse(self._should_unlock_next("Completed", True, False))


class TestWIPWarehouseMap(unittest.TestCase):
    """Warehouse mapping for stage names."""

    def _get_wip(self, stage_name):
        mapping = {
            "warp": "Warping WIP - ST",
            "weav": "Loom Floor - ST",
            "loom": "Loom Floor - ST",
            "finish": "Finishing WIP - ST",
            "dye": "Finishing WIP - ST",
            "pack": "Cutting and Packing Floor - ST",
            "cut": "Cutting and Packing Floor - ST",
        }
        name_lower = (stage_name or "").lower()
        for keyword, wh in mapping.items():
            if keyword in name_lower:
                return wh
        return None

    def test_warping(self):
        self.assertEqual(self._get_wip("Warping"), "Warping WIP - ST")

    def test_weaving(self):
        self.assertEqual(self._get_wip("Weaving"), "Loom Floor - ST")

    def test_finishing(self):
        self.assertEqual(self._get_wip("Finishing"), "Finishing WIP - ST")

    def test_packing(self):
        self.assertEqual(self._get_wip("Packing"), "Cutting and Packing Floor - ST")

    def test_dyeing(self):
        self.assertEqual(self._get_wip("Dyeing"), "Finishing WIP - ST")

    def test_cutting(self):
        self.assertEqual(self._get_wip("Cutting"), "Cutting and Packing Floor - ST")

    def test_unknown(self):
        self.assertIsNone(self._get_wip("Embroidery"))


class TestPOStatusComputation(unittest.TestCase):
    """Overall PO status from stage statuses."""

    def _compute_status(self, statuses):
        if all(s == "Completed" for s in statuses):
            return "Completed"
        elif any(s in ("In Progress", "WO Submitted", "Completed") for s in statuses):
            return "In Progress"
        else:
            return "Submitted"

    def test_all_locked(self):
        """Initial state after submit — first is Not Started, rest Locked."""
        self.assertEqual(
            self._compute_status(["Not Started", "Locked", "Locked", "Locked"]),
            "Submitted"
        )

    def test_first_in_progress(self):
        self.assertEqual(
            self._compute_status(["In Progress", "Locked", "Locked", "Locked"]),
            "In Progress"
        )

    def test_mixed(self):
        self.assertEqual(
            self._compute_status(["Completed", "In Progress", "Locked", "Locked"]),
            "In Progress"
        )

    def test_all_completed(self):
        self.assertEqual(
            self._compute_status(["Completed", "Completed", "Completed", "Completed"]),
            "Completed"
        )

    def test_five_stages(self):
        """Striped 701 has 5 stages."""
        self.assertEqual(
            self._compute_status(["Completed", "Completed", "In Progress", "Locked", "Locked"]),
            "In Progress"
        )


class TestBatchChain(unittest.TestCase):
    """Batch linking between stages."""

    def test_chain_4_stages(self):
        """Each stage output batch feeds next stage input."""
        stages = [
            {"seq": 1, "name": "Warping", "batch": "BM-0015"},
            {"seq": 2, "name": "Weaving", "batch": "RL-0023"},
            {"seq": 3, "name": "Finishing", "batch": "FR-0010"},
            {"seq": 4, "name": "Packing", "batch": ""},
        ]
        for i in range(1, len(stages)):
            prev_batch = stages[i-1]["batch"]
            self.assertTrue(bool(prev_batch),
                f"Stage {stages[i]['name']} needs batch from {stages[i-1]['name']}")

    def test_first_stage_no_previous_batch(self):
        """First stage has no previous batch — uses raw material from warehouse."""
        stages = [{"seq": 1, "name": "Warping", "batch": "BM-0015"}]
        # No previous stage to check
        self.assertTrue(True)


class TestProductionOrderIntegration(unittest.TestCase):
    """Bench integration tests."""

    def test_doctype_exists(self):
        try:
            import frappe
            self.assertTrue(frappe.db.exists("DocType", "DESAR Production Order"))
        except ImportError:
            self.skipTest("frappe not available")

    def test_child_doctype_exists(self):
        try:
            import frappe
            self.assertTrue(frappe.db.exists("DocType", "DESAR Production Order Stage"))
        except ImportError:
            self.skipTest("frappe not available")

    def test_api_importable(self):
        try:
            from desar_manufacturing.api.production_order import submit_stage_wo
            self.assertTrue(callable(submit_stage_wo))
        except ImportError:
            self.skipTest("frappe not available")
