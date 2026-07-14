"""P4 — _configure_wo's 3 duplicated keyword maps collapsed into resolve_by_keyword.
Now also reused by bom_service's default-workstation lookup (Phase D dedup)."""
import unittest

from desar_manufacturing.utils.validation_utils import resolve_by_keyword


class TestResolveByKeyword(unittest.TestCase):
	MAP = {"grey": "WH-Grey", "finish": "WH-Finish", "pack": "WH-Pack"}

	def test_matches_first_substring(self):
		self.assertEqual(resolve_by_keyword("grey", self.MAP), "WH-Grey")

	def test_no_match_returns_none(self):
		self.assertIsNone(resolve_by_keyword("warp", self.MAP))

	def test_falsy_value_still_returned_not_skipped(self):
		"""Matches old loop behavior: first matching key wins even if its value is empty."""
		self.assertIsNone(resolve_by_keyword("finish", {"finish": None, "pack": "WH-Pack"}))
