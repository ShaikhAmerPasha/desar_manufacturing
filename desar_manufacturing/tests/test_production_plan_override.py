"""
Production Plan override — skip duplicate Work Order creation.

Core's own dedup guard (ordered_qty) only updates on Work Order submit, never
on plain insert, so re-clicking "Create Work Order" while everything is still
Draft duplicates the whole set. CustomProductionPlan.create_work_order closes
that gap directly.
"""
import unittest
from unittest.mock import patch, MagicMock

from desar_manufacturing.overrides.production_plan import CustomProductionPlan


class TestSkipsExistingWorkOrder(unittest.TestCase):
    @patch("frappe.msgprint")
    @patch("frappe.db.exists", return_value="MFG-WO-2026-00001")
    def test_second_call_skips_and_does_not_insert(self, mock_exists, mock_msgprint):
        plan = MagicMock(spec=CustomProductionPlan)
        plan.name = "MFG-PP-2026-00001"

        with patch(
            "desar_manufacturing.overrides.production_plan.ProductionPlan.create_work_order"
        ) as mock_super_create:
            result = CustomProductionPlan.create_work_order(
                plan, {"production_item": "Warping Beam", "bom_no": "BOM-Warping Beam-001"}
            )

        self.assertIsNone(result)
        mock_super_create.assert_not_called()
        mock_exists.assert_called_once_with("Work Order", {
            "production_plan": "MFG-PP-2026-00001",
            "production_item": "Warping Beam",
            "bom_no": "BOM-Warping Beam-001",
            "docstatus": ["!=", 2],
        })

    @patch("frappe.db.exists", return_value=None)
    def test_new_item_still_creates_normally(self, mock_exists):
        plan = MagicMock(spec=CustomProductionPlan)
        plan.name = "MFG-PP-2026-00001"

        with patch(
            "desar_manufacturing.overrides.production_plan.ProductionPlan.create_work_order",
            return_value="MFG-WO-2026-00099",
        ) as mock_super_create:
            result = CustomProductionPlan.create_work_order(
                plan, {"production_item": "Grey Roll", "bom_no": "BOM-Grey Roll-002"}
            )

        self.assertEqual(result, "MFG-WO-2026-00099")
        mock_super_create.assert_called_once()
