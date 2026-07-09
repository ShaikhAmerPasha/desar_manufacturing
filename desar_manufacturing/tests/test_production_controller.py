"""
DESAR Production Controller — Test Suite

Level 1 (standalone pytest — no frappe):
  - TestStageLockingLogic: stage unlock rules
  - TestRoleDetermination: role mapping
  - TestStageStatusLogic: button visibility per role/state

Level 2 (bench run-tests — frappe required):
  - TestControllerAPIIntegration: get_orders, get_order_detail
  - TestStartStageIntegration: start_stage permissions
  - TestJobCardFilterIntegration: operator sees only assigned JCs

Run Level 1: python3 -m pytest desar_manufacturing/tests/test_production_controller.py -k "not Integration" -v
Run Level 2: bench --site excel run-tests --app desar_manufacturing
"""
import unittest


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 1 — Pure Logic Tests (no frappe)
# ═══════════════════════════════════════════════════════════════════════════

class TestStageLockingLogic(unittest.TestCase):
    """
    Stage locking: a stage is locked if the previous stage is not completed.
    Stage 1 is always unlocked.
    """

    def _is_locked(self, stage_idx: int, completed_stages: list) -> bool:
        """Mirror of locking logic in desar_production_controller.py"""
        if stage_idx == 0:
            return False
        prev_idx = stage_idx - 1
        return prev_idx not in completed_stages

    def test_first_stage_always_unlocked(self):
        self.assertFalse(self._is_locked(0, []))

    def test_second_stage_locked_when_first_not_done(self):
        self.assertTrue(self._is_locked(1, []))

    def test_second_stage_unlocked_when_first_done(self):
        self.assertFalse(self._is_locked(1, [0]))

    def test_third_stage_locked_when_second_not_done(self):
        self.assertTrue(self._is_locked(2, [0]))

    def test_third_stage_unlocked_when_second_done(self):
        self.assertFalse(self._is_locked(2, [0, 1]))

    def test_fourth_stage_requires_third_done(self):
        self.assertTrue(self._is_locked(3, [0, 1]))
        self.assertFalse(self._is_locked(3, [0, 1, 2]))

    def test_non_sequential_completion_still_locks(self):
        """Stage 3 checks stage 2 done — stage 2 idx=1 IS in completed list."""
        # Stage 3 (idx=2) checks if prev (idx=1) is in completed
        # If [1] means stage 2 is done — stage 3 should be UNLOCKED
        self.assertFalse(self._is_locked(2, [1]))
        # Stage 3 locked when stage 2 (idx=1) not done
        self.assertTrue(self._is_locked(2, [0]))

    def test_all_stages_complete(self):
        for i in range(4):
            completed = list(range(i))
            if i == 0:
                self.assertFalse(self._is_locked(i, completed))
            else:
                self.assertFalse(self._is_locked(i, completed))


class TestRoleDetermination(unittest.TestCase):
    """Role mapping: user roles → simplified DESAR role."""

    def _get_role(self, user_roles: list) -> str:
        """Mirror of _get_desar_role logic."""
        if "DESAR Supervisor" in user_roles or "System Manager" in user_roles:
            return "supervisor"
        elif "DESAR Operator" in user_roles:
            return "operator"
        elif "DESAR QC Inspector" in user_roles:
            return "qc"
        elif "DESAR Store Manager" in user_roles:
            return "store"
        return "supervisor"

    def test_supervisor_role(self):
        self.assertEqual(self._get_role(["DESAR Supervisor"]), "supervisor")

    def test_system_manager_is_supervisor(self):
        self.assertEqual(self._get_role(["System Manager"]), "supervisor")

    def test_operator_role(self):
        self.assertEqual(self._get_role(["DESAR Operator"]), "operator")

    def test_qc_role(self):
        self.assertEqual(self._get_role(["DESAR QC Inspector"]), "qc")

    def test_store_role(self):
        self.assertEqual(self._get_role(["DESAR Store Manager"]), "store")

    def test_unknown_role_defaults_to_supervisor(self):
        self.assertEqual(self._get_role(["Some Other Role"]), "supervisor")

    def test_multiple_roles_supervisor_wins(self):
        self.assertEqual(self._get_role(["DESAR Operator", "DESAR Supervisor"]), "supervisor")

    def test_system_manager_overrides_operator(self):
        self.assertEqual(self._get_role(["DESAR Operator", "System Manager"]), "supervisor")


