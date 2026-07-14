"""P1 — role checks on api/production_order.py and api/manufacturing.py whitelisted RPC methods."""
import unittest
from unittest.mock import patch

import desar_manufacturing.api.production_order as api
import desar_manufacturing.api.manufacturing as mfg_api


class _Stop(Exception):
	pass


CALLS = [
	("preview_plan", ("PP-1",), api.CREATE_ROLES),
	("create_desar_po", ("PP-1",), api.CREATE_ROLES),
	("start_warping", ("PO-1",), api.MUTATE_ROLES),
	("complete_warping", ("PO-1",), api.MUTATE_ROLES),
	("split_beam", ("PO-1", []), api.MUTATE_ROLES),
	("start_grey_roll", ("PO-1", 1), api.MUTATE_ROLES),
	("complete_grey_roll", ("PO-1", 1), api.MUTATE_ROLES),
	("start_finished_roll", ("PO-1", 1), api.MUTATE_ROLES),
	("complete_finished_roll", ("PO-1", 1), api.MUTATE_ROLES),
	("start_packing", ("PO-1", 1), api.MUTATE_ROLES),
	("complete_packing", ("PO-1", 1), api.MUTATE_ROLES),
	("finalize_packing", ("PO-1", 1), api.MUTATE_ROLES),
	("complete_roll", ("PO-1", 1), api.MUTATE_ROLES),
	("refresh_roll", ("PO-1", 1), api.MUTATE_ROLES),
]


class TestRoleChecks(unittest.TestCase):
	def test_every_endpoint_checks_roles_before_doing_anything(self):
		for fn_name, args, expected_roles in CALLS:
			with self.subTest(fn=fn_name):
				fn = getattr(api, fn_name)
				with patch("frappe.only_for", side_effect=_Stop) as mock_only_for, \
					patch.object(api, "_safe") as mock_safe:
					with self.assertRaises(_Stop):
						fn(*args)
				mock_only_for.assert_called_once_with(expected_roles)
				mock_safe.assert_not_called()


MFG_CALLS = [
	("finish_work_order", ("WO-1",)),
	("create_transfer_se", ("WO-1",)),
]


class TestManufacturingApiRoleChecks(unittest.TestCase):
	"""The two real mutating endpoints in api/manufacturing.py that had zero role checks."""

	def test_checks_roles_before_doing_anything(self):
		for fn_name, args in MFG_CALLS:
			with self.subTest(fn=fn_name):
				fn = getattr(mfg_api, fn_name)
				with patch("frappe.only_for", side_effect=_Stop) as mock_only_for, \
					patch("frappe.get_doc") as mock_get_doc:
					with self.assertRaises(_Stop):
						fn(*args)
				mock_only_for.assert_called_once_with(api.MUTATE_ROLES)
				mock_get_doc.assert_not_called()
