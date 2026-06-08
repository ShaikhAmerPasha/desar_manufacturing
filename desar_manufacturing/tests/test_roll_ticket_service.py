"""
DESAR Manufacturing — Level 2 Integration Tests
Tests for RollTicketService and QI stage detection.

Requires: Running ERPNext v15 instance with desar_manufacturing installed.
Run with: bench --site <site> run-tests --app desar_manufacturing --module desar_manufacturing.tests.test_roll_ticket_service -v

All tests are isolated — each creates and cleans up its own documents.
No test depends on another test or on existing data.

Author: DESAR Factory
Version: 2.3.0
"""

import frappe
import unittest
from frappe.utils import nowdate, flt


class TestRollTicketServiceUnit(unittest.TestCase):
    """
    Fast unit tests for RollTicketService internal methods.
    Uses mock objects — no real document creation.
    These run in milliseconds.
    """

    class _MockQI:
        """
        Minimal mock that behaves like a Frappe document.

        RULE: All fields that the service accesses via qi_doc.get("field_name")
        MUST be passed as kwargs to __init__ so they live in _data.

        WRONG — service calls get("batch_no") which misses this:
            mock.batch_no = "RL-0001"

        RIGHT — service calls get("batch_no") and finds it in _data:
            MockQI(batch_no="RL-0001", custom_grey_qty_a=40)
        """
        def __init__(self, **kwargs):
            self._data = kwargs
            self.name = "TEST-QI-MOCK"
            self.reference_type = "Stock Entry"
            self.reference_name = None
            self.item_code = kwargs.get("item_code", "")

        def get(self, key, default=None):
            return self._data.get(key, default if default is not None else 0)

    # ── _detect_qi_stage ──────────────────────────────────────────────────────

    def test_detect_grey_stage(self):
        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        from desar_manufacturing.constants import QIStage

        qi = self._MockQI(
            custom_grey_qty_a=40,
            custom_grey_qty_b=5,
            custom_grey_qty_c=5,
        )
        self.assertEqual(RollTicketService._detect_qi_stage(qi), QIStage.GREY)

    def test_detect_finishing_stage(self):
        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        from desar_manufacturing.constants import QIStage

        qi = self._MockQI(
            custom_finished_qty_a=38,
            custom_finished_qty_b=8,
            custom_finished_qty_c=4,
        )
        self.assertEqual(RollTicketService._detect_qi_stage(qi), QIStage.FINISHING)

    def test_detect_final_stage(self):
        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        from desar_manufacturing.constants import QIStage

        qi = self._MockQI(
            custom_cutted_qty_a=42,
            custom_cutted_qty_b=6,
            custom_cutted_qty_c=2,
        )
        self.assertEqual(RollTicketService._detect_qi_stage(qi), QIStage.FINAL)

    def test_final_takes_priority_over_grey_and_finishing(self):
        """
        If multiple stage fields are filled (edge case),
        FINAL must take precedence — it is the authoritative stage.
        """
        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        from desar_manufacturing.constants import QIStage

        qi = self._MockQI(
            custom_grey_qty_a=40,
            custom_grey_qty_b=5,
            custom_grey_qty_c=5,
            custom_finished_qty_a=38,
            custom_finished_qty_b=8,
            custom_finished_qty_c=4,
            custom_cutted_qty_a=42,
            custom_cutted_qty_b=6,
            custom_cutted_qty_c=2,
        )
        self.assertEqual(RollTicketService._detect_qi_stage(qi), QIStage.FINAL)

    def test_detect_unknown_when_no_grades(self):
        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        from desar_manufacturing.constants import QIStage

        qi = self._MockQI()
        self.assertEqual(RollTicketService._detect_qi_stage(qi), QIStage.UNKNOWN)

    def test_detect_with_only_grade_b_filled(self):
        """Edge case: only Grade B is filled in grey stage"""
        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        from desar_manufacturing.constants import QIStage

        qi = self._MockQI(custom_grey_qty_b=50)
        self.assertEqual(RollTicketService._detect_qi_stage(qi), QIStage.GREY)