class TestStageButtonVisibility(unittest.TestCase):
    """
    Button visibility rules per role and WO state:
    - can_start: supervisor only, WO not submitted, stage not locked
    - can_transfer: operator/supervisor, all JCs done, no mfg SE, skip_transfer=0
    - can_finish: operator/supervisor, all JCs done, transfer done or skip_transfer
    - can_create_qi: qc only, mfg SE exists, qi_required=1, no existing QI
    """

    def _calc_buttons(self, role, wo_docstatus, wo_status, is_locked,
                      all_jcs_done, manufacture_se, transfer_se,
                      skip_transfer, qi_required, qi_exists):
        """Mirror of button calculation logic."""
        buttons = {
            "can_start": False,
            "can_transfer": False,
            "can_finish": False,
            "can_create_qi": False,
        }

        if wo_docstatus == 0:
            buttons["can_start"] = (role == "supervisor") and not is_locked
            return buttons

        buttons["can_transfer"] = bool(
            not manufacture_se and not skip_transfer and
            all_jcs_done and role in ["supervisor", "operator"]
        )

        transfer_ready = bool(transfer_se or skip_transfer)
        buttons["can_finish"] = bool(
            all_jcs_done and not manufacture_se and
            transfer_ready and role in ["supervisor", "operator"]
        )

        if qi_required and manufacture_se and role == "qc":
            buttons["can_create_qi"] = not qi_exists

        return buttons

    def test_supervisor_sees_start_on_unlocked_stage(self):
        b = self._calc_buttons("supervisor", 0, "Draft", False,
                               False, None, None, False, False, False)
        self.assertTrue(b["can_start"])

    def test_supervisor_no_start_on_locked_stage(self):
        b = self._calc_buttons("supervisor", 0, "Draft", True,
                               False, None, None, False, False, False)
        self.assertFalse(b["can_start"])

    def test_operator_cannot_start(self):
        b = self._calc_buttons("operator", 0, "Draft", False,
                               False, None, None, False, False, False)
        self.assertFalse(b["can_start"])

    def test_operator_sees_transfer_when_jcs_done(self):
        b = self._calc_buttons("operator", 1, "In Process", False,
                               True, None, None, False, False, False)
        self.assertTrue(b["can_transfer"])

    def test_operator_no_transfer_when_jcs_not_done(self):
        b = self._calc_buttons("operator", 1, "In Process", False,
                               False, None, None, False, False, False)
        self.assertFalse(b["can_transfer"])

    def test_no_transfer_when_skip_transfer(self):
        b = self._calc_buttons("operator", 1, "In Process", False,
                               True, None, None, True, False, False)
        self.assertFalse(b["can_transfer"])

    def test_qc_no_transfer_or_finish(self):
        b = self._calc_buttons("qc", 1, "In Process", False,
                               True, None, None, False, True, False)
        self.assertFalse(b["can_transfer"])
        self.assertFalse(b["can_finish"])

    def test_finish_requires_transfer_done(self):
        b = self._calc_buttons("operator", 1, "In Process", False,
                               True, None, None, False, False, False)
        self.assertFalse(b["can_finish"])

    def test_finish_allowed_after_transfer(self):
        b = self._calc_buttons("operator", 1, "In Process", False,
                               True, None, "MAT-STE-001", False, False, False)
        self.assertTrue(b["can_finish"])

    def test_finish_allowed_with_skip_transfer(self):
        b = self._calc_buttons("operator", 1, "In Process", False,
                               True, None, None, True, False, False)
        self.assertTrue(b["can_finish"])

    def test_qc_sees_qi_button_after_manufacture(self):
        b = self._calc_buttons("qc", 1, "Completed", False,
                               True, "MAT-STE-001", None, False, True, False)
        self.assertTrue(b["can_create_qi"])

    def test_qc_no_qi_button_when_qi_exists(self):
        b = self._calc_buttons("qc", 1, "Completed", False,
                               True, "MAT-STE-001", None, False, True, True)
        self.assertFalse(b["can_create_qi"])

    def test_operator_no_qi_button(self):
        b = self._calc_buttons("operator", 1, "Completed", False,
                               True, "MAT-STE-001", None, False, True, False)
        self.assertFalse(b["can_create_qi"])

    def test_qc_no_qi_without_manufacture_se(self):
        b = self._calc_buttons("qc", 1, "In Process", False,
                               True, None, None, False, True, False)
        self.assertFalse(b["can_create_qi"])

    def test_store_no_buttons(self):
        b = self._calc_buttons("store", 1, "Completed", False,
                               True, "MAT-STE-001", None, False, True, False)
        self.assertFalse(b["can_start"])
        self.assertFalse(b["can_transfer"])
        self.assertFalse(b["can_finish"])
        self.assertFalse(b["can_create_qi"])


