"""
DESAR Production Order — current_stage (bottleneck stage, list-view clarity).

Calls the real _compute_current_stage directly — pure logic over plain
attributes, no DB needed.
"""
import unittest
from unittest.mock import MagicMock

import frappe
from desar_manufacturing.services.roll_service import _compute_current_stage, refresh_po_status


def _roll(grey="Completed", finished="Completed", packing="Completed"):
    return frappe._dict({
        "grey_roll_status": grey, "finished_roll_status": finished, "packing_status": packing,
    })


class TestCurrentStageBeforeRolls(unittest.TestCase):
    def test_warping_in_progress(self):
        po = frappe._dict({"warping_status": "In Progress", "beam_split_status": "Not Started"})
        self.assertEqual(_compute_current_stage(po, []), "Warping")

    def test_warping_done_beam_split_pending(self):
        po = frappe._dict({"warping_status": "Completed", "beam_split_status": "Not Started"})
        self.assertEqual(_compute_current_stage(po, []), "Beam Split")


class TestCurrentStageSingleRoll(unittest.TestCase):
    def _po(self):
        return frappe._dict({"warping_status": "Completed", "beam_split_status": "Completed"})

    def test_at_grey_roll(self):
        rolls = [_roll(grey="In Progress")]
        self.assertEqual(_compute_current_stage(self._po(), rolls), "Grey Roll (1/1 rolls)")

    def test_at_packing(self):
        rolls = [_roll(packing="Not Started")]
        self.assertEqual(_compute_current_stage(self._po(), rolls), "Packing (1/1 rolls)")

    def test_fully_completed(self):
        rolls = [_roll()]
        self.assertEqual(_compute_current_stage(self._po(), rolls), "Completed")


class TestCurrentStageMultipleRolls(unittest.TestCase):
    def _po(self):
        return frappe._dict({"warping_status": "Completed", "beam_split_status": "Completed"})

    def test_bottleneck_is_earliest_incomplete_stage_not_majority(self):
        """3 rolls at Packing, 2 stuck at Grey Roll — must report the stuck
        ones (bottleneck), not the majority (Packing)."""
        rolls = [
            _roll(packing="Not Started"), _roll(packing="Not Started"), _roll(packing="Not Started"),
            _roll(grey="In Progress"), _roll(grey="Not Started"),
        ]
        self.assertEqual(_compute_current_stage(self._po(), rolls), "Grey Roll (2/5 rolls)")

    def test_all_at_finished_roll(self):
        rolls = [_roll(finished="In Progress"), _roll(finished="Not Started")]
        self.assertEqual(_compute_current_stage(self._po(), rolls), "Finished Roll (2/2 rolls)")

    def test_all_rolls_completed_reports_completed(self):
        rolls = [_roll(), _roll(), _roll()]
        self.assertEqual(_compute_current_stage(self._po(), rolls), "Completed")


def _mock_po(warping_status, beam_split_status, status, roll_chains=None, current_stage=None):
    po = MagicMock()
    po.reload = MagicMock()
    po.warping_status = warping_status
    po.beam_split_status = beam_split_status
    po.status = status
    po.current_stage = current_stage
    po.roll_chains = roll_chains or []
    return po


class TestRefreshPoStatusBeforeRolls(unittest.TestCase):
    """Regression: status previously stuck at 'Submitted' forever whenever
    no roll existed yet (Warping/Beam Split phase), because the function
    returned early before computing `status` at all."""

    def test_warping_in_progress_updates_status(self):
        po = _mock_po("In Progress", "Not Started", "Submitted")
        refresh_po_status(po)
        po.db_set.assert_any_call("status", "In Progress", update_modified=True)

    def test_warping_completed_beam_split_pending_is_in_progress(self):
        po = _mock_po("Completed", "Not Started", "Submitted")
        refresh_po_status(po)
        po.db_set.assert_any_call("status", "In Progress", update_modified=True)

    def test_warping_not_started_stays_submitted_no_write(self):
        po = _mock_po("Not Started", "Not Started", "Submitted")
        refresh_po_status(po)
        for call in po.db_set.call_args_list:
            self.assertNotEqual(call.args[0], "status")


class TestRefreshPoStatusWithRolls(unittest.TestCase):
    def test_all_rolls_completed_but_beam_split_not_flagged_is_in_progress(self):
        """Guards the bool(rolls) fix: an empty-rolls vacuous True must not
        leak into a real Completed verdict when rolls do exist but aren't done."""
        rolls = [_roll_status("In Progress")]
        po = _mock_po("Completed", "Completed", "In Progress", roll_chains=rolls)
        refresh_po_status(po)
        for call in po.db_set.call_args_list:
            if call.args[0] == "status":
                self.assertEqual(call.args[1], "In Progress")

    def test_fully_completed_writes_completed(self):
        rolls = [_roll_status("Completed"), _roll_status("Completed")]
        po = _mock_po("Completed", "Completed", "In Progress", roll_chains=rolls)
        refresh_po_status(po)
        po.db_set.assert_any_call("status", "Completed", update_modified=True)


def _roll_status(roll_status):
    return frappe._dict({
        "roll_status": roll_status,
        "grey_roll_status": "Completed", "finished_roll_status": "Completed", "packing_status": "Completed",
    })