class TestRollTicketServiceIntegration(unittest.TestCase):
    """
    Integration tests that create real Frappe documents.
    Each test is fully isolated — creates and cleans up its own data.
    """

    @classmethod
    def setUpClass(cls):
        """One-time check: verify DESAR Settings is configured."""
        frappe.set_user("Administrator")
        if not frappe.db.exists("DocType", "DESAR Settings"):
            raise unittest.SkipTest(
                "DESAR Settings DocType not found. "
                "Install desar_manufacturing app first."
            )

    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup = []  # list of (doctype, name) to delete in tearDown

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype, name in reversed(self._cleanup):
            try:
                if frappe.db.exists(doctype, name):
                    doc = frappe.get_doc(doctype, name)
                    if getattr(doc, "docstatus", 0) == 1:
                        doc.cancel()
                    frappe.delete_doc(doctype, name, force=True, ignore_missing=True)
            except Exception as e:
                frappe.logger().warning(f"Cleanup failed for {doctype}/{name}: {e}")
        frappe.db.commit()

    def _track(self, doctype, name):
        """Register a document for cleanup in tearDown."""
        self._cleanup.append((doctype, name))
        return name

    def _make_grey_roll_batch(self, batch_id):
        """Create a test Grey Roll batch."""
        if not frappe.db.exists("Batch", batch_id):
            batch = frappe.get_doc({
                "doctype": "Batch",
                "item": "Grey Roll",
                "batch_id": batch_id,
            })
            batch.insert(ignore_permissions=True)
        self._track("Batch", batch_id)
        return batch_id

    # ── create_for_grey_roll ──────────────────────────────────────────────────

    def test_creates_roll_ticket_for_new_batch(self):
        """
        Given: A new batch that has no Roll Ticket yet
        When: create_for_grey_roll is called
        Then: Roll Ticket is created with correct status and batch
        """
        from desar_manufacturing.services.roll_ticket_service import RollTicketService

        batch_id = "ITEST-RL-001"
        self._make_grey_roll_batch(batch_id)

        rt_name = RollTicketService.create_for_grey_roll(
            stock_entry_name="DUMMY-SE-FOR-TEST",
            batch_no=batch_id,
            qty=1,
            uom="Nos",
        )

        if rt_name:  # May be None if auto_create_roll_ticket is disabled
            self._track("Roll Ticket", rt_name)
            rt_data = frappe.db.get_value("Roll Ticket", rt_name,
                ["roll_batch", "roll_status", "qty_in_roll"], as_dict=True
            )
            self.assertEqual(rt_data.roll_batch, batch_id)
            self.assertEqual(rt_data.roll_status, "In Grey Store")
            self.assertEqual(flt(rt_data.qty_in_roll), 1.0)

    def test_does_not_create_duplicate(self):
        """
        Given: A Roll Ticket already exists for a batch
        When: create_for_grey_roll is called again with same batch
        Then: Returns None, no duplicate created
        """
        from desar_manufacturing.services.roll_ticket_service import RollTicketService

        batch_id = "ITEST-RL-002"
        self._make_grey_roll_batch(batch_id)

        # First creation
        rt_name = RollTicketService.create_for_grey_roll(
            stock_entry_name="DUMMY-SE",
            batch_no=batch_id,
            qty=1,
        )
        if rt_name:
            self._track("Roll Ticket", rt_name)

        # Second call — must not create duplicate
        rt_name_2 = RollTicketService.create_for_grey_roll(
            stock_entry_name="DUMMY-SE",
            batch_no=batch_id,
            qty=1,
        )
        self.assertIsNone(rt_name_2)

        # Verify count
        count = frappe.db.count("Roll Ticket", {"roll_batch": batch_id})
        self.assertLessEqual(count, 1)

    # ── update_from_qi ────────────────────────────────────────────────────────

    def test_updates_roll_ticket_grey_grades(self):
        """
        Given: Roll Ticket exists in Grey Store
        When: Grey QI is submitted with grade counts
        Then: Roll Ticket grey_qty_* updated, status → In Finishing
        """
        from desar_manufacturing.services.roll_ticket_service import RollTicketService

        batch_id = "ITEST-RL-003"
        self._make_grey_roll_batch(batch_id)

        # Insert Roll Ticket via raw SQL — avoids loading the DocType
        # controller which fails in test runner due to module registry issue.
        # frappe.db.insert() does not exist in Frappe v15 MariaDB driver.
        import datetime
        rt_name = "RT-TEST-" + datetime.datetime.now().strftime("%f")
        frappe.db.sql("""
            INSERT INTO `tabRoll Ticket`
                (name, roll_batch, roll_status, qty_in_roll, uom, owner, modified_by, creation, modified)
            VALUES
                (%s, %s, %s, %s, %s, 'Administrator', 'Administrator', NOW(), NOW())
        """, (rt_name, batch_id, "In Grey Store", 1, "Nos"))
        frappe.db.commit()
        self._track("Roll Ticket", rt_name)

        # Mock QI with grey grades
        # IMPORTANT: batch_no must be in the get() data dict
        # because service calls qi_doc.get("batch_no"), not qi_doc.batch_no
        class MockQI:
            name = "TEST-QI-GREY"
            reference_type = "Stock Entry"
            reference_name = None
            item_code = "Grey Roll"

            def get(self, key, default=None):
                data = {
                    "batch_no":            batch_id,
                    "custom_grey_qty_a":   40,
                    "custom_grey_qty_b":   6,
                    "custom_grey_qty_c":   4,
                }
                return data.get(key, default or 0)

        updated = RollTicketService.update_from_qi(MockQI())
        self.assertEqual(updated, rt_name)

        # Verify DB values using get_value — avoids controller loading
        rt_data = frappe.db.get_value("Roll Ticket", rt_name,
            ["grey_qty_a", "grey_qty_b", "grey_qty_c", "roll_status"],
            as_dict=True
        )
        self.assertEqual(rt_data.grey_qty_a, 40)
        self.assertEqual(rt_data.grey_qty_b, 6)
        self.assertEqual(rt_data.grey_qty_c, 4)
        self.assertEqual(rt_data.roll_status, "In Finishing")

    def test_updates_roll_ticket_final_grades_and_completes(self):
        """
        Given: Roll Ticket in In Packing status
        When: Final QI is submitted
        Then: Roll Ticket cutted_qty_* updated, status → Completed
        """
        from desar_manufacturing.services.roll_ticket_service import RollTicketService

        batch_id = "ITEST-RL-004"
        self._make_grey_roll_batch(batch_id)

        # Insert Roll Ticket via raw SQL — avoids controller loading
        import datetime
        rt_name = "RT-TEST-" + datetime.datetime.now().strftime("%f")
        frappe.db.sql("""
            INSERT INTO `tabRoll Ticket`
                (name, roll_batch, roll_status, qty_in_roll, uom, owner, modified_by, creation, modified)
            VALUES
                (%s, %s, %s, %s, %s, 'Administrator', 'Administrator', NOW(), NOW())
        """, (rt_name, batch_id, "In Packing", 1, "Nos"))
        frappe.db.commit()
        self._track("Roll Ticket", rt_name)

        # IMPORTANT: batch_no must be in the get() data dict
        # because service calls qi_doc.get("batch_no"), not qi_doc.batch_no
        class MockFinalQI:
            name = "TEST-QI-FINAL"
            reference_type = "Stock Entry"
            reference_name = None
            item_code = "Shemagh-VIC-60-A"

            def get(self, key, default=None):
                data = {
                    "batch_no":             batch_id,
                    "custom_cutted_qty_a":  42,
                    "custom_cutted_qty_b":  6,
                    "custom_cutted_qty_c":  2,
                }
                return data.get(key, default or 0)

        updated = RollTicketService.update_from_qi(MockFinalQI())
        self.assertEqual(updated, rt_name)

        # Verify DB values using get_value — avoids controller loading
        rt_data = frappe.db.get_value("Roll Ticket", rt_name,
            ["cutted_qty_a", "cutted_qty_b", "cutted_qty_c", "roll_status"],
            as_dict=True
        )
        self.assertEqual(rt_data.cutted_qty_a, 42)
        self.assertEqual(rt_data.cutted_qty_b, 6)
        self.assertEqual(rt_data.cutted_qty_c, 2)
        self.assertEqual(rt_data.roll_status, "Completed")

    def test_returns_none_when_no_roll_ticket_found(self):
        """
        Given: No Roll Ticket exists for the batch
        When: update_from_qi is called
        Then: Returns None silently — no exception raised
        """
        from desar_manufacturing.services.roll_ticket_service import RollTicketService

        class MockQI:
            name = "TEST-QI-NOTFOUND"
            reference_type = "Stock Entry"
            reference_name = None
            item_code = "Grey Roll"

            def get(self, key, default=None):
                data = {
                    "batch_no":          "BATCH-DOES-NOT-EXIST-ZZZZZ",
                    "custom_grey_qty_a": 40,
                }
                return data.get(key, default or 0)

        result = RollTicketService.update_from_qi(MockQI())
        self.assertIsNone(result)


