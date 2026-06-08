"""
DESAR Manufacturing — Level 3 End-to-End Test Script
Runs a complete production cycle programmatically and verifies each step.

This is NOT a unit test — it is a system verification script.
It creates REAL documents on your ERPNext site and checks expected outcomes.

Usage:
    bench --site <your-site> execute \
        desar_manufacturing.tests.test_e2e_cycle.run_full_cycle

Pre-conditions (must be true before running):
    1. DESAR Settings — all 12 warehouse fields filled
    2. All 4 BOMs submitted for Shemagh-VIC-60-A
    3. Stock available: Yarn Store, Chemical Store, Accessories Store
    4. QI Templates exist with max_value=1 on all parameters

Author: DESAR Factory
Version: 2.3.0
"""

import frappe
from frappe.utils import nowdate, flt
from frappe import _


# ── Test State ────────────────────────────────────────────────────────────────

_state = {
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "errors": [],
    "created_docs": [],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pass(test_name):
    _state["passed"] += 1
    print(f"  ✅ PASS — {test_name}")


def _fail(test_name, reason):
    _state["failed"] += 1
    _state["errors"].append(f"{test_name}: {reason}")
    print(f"  ❌ FAIL — {test_name}")
    print(f"         Reason: {reason}")


def _skip(test_name, reason):
    _state["skipped"] += 1
    print(f"  ⏭  SKIP — {test_name} ({reason})")


def _check(test_name, condition, failure_msg=""):
    if condition:
        _pass(test_name)
    else:
        _fail(test_name, failure_msg or "Condition not met")


def _track(doctype, name):
    _state["created_docs"].append((doctype, name))


def _section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _cleanup_all():
    """Delete all documents created during the test run."""
    print("\n🧹 Cleaning up test documents...")
    for doctype, name in reversed(_state["created_docs"]):
        try:
            if frappe.db.exists(doctype, name):
                doc = frappe.get_doc(doctype, name)
                if getattr(doc, "docstatus", 0) == 1:
                    doc.cancel()
                frappe.delete_doc(doctype, name, force=True, ignore_missing=True)
                print(f"   Deleted {doctype}: {name}")
        except Exception as e:
            print(f"   Warning: Could not delete {doctype}/{name}: {e}")
    frappe.db.commit()
    print("   Done.")


# ── Pre-condition Checks ──────────────────────────────────────────────────────

def _check_preconditions():
    _section("PRE-CONDITION CHECKS")
    ok = True

    # Check DESAR Settings
    from desar_manufacturing.config.settings_manager import SettingsManager
    frappe.cache().delete_value(SettingsManager._CACHE_KEY)

    missing_wh = []
    for key in SettingsManager.WAREHOUSE_KEYS:
        if not SettingsManager.get(key):
            missing_wh.append(key)

    if missing_wh:
        _fail("DESAR Settings warehouses", f"Missing: {', '.join(missing_wh)}")
        ok = False
    else:
        _pass("DESAR Settings — all 12 warehouses configured")

    # Check BOM exists for Shemagh-VIC-60-A
    bom_exists = frappe.db.exists("BOM", {
        "item": "Shemagh-VIC-60-A",
        "is_active": 1,
        "docstatus": 1,
    })
    _check("BOM for Shemagh-VIC-60-A exists", bom_exists, "No active BOM found")
    if not bom_exists:
        ok = False

    # Check QI templates
    for template in [
        "Grey Inspection - Shemagh",
        "Finishing Inspection - Shemagh",
        "Final Packing Inspection - Shemagh",
    ]:
        exists = frappe.db.exists("Quality Inspection Template", template)
        _check(f"QI Template: {template}", exists, "Template not found")
        if not exists:
            ok = False

    # Check items exist
    for item in ["Grey Roll", "Finished Roll", "Warping Beam",
                 "Shemagh-VIC-60-A", "Shemagh-VIC-60-B", "Shemagh Scrap"]:
        exists = frappe.db.exists("Item", item)
        _check(f"Item exists: {item}", exists, f"Item '{item}' not found")
        if not exists:
            ok = False

    return ok


# ── Test Sections ─────────────────────────────────────────────────────────────

def _test_validation_logic():
    _section("TEST BLOCK 1: Validation Logic")

    from desar_manufacturing.utils.validation_utils import (
        validate_final_grade_counts,
        derive_grade_b_item,
    )

    # T1.1 — exact match passes
    valid, _ = validate_final_grade_counts(42, 6, 2, 50)
    _check("T1.1 Final grade exact match passes", valid)

    # T1.2 — over-count blocked
    valid, msg = validate_final_grade_counts(43, 6, 2, 50)
    _check("T1.2 Over-count (51>50) blocked", not valid and "51" in str(msg))

    # T1.3 — under-count blocked
    valid, msg = validate_final_grade_counts(40, 6, 2, 50)
    _check("T1.3 Under-count (48<50) blocked", not valid and "2" in str(msg))

    # T1.4 — zero grades skipped
    valid, _ = validate_final_grade_counts(0, 0, 0, 50)
    _check("T1.4 Zero grades not a final QI — passes", valid)

    # T1.5 — derive grade B
    result = derive_grade_b_item("Shemagh-VIC-60-A")
    _check("T1.5 Grade B derived correctly", result == "Shemagh-VIC-60-B", f"Got: {result}")

    # T1.6 — rfind logic
    result = derive_grade_b_item("Shemagh-VIC-A1-60-A")
    _check("T1.6 rfind replaces last -A only", result == "Shemagh-VIC-A1-60-B", f"Got: {result}")


def _test_roll_ticket_auto_creation():
    _section("TEST BLOCK 2: Roll Ticket Auto-Creation")

    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    from desar_manufacturing.repositories.roll_ticket_repository import RollTicketRepository

    TEST_BATCH = "E2E-RL-TEST-001"

    # Clean up any leftover from previous run
    if frappe.db.exists("Batch", TEST_BATCH):
        frappe.delete_doc("Batch", TEST_BATCH, force=True)
    for rt in frappe.get_all("Roll Ticket", {"roll_batch": TEST_BATCH}):
        frappe.delete_doc("Roll Ticket", rt.name, force=True)

    # Create test batch
    batch = frappe.get_doc({
        "doctype": "Batch",
        "item": "Grey Roll",
        "batch_id": TEST_BATCH,
    })
    batch.insert(ignore_permissions=True)
    _track("Batch", TEST_BATCH)

    # T2.1 — create Roll Ticket
    rt_name = RollTicketService.create_for_grey_roll(
        stock_entry_name="DUMMY-SE",
        batch_no=TEST_BATCH,
        qty=1,
        uom="Nos",
    )

    if rt_name:
        _track("Roll Ticket", rt_name)
        rt = frappe.get_doc("Roll Ticket", rt_name)
        _check("T2.1 Roll Ticket created", bool(rt_name))
        _check("T2.2 Roll Ticket batch matches", rt.roll_batch == TEST_BATCH)
        _check("T2.3 Roll Ticket status = In Grey Store", rt.roll_status == "In Grey Store")
        _check("T2.4 Roll Ticket qty = 1", flt(rt.qty_in_roll) == 1.0)
    else:
        _skip("T2.1-T2.4", "auto_create_roll_ticket is disabled in DESAR Settings")

    # T2.5 — duplicate prevention
    rt_name_2 = RollTicketService.create_for_grey_roll(
        stock_entry_name="DUMMY-SE",
        batch_no=TEST_BATCH,
        qty=1,
    )
    _check("T2.5 Duplicate prevented", rt_name_2 is None)

    count = frappe.db.count("Roll Ticket", {"roll_batch": TEST_BATCH})
    _check("T2.6 Only 1 Roll Ticket exists for batch", count <= 1, f"Count = {count}")


def _test_roll_ticket_update_from_qi():
    _section("TEST BLOCK 3: Roll Ticket Update from QI")

    from desar_manufacturing.services.roll_ticket_service import RollTicketService

    TEST_BATCH = "E2E-RL-TEST-002"

    # Create batch
    if not frappe.db.exists("Batch", TEST_BATCH):
        batch = frappe.get_doc({
            "doctype": "Batch",
            "item": "Grey Roll",
            "batch_id": TEST_BATCH,
        })
        batch.insert(ignore_permissions=True)
        _track("Batch", TEST_BATCH)

    # Create Roll Ticket manually
    rt = frappe.get_doc({
        "doctype": "Roll Ticket",
        "roll_batch": TEST_BATCH,
        "roll_status": "In Grey Store",
        "qty_in_roll": 1,
        "uom": "Nos",
    })
    rt.insert(ignore_permissions=True)
    _track("Roll Ticket", rt.name)

    # Mock Grey QI
    # IMPORTANT: batch_no must be in get() dict — service calls qi_doc.get("batch_no")
    class MockGreyQI:
        name = "MOCK-GREY-QI"
        reference_type = "Stock Entry"
        reference_name = None
        item_code = "Grey Roll"
        def get(self, key, d=None):
            return {
                "batch_no":            TEST_BATCH,
                "custom_grey_qty_a":   40,
                "custom_grey_qty_b":   7,
                "custom_grey_qty_c":   3,
            }.get(key, d or 0)

    updated = RollTicketService.update_from_qi(MockGreyQI())
    _check("T3.1 Roll Ticket updated from grey QI", updated == rt.name)

    rt_doc = frappe.get_doc("Roll Ticket", rt.name)
    _check("T3.2 grey_qty_a = 40", rt_doc.grey_qty_a == 40, f"Got: {rt_doc.grey_qty_a}")
    _check("T3.3 grey_qty_b = 7", rt_doc.grey_qty_b == 7, f"Got: {rt_doc.grey_qty_b}")
    _check("T3.4 Status → In Finishing", rt_doc.roll_status == "In Finishing", f"Got: {rt_doc.roll_status}")

    # Mock Final QI
    # IMPORTANT: batch_no must be in get() dict — service calls qi_doc.get("batch_no")
    class MockFinalQI:
        name = "MOCK-FINAL-QI"
        reference_type = "Stock Entry"
        reference_name = None
        item_code = "Shemagh-VIC-60-A"
        def get(self, key, d=None):
            return {
                "batch_no":             TEST_BATCH,
                "custom_cutted_qty_a":  42,
                "custom_cutted_qty_b":  6,
                "custom_cutted_qty_c":  2,
            }.get(key, d or 0)

    RollTicketService.update_from_qi(MockFinalQI())
    rt_doc2 = frappe.get_doc("Roll Ticket", rt.name)
    _check("T3.5 cutted_qty_a = 42", rt_doc2.cutted_qty_a == 42, f"Got: {rt_doc2.cutted_qty_a}")
    _check("T3.6 Status → Completed", rt_doc2.roll_status == "Completed", f"Got: {rt_doc2.roll_status}")


def _test_repack_build_items():
    _section("TEST BLOCK 4: Repack SE Items Logic")

    from desar_manufacturing.services.repack_service import RepackService

    # T4.1 — standard 4-row Repack
    items = RepackService._build_items(
        item_a="Shemagh-VIC-60-A",
        item_b="Shemagh-VIC-60-B",
        wh_src="S", wh_a="A", wh_b="B", wh_sc="SC",
        total=50, grade_a=42, grade_b=6, grade_c=2,
        val_rate=100.0,
    )
    _check("T4.1 4 rows built (source + A + B + scrap)", len(items) == 4, f"Got: {len(items)}")
    _check("T4.2 Source qty = total (50)", items[0]["qty"] == 50)
    _check("T4.3 Grade A qty = 42", items[1]["qty"] == 42)
    _check("T4.4 Grade B qty = 6", items[2]["qty"] == 6)
    _check("T4.5 Scrap qty = 2", items[3]["qty"] == 2)
    _check("T4.6 Grade B rate = 60%", abs(items[2]["basic_rate"] - 60.0) < 0.01)
    _check("T4.7 Scrap rate = 5%", abs(items[3]["basic_rate"] - 5.0) < 0.01)

    # T4.2 — no grade B
    items2 = RepackService._build_items(
        item_a="Shemagh-VIC-60-A", item_b=None,
        wh_src="S", wh_a="A", wh_b="B", wh_sc="SC",
        total=50, grade_a=48, grade_b=0, grade_c=2,
        val_rate=100.0,
    )
    _check("T4.8 Grade B row skipped when qty=0", len(items2) == 3)


def _test_qi_creation_api():
    _section("TEST BLOCK 5: QI Creation API")

    # T5.1 — invalid stage rejected
    try:
        frappe.call(
            "desar_manufacturing.api.manufacturing.create_quality_inspection",
            work_order="TEST-WO",
            stage="invalid_stage_xyz",
        )
        _fail("T5.1 Invalid stage rejected", "Should have raised exception")
    except Exception as e:
        _check("T5.1 Invalid stage raises error", "invalid_stage_xyz" in str(e) or "valid" in str(e).lower())

    # T5.2 — empty work_order rejected
    try:
        import importlib
        api = importlib.import_module("desar_manufacturing.api.manufacturing")
        api.create_quality_inspection(work_order="", stage="grey")
        _fail("T5.2 Empty work_order rejected", "Should have raised exception")
    except Exception:
        _pass("T5.2 Empty work_order raises error")

    # T5.3 — nonexistent WO rejected
    try:
        api = importlib.import_module("desar_manufacturing.api.manufacturing")
        api.create_quality_inspection(work_order="WO-DOES-NOT-EXIST-ZZZZ", stage="grey")
        _fail("T5.3 Nonexistent WO rejected", "Should have raised exception")
    except Exception:
        _pass("T5.3 Nonexistent WO raises error")


# ── Summary ───────────────────────────────────────────────────────────────────

def _print_summary():
    total = _state["passed"] + _state["failed"] + _state["skipped"]
    print(f"\n{'='*60}")
    print(f"  TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  Total:   {total}")
    print(f"  ✅ Pass:  {_state['passed']}")
    print(f"  ❌ Fail:  {_state['failed']}")
    print(f"  ⏭  Skip:  {_state['skipped']}")

    if _state["errors"]:
        print(f"\n  Failed tests:")
        for err in _state["errors"]:
            print(f"    • {err}")

    if _state["failed"] == 0:
        print(f"\n  🎉 All tests passed!")
    else:
        print(f"\n  ⚠️  {_state['failed']} test(s) failed. Review above.")
    print(f"{'='*60}\n")


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_full_cycle(cleanup=True):
    """
    Run all E2E tests.

    Args:
        cleanup: If True (default), delete all test documents after run.
                 Set to False to inspect created documents in ERPNext UI.

    Usage:
        bench --site <site> execute \
            desar_manufacturing.tests.test_e2e_cycle.run_full_cycle
    """
    print("\n🚀 DESAR Manufacturing v2.3 — E2E Test Run")
    print(f"   Site:  {frappe.local.site}")
    print(f"   User:  {frappe.session.user}")
    print(f"   Date:  {nowdate()}")

    frappe.set_user("Administrator")

    # Pre-conditions — stop if environment not ready
    if not _check_preconditions():
        print("\n⛔ Pre-conditions failed. Fix issues above before running E2E tests.")
        return

    # Run all test blocks
    _test_validation_logic()
    _test_roll_ticket_auto_creation()
    _test_roll_ticket_update_from_qi()
    _test_repack_build_items()
    _test_qi_creation_api()

    # Print summary
    _print_summary()

    # Cleanup
    if cleanup:
        _cleanup_all()
    else:
        print("\n📋 Documents created (cleanup=False):")
        for doctype, name in _state["created_docs"]:
            print(f"   {doctype}: {name}")

    frappe.db.commit()
