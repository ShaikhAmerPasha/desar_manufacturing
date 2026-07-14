"""
DESAR Manufacturing — P0 Hardening Tests

Covers three fixes, each exercised against the REAL service functions
(no logic reimplemented here):
  1. for_update=True locking on the 11 stage-transition entry points
  2. removal of mid-function frappe.db.commit() calls
  3. the 5 previously-silently-swallowed exception sites

Run with:
  bench --site <site> run-tests --app desar_manufacturing --module desar_manufacturing.tests.test_p0_hardening -v
"""
import unittest
from unittest.mock import patch, MagicMock

import frappe


class _StopAtLock(Exception):
    """Raised by the mocked frappe.get_doc to halt execution right after the lock call."""


# (module, function, args) for every function that must lock the Production Order.
LOCKED_ENTRY_POINTS = [
	("desar_manufacturing.services.roll_service", "start_grey_roll", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "complete_grey_roll", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "start_finished_roll", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "complete_finished_roll", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "start_packing", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "complete_packing", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "finalize_packing", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.roll_service", "complete_roll", ("PO-DUMMY", 1)),
	("desar_manufacturing.services.warping_service", "start_warping", ("PO-DUMMY",)),
	("desar_manufacturing.services.warping_service", "complete_warping", ("PO-DUMMY",)),
	("desar_manufacturing.services.warping_service", "split_beam", ("PO-DUMMY", [])),
]


class TestForUpdateLocking(unittest.TestCase):
	"""Every stage-transition entry point must lock the Production Order row."""

	def test_all_entry_points_pass_for_update(self):
		for module_path, fn_name, args in LOCKED_ENTRY_POINTS:
			with self.subTest(fn=fn_name):
				module = __import__(module_path, fromlist=[fn_name])
				fn = getattr(module, fn_name)

				captured = {}

				def fake_get_doc(*call_args, **call_kwargs):
					captured["args"] = call_args
					captured["kwargs"] = call_kwargs
					raise _StopAtLock()

				with patch("frappe.get_doc", side_effect=fake_get_doc):
					with self.assertRaises(_StopAtLock):
						fn(*args)

				self.assertEqual(captured["args"][0], "DESAR Production Order")
				self.assertTrue(
					captured["kwargs"].get("for_update"),
					f"{fn_name} did not pass for_update=True",
				)

	def test_refresh_roll_is_not_locked(self):
		"""refresh_roll is idempotent — intentionally not locked."""
		from desar_manufacturing.services.roll_service import refresh_roll

		captured = {}

		def fake_get_doc(*call_args, **call_kwargs):
			captured["kwargs"] = call_kwargs
			raise _StopAtLock()

		with patch("frappe.get_doc", side_effect=fake_get_doc):
			with self.assertRaises(_StopAtLock):
				refresh_roll("PO-DUMMY", 1)

		self.assertNotIn("for_update", captured["kwargs"])


class TestNoMidFunctionCommit(unittest.TestCase):
	"""_update_roll and the top-level service functions must never commit mid-flight."""

	def test_update_roll_does_not_commit(self):
		from desar_manufacturing.services.roll_service import _update_roll

		fake_roll = MagicMock()
		fake_roll.name = "RC-DUMMY"

		with patch("frappe.db.set_value") as mock_set_value, \
			patch("frappe.db.commit") as mock_commit:
			_update_roll(fake_roll, {"grey_roll_status": "In Progress"})

		mock_set_value.assert_called_once()
		mock_commit.assert_not_called()

	def test_no_commit_calls_left_in_hardened_service_files(self):
		"""Regression trip-wire: these files must stay commit-free."""
		import desar_manufacturing.services.roll_service as roll_service
		import desar_manufacturing.services.warping_service as warping_service
		import desar_manufacturing.services.production_plan_service as production_plan_service
		import desar_manufacturing.services.bom_service as bom_service
		import inspect

		for module in (roll_service, warping_service, production_plan_service, bom_service):
			source = inspect.getsource(module)
			self.assertNotIn(
				"frappe.db.commit()", source,
				f"{module.__name__} must not call frappe.db.commit() — rely on request-level commit",
			)


class TestCreateRollQIPropagates(unittest.TestCase):
	"""_create_roll_qi must let QI-creation failures propagate, not swallow them."""

	def test_failure_propagates(self):
		from desar_manufacturing.services.roll_service import _create_roll_qi

		fake_roll = MagicMock()
		fake_roll.roll_no = 1

		with patch(
			"desar_manufacturing.services.qi_service.make_roll_qi",
			side_effect=ValueError("boom"),
		):
			with self.assertRaises(ValueError):
				_create_roll_qi(po=None, roll=fake_roll, stage_name="Grey Roll", batch_no="B-1", work_order="WO-1")

	def test_success_still_returns_qi_name(self):
		from desar_manufacturing.services.roll_service import _create_roll_qi

		fake_qi = MagicMock()
		fake_qi.name = "QI-001"

		with patch(
			"desar_manufacturing.services.qi_service.make_roll_qi",
			return_value=fake_qi,
		):
			result = _create_roll_qi(po=None, roll=MagicMock(), stage_name="Grey Roll", batch_no="B-1", work_order="WO-1")

		self.assertEqual(result, "QI-001")


class TestRepackServiceSurfacesFailure(unittest.TestCase):
	"""create_from_final_qi must log + surface failures without alert=True (blocking, not a toast)."""

	def test_failure_surfaces_without_alert(self):
		from desar_manufacturing.services.repack_service import RepackService

		fake_qi = MagicMock()

		with patch("desar_manufacturing.config.settings_manager.SettingsManager.is_auto_repack_enabled", return_value=True), \
			patch("desar_manufacturing.config.settings_manager.SettingsManager.get_company", return_value="Standardtouch"), \
			patch("desar_manufacturing.config.settings_manager.SettingsManager.get_warehouse", return_value="WH-1"), \
			patch("desar_manufacturing.config.settings_manager.SettingsManager.get_grade_configuration", return_value=[]), \
			patch.object(RepackService, "_build_items_legacy", return_value=([{"item_code": "X", "qty": 1}], 1)), \
			patch("frappe.get_doc", side_effect=RuntimeError("insert failed")), \
			patch("frappe.log_error") as mock_log_error, \
			patch("frappe.msgprint") as mock_msgprint:

			result = RepackService.create_from_final_qi(fake_qi)

		self.assertIsNone(result)
		mock_log_error.assert_called_once()
		mock_msgprint.assert_called_once()
		self.assertNotIn("alert", mock_msgprint.call_args.kwargs)


class TestRollTicketServiceSurfacesFailure(unittest.TestCase):
	"""create_for_grey_roll must now show a visible msgprint on failure, not just log_error."""

	def test_failure_surfaces_via_msgprint(self):
		from desar_manufacturing.services.roll_ticket_service import RollTicketService

		with patch("desar_manufacturing.config.settings_manager.SettingsManager.is_auto_roll_ticket_enabled", return_value=True), \
			patch("desar_manufacturing.repositories.roll_ticket_repository.RollTicketRepository.exists_for_batch", return_value=False), \
			patch("desar_manufacturing.repositories.stock_entry_repository.StockEntryRepository.get_work_order", return_value=None), \
			patch("desar_manufacturing.repositories.stock_entry_repository.StockEntryRepository.get_consumed_beam_batch", return_value=None), \
			patch("desar_manufacturing.repositories.roll_ticket_repository.RollTicketRepository.create", side_effect=RuntimeError("db down")), \
			patch("frappe.log_error") as mock_log_error, \
			patch("frappe.msgprint") as mock_msgprint:

			result = RollTicketService.create_for_grey_roll(
				stock_entry_name="SE-DUMMY", batch_no="BATCH-DUMMY", qty=1,
			)

		self.assertIsNone(result)
		mock_log_error.assert_called_once()
		mock_msgprint.assert_called_once()
		self.assertEqual(mock_msgprint.call_args.kwargs.get("alert"), True)
		self.assertEqual(mock_msgprint.call_args.kwargs.get("indicator"), "orange")


class TestDeleteIfDraftLogsFailure(unittest.TestCase):
	"""delete_if_draft must log a failed delete instead of swallowing it silently."""

	def test_failed_delete_is_logged_not_raised(self):
		from desar_manufacturing.services.wo_split_helpers import delete_if_draft

		todo = frappe.get_doc({"doctype": "ToDo", "description": "P0 hardening test"})
		todo.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("ToDo", todo.name, force=True, ignore_permissions=True))

		with patch("frappe.delete_doc", side_effect=RuntimeError("locked")), \
			patch("frappe.log_error") as mock_log_error:
			delete_if_draft("ToDo", todo.name)

		mock_log_error.assert_called_once()


class TestQIReadingsTemplateFailureIsLogged(unittest.TestCase):
	"""The template-readings load in qi_service.make_roll_qi must log, not silently pass."""

	def test_no_bare_except_pass_remains(self):
		import inspect
		import desar_manufacturing.services.qi_service as qi_service

		source = inspect.getsource(qi_service)
		self.assertNotIn(
			"except Exception:\n\t\t\tpass", source,
			"qi_service must log template-load failures instead of silently passing",
		)
		self.assertIn("QI readings template load failed", source)