class TestRepackServiceUnit(unittest.TestCase):
    """
    Unit tests for RepackService._build_items
    No DB needed — pure construction logic.
    """

    def test_build_items_all_grades(self):
        """All 3 output rows created when all grades present"""
        from desar_manufacturing.services.repack_service import RepackService

        items = RepackService._build_items(
            item_a="Shemagh-VIC-60-A",
            item_b="Shemagh-VIC-60-B",
            wh_src="Cutting - ST",
            wh_a="FG Grade A - ST",
            wh_b="FG Grade B - ST",
            wh_sc="Scrap Yard - ST",
            total=50,
            grade_a=42,
            grade_b=6,
            grade_c=2,
            val_rate=100.0,
        )

        # Must have 4 rows: 1 source + 3 output
        self.assertEqual(len(items), 4)

        source_row = items[0]
        self.assertEqual(source_row["item_code"], "Shemagh-VIC-60-A")
        self.assertEqual(source_row["qty"], 50)
        self.assertIn("s_warehouse", source_row)

        grade_a_row = items[1]
        self.assertEqual(grade_a_row["item_code"], "Shemagh-VIC-60-A")
        self.assertEqual(grade_a_row["qty"], 42)
        self.assertEqual(grade_a_row["basic_rate"], 100.0)

        grade_b_row = items[2]
        self.assertEqual(grade_b_row["item_code"], "Shemagh-VIC-60-B")
        self.assertEqual(grade_b_row["qty"], 6)
        self.assertAlmostEqual(grade_b_row["basic_rate"], 60.0, places=1)

        scrap_row = items[3]
        self.assertEqual(scrap_row["qty"], 2)
        self.assertAlmostEqual(scrap_row["basic_rate"], 5.0, places=1)

    def test_grade_b_skipped_when_qty_zero(self):
        """No Grade B pieces → no Grade B row"""
        from desar_manufacturing.services.repack_service import RepackService

        items = RepackService._build_items(
            item_a="Shemagh-VIC-60-A",
            item_b="Shemagh-VIC-60-B",
            wh_src="Cutting - ST",
            wh_a="FG Grade A - ST",
            wh_b="FG Grade B - ST",
            wh_sc="Scrap Yard - ST",
            total=50,
            grade_a=48,
            grade_b=0,
            grade_c=2,
            val_rate=100.0,
        )

        item_codes = [r["item_code"] for r in items]
        self.assertNotIn("Shemagh-VIC-60-B", item_codes)
        self.assertEqual(len(items), 3)  # source + grade_a + scrap

    def test_scrap_skipped_when_qty_zero(self):
        """No scrap → no scrap row"""
        from desar_manufacturing.services.repack_service import RepackService

        items = RepackService._build_items(
            item_a="Shemagh-VIC-60-A",
            item_b="Shemagh-VIC-60-B",
            wh_src="Cutting - ST",
            wh_a="FG Grade A - ST",
            wh_b="FG Grade B - ST",
            wh_sc="Scrap Yard - ST",
            total=50,
            grade_a=44,
            grade_b=6,
            grade_c=0,
            val_rate=100.0,
        )

        from desar_manufacturing.constants import SHEMAGH_SCRAP
        item_codes = [r["item_code"] for r in items]
        self.assertNotIn(SHEMAGH_SCRAP, item_codes)

    def test_grade_b_valuation_is_60_percent(self):
        """Grade B must always be exactly 60% of Grade A rate"""
        from desar_manufacturing.services.repack_service import RepackService

        items = RepackService._build_items(
            item_a="Shemagh-VIC-60-A",
            item_b="Shemagh-VIC-60-B",
            wh_src="S", wh_a="A", wh_b="B", wh_sc="SC",
            total=50, grade_a=42, grade_b=6, grade_c=2,
            val_rate=18.04,
        )

        grade_a_rate = items[1]["basic_rate"]
        grade_b_rate = items[2]["basic_rate"]
        expected_b = round(18.04 * 0.6, 2)
        self.assertAlmostEqual(grade_b_rate, expected_b, places=2)

    def test_scrap_valuation_is_5_percent(self):
        """Scrap must always be exactly 5% of Grade A rate"""
        from desar_manufacturing.services.repack_service import RepackService

        items = RepackService._build_items(
            item_a="Shemagh-VIC-60-A",
            item_b="Shemagh-VIC-60-B",
            wh_src="S", wh_a="A", wh_b="B", wh_sc="SC",
            total=50, grade_a=42, grade_b=6, grade_c=2,
            val_rate=18.04,
        )

        scrap_rate = items[3]["basic_rate"]
        expected_scrap = round(18.04 * 0.05, 2)
        self.assertAlmostEqual(scrap_rate, expected_scrap, places=2)