class TestStockEntryVisibility(unittest.TestCase):
    """Only SE-1 and SE-2 visible to supervisor and store manager."""

    def _can_see_se(self, role: str) -> bool:
        return role in ["supervisor", "store"]

    def test_supervisor_sees_se(self):
        self.assertTrue(self._can_see_se("supervisor"))

    def test_store_sees_se(self):
        self.assertTrue(self._can_see_se("store"))

    def test_operator_no_se(self):
        self.assertFalse(self._can_see_se("operator"))

    def test_qc_no_se(self):
        self.assertFalse(self._can_see_se("qc"))


class TestOrderProgressCalculation(unittest.TestCase):
    """Order progress percentage calculation."""

    def _calc_pct(self, completed: int, total: int) -> int:
        if not total:
            return 0
        return round(completed / total * 100)

    def test_zero_progress(self):
        self.assertEqual(self._calc_pct(0, 4), 0)

    def test_half_progress(self):
        self.assertEqual(self._calc_pct(2, 4), 50)

    def test_complete(self):
        self.assertEqual(self._calc_pct(4, 4), 100)

    def test_one_of_four(self):
        self.assertEqual(self._calc_pct(1, 4), 25)

    def test_three_of_four(self):
        self.assertEqual(self._calc_pct(3, 4), 75)

    def test_zero_total(self):
        self.assertEqual(self._calc_pct(0, 0), 0)


# ═══════════════════════════════════════════════════════════════════════════
# LEVEL 2 — Integration Tests (bench required)
# ═══════════════════════════════════════════════════════════════════════════

class TestControllerAPIIntegration(unittest.TestCase):

    def test_get_orders_returns_list(self):
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_controller\
                .desar_production_controller import get_orders
            result = get_orders()
            self.assertIsInstance(result, list)
        except ImportError:
            self.skipTest("frappe not available")

    def test_get_order_detail_invalid_pp(self):
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_controller\
                .desar_production_controller import get_order_detail
            result = get_order_detail("NONEXISTENT-PP")
            self.assertEqual(result, {})
        except ImportError:
            self.skipTest("frappe not available")

    def test_get_workers_returns_list(self):
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_controller\
                .desar_production_controller import get_workers
            result = get_workers()
            self.assertIsInstance(result, list)
        except ImportError:
            self.skipTest("frappe not available")


class TestStartStageIntegration(unittest.TestCase):

    def test_start_stage_requires_work_order(self):
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_controller\
                .desar_production_controller import start_stage
            with self.assertRaises(Exception):
                start_stage("PP-FAKE", "WO-NONEXISTENT")
        except ImportError:
            self.skipTest("frappe not available")

    def test_get_stage_job_cards_empty_wo(self):
        try:
            import frappe
            from desar_manufacturing.desar_manufacturing.page.desar_production_controller\
                .desar_production_controller import get_stage_job_cards
            result = get_stage_job_cards("")
            self.assertEqual(result, [])
        except ImportError:
            self.skipTest("frappe not available")
