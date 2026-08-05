"""
Production Plan Service — multi-design scoping.

Calls the real _load_design_wos()/list_design_masters_for_plan() directly,
with frappe.get_all/wo_split_helpers.load_plan_wos mocked (no DB needed).
"""
import unittest
from unittest.mock import patch

import frappe
from desar_manufacturing.services import production_plan_service as pps


def _wo(name, design_master):
    return frappe._dict({"name": name, "custom_design_master": design_master})


class TestLoadDesignWos(unittest.TestCase):
    @patch("desar_manufacturing.services.production_plan_service.wo.load_plan_wos")
    def test_filters_to_one_design_out_of_many(self, mock_load):
        mock_load.return_value = [
            _wo("WO-1", "DM-ZEP-55"), _wo("WO-2", "DM-ATL-55"), _wo("WO-3", "DM-ZEP-55"),
        ]
        result = pps._load_design_wos("PP-0001", "DM-ZEP-55")
        self.assertEqual([w.name for w in result], ["WO-1", "WO-3"])

    @patch("desar_manufacturing.services.production_plan_service.wo.load_plan_wos")
    def test_single_design_plan_is_a_no_op_filter(self, mock_load):
        mock_load.return_value = [_wo("WO-1", "DM-VIC-60"), _wo("WO-2", "DM-VIC-60")]
        result = pps._load_design_wos("PP-0002", "DM-VIC-60")
        self.assertEqual(len(result), 2)


class TestListDesignMastersForPlan(unittest.TestCase):
    @patch("frappe.get_all")
    def test_returns_distinct_sorted_design_masters(self, mock_get_all):
        mock_get_all.return_value = [
            frappe._dict({"custom_design_master": "DM-ATL-55"}),
            frappe._dict({"custom_design_master": "DM-ZEP-55"}),
            frappe._dict({"custom_design_master": "DM-ATL-55"}),
        ]
        result = pps.list_design_masters_for_plan("PP-0001")
        self.assertEqual(result, ["DM-ATL-55", "DM-ZEP-55"])

    @patch("frappe.get_all")
    def test_blank_design_master_excluded(self, mock_get_all):
        mock_get_all.return_value = [
            frappe._dict({"custom_design_master": "DM-VIC-60"}),
            frappe._dict({"custom_design_master": None}),
        ]
        result = pps.list_design_masters_for_plan("PP-0002")
        self.assertEqual(result, ["DM-VIC-60"])