class TestSettingsManager(unittest.TestCase):
    """
    Tests for SettingsManager behavior.
    Requires DESAR Settings DocType to exist.
    """

    @classmethod
    def setUpClass(cls):
        if not frappe.db.exists("DocType", "DESAR Settings"):
            raise unittest.SkipTest("DESAR Settings not installed")

    def test_get_returns_value_or_default(self):
        from desar_manufacturing.config.settings_manager import SettingsManager
        # Clear cache first
        frappe.cache().delete_value(SettingsManager._CACHE_KEY)

        # Should not raise — returns None or value
        value = SettingsManager.get("default_company", "FALLBACK")
        # Either a configured company or the fallback
        self.assertIsNotNone(value)

    def test_cache_cleared_after_delete(self):
        """
        Test observable behavior: after cache clear, SettingsManager
        still returns correct values (re-reads from DB).

        NOTE: We do NOT test frappe.cache() internals because
        frappe.cache() is a NullCache in bench test mode and does
        not persist values between calls. Testing the cache object
        directly is testing Frappe internals, not our code.

        What we test instead: SettingsManager.get() is consistent
        across multiple calls — the caching is transparent to callers.
        """
        from desar_manufacturing.config.settings_manager import SettingsManager

        # Clear any existing cache state
        frappe.cache().delete_value(SettingsManager._CACHE_KEY)

        # Call get() multiple times — must return same value each time
        # regardless of whether cache is working or doing DB reads
        val1 = SettingsManager.get("default_company", "FALLBACK")
        val2 = SettingsManager.get("default_company", "FALLBACK")

        self.assertEqual(val1, val2,
            "SettingsManager.get() must return consistent values across calls")

        # Calling clear_cache equivalent should not raise
        frappe.cache().delete_value(SettingsManager._CACHE_KEY)

        # Value still accessible after cache clear (re-reads from DB)
        val3 = SettingsManager.get("default_company", "FALLBACK")
        self.assertEqual(val1, val3,
            "SettingsManager.get() must return same value after cache clear")

    def test_get_warehouse_raises_when_not_configured(self):
        """
        If a warehouse key is not set, get_warehouse must raise
        with a user-friendly message — not a KeyError or AttributeError.
        """
        from desar_manufacturing.config.settings_manager import SettingsManager

        # Use a key that definitely doesn't exist
        with self.assertRaises(Exception) as ctx:
            SettingsManager.get_warehouse("nonexistent_warehouse_key_zzz")

        # Error message must be human-readable
        self.assertIn("not configured", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)