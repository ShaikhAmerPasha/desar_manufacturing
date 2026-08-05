"""
Production Plan — Production Buffer % (custom_production_buffer_pct).

Calls events.production_plan.validate() directly (real hook), with
frappe.db.get_value("Sales Order Item", ...) mocked (no DB needed).
"""
import unittest
from unittest.mock import patch

import frappe
from desar_manufacturing.events import production_plan


def _plan(buffer_pct, docstatus, rows):
    return frappe._dict({
        "docstatus": docstatus,
        "custom_production_buffer_pct": buffer_pct,
        "po_items": [frappe._dict(r) for r in rows],
        "sub_assembly_items": [],
    })


class TestProductionBuffer(unittest.TestCase):
    @patch("frappe.db.get_value", return_value=500)
    def test_buffer_applies_to_sales_order_linked_rows(self, mock_get_value):
        doc = _plan(15, 0, [{"sales_order": "SO-001", "sales_order_item": "soi-1", "planned_qty": 500}])
        production_plan.validate(doc)
        self.assertEqual(doc.po_items[0].planned_qty, 575)

    @patch("frappe.db.get_value", return_value=500)
    def test_zero_buffer_is_a_no_op(self, mock_get_value):
        doc = _plan(0, 0, [{"sales_order": "SO-001", "sales_order_item": "soi-1", "planned_qty": 500}])
        production_plan.validate(doc)
        self.assertEqual(doc.po_items[0].planned_qty, 500)

    @patch("frappe.db.get_value")
    def test_row_without_sales_order_untouched(self, mock_get_value):
        doc = _plan(15, 0, [{"sales_order": None, "sales_order_item": None, "planned_qty": 500}])
        production_plan.validate(doc)
        self.assertEqual(doc.po_items[0].planned_qty, 500)
        mock_get_value.assert_not_called()

    @patch("frappe.db.get_value", return_value=500)
    def test_not_reapplied_after_submit(self, mock_get_value):
        """docstatus=1: must not recompute planned_qty once submitted."""
        doc = _plan(15, 1, [{"sales_order": "SO-001", "sales_order_item": "soi-1", "planned_qty": 575}])
        production_plan.validate(doc)
        self.assertEqual(doc.po_items[0].planned_qty, 575)

    @patch("frappe.db.get_value", return_value=500)
    def test_idempotent_across_repeated_saves(self, mock_get_value):
        """Regression: core ERPNext's set_pending_qty_in_row_without_reference()
        has an `or` where it should have `and`, so it resets pending_qty =
        planned_qty on every save for ANY sales-order-linked row (they never
        have material_request set). Anchoring to pending_qty would compound
        the buffer each resave (500 -> 575 -> 661.25 -> ...). Anchoring to the
        Sales Order Item's own qty (mocked here, never mutated by that bug)
        must stay at 575 no matter how many times validate() runs."""
        doc = _plan(15, 0, [{"sales_order": "SO-001", "sales_order_item": "soi-1", "planned_qty": 500}])
        production_plan.validate(doc)
        production_plan.validate(doc)
        production_plan.validate(doc)
        self.assertEqual(doc.po_items[0].planned_qty, 575)

    @patch("frappe.db.get_value", return_value=0)
    def test_missing_so_qty_leaves_planned_qty_untouched(self, mock_get_value):
        doc = _plan(15, 0, [{"sales_order": "SO-001", "sales_order_item": "soi-1", "planned_qty": 500}])
        production_plan.validate(doc)
        self.assertEqual(doc.po_items[0].planned_qty, 500)
