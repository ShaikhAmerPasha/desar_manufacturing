"""
DESAR BOM Service — Sticker Accessory + Chemical Materials Tests

Calls BOMService's real helper methods directly (not a reimplementation),
with frappe.db.exists/get_single_value mocked so no DocType fixtures are
required to run this file standalone.
"""
import unittest
from unittest.mock import patch

import frappe
from desar_manufacturing.services.bom_service import BOMService


def _dm(**overrides):
    base = {
        "branded_box_item": None,
        "label_item": None,
        "sticker_item": None,
        "default_size": "60",
        "chemical_materials_qty_kg": 0,
        "wash_agent_qty": 0,
        "finish_chem_qty": 0,
        "flower_chem_qty": 0,
    }
    base.update(overrides)
    return frappe._dict(base)


class TestAccessoryItemsIncludeSticker(unittest.TestCase):

    @patch("frappe.db.get_single_value", return_value="Accessories Store - ST")
    @patch("frappe.db.exists", return_value=True)
    def test_sticker_item_included_when_set(self, mock_exists, mock_wh):
        dm = _dm(branded_box_item="Boxes", label_item="Stamps", sticker_item="Stickers")
        items = BOMService._get_accessory_items(dm, pcs=115)
        codes = [i["item_code"] for i in items]
        self.assertIn("Stickers", codes)
        self.assertEqual(len(items), 3)

    @patch("frappe.db.get_single_value", return_value="Accessories Store - ST")
    @patch("frappe.db.exists", return_value=True)
    def test_sticker_falls_back_to_default_code(self, mock_exists, mock_wh):
        dm = _dm(default_size="55")
        items = BOMService._get_accessory_items(dm, pcs=115)
        codes = [i["item_code"] for i in items]
        self.assertIn("Sticker-55", codes)

    @patch("frappe.db.get_single_value", return_value="Accessories Store - ST")
    @patch("frappe.db.exists", return_value=False)
    def test_sticker_skipped_when_item_missing(self, mock_exists, mock_wh):
        dm = _dm(sticker_item="Stickers")
        items = BOMService._get_accessory_items(dm, pcs=115)
        self.assertEqual(items, [])


class TestChemicalItemsIncludeChemicalMaterials(unittest.TestCase):

    @patch("frappe.db.get_single_value", return_value="Chemical Store - ST")
    @patch("frappe.db.exists", return_value=True)
    def test_chemical_materials_included_when_qty_set(self, mock_exists, mock_wh):
        dm = _dm(chemical_materials_qty_kg=21.74)
        items = BOMService._get_chemical_items(dm)
        row = next(i for i in items if i["item_code"] == "Chemical Materials")
        self.assertEqual(row["qty"], 21.74)
        self.assertEqual(row["uom"], "Kg")

    @patch("frappe.db.get_single_value", return_value="Chemical Store - ST")
    @patch("frappe.db.exists", return_value=True)
    def test_chemical_materials_skipped_when_qty_zero(self, mock_exists, mock_wh):
        dm = _dm(chemical_materials_qty_kg=0)
        items = BOMService._get_chemical_items(dm)
        codes = [i["item_code"] for i in items]
        self.assertNotIn("Chemical Materials", codes)

    @patch("frappe.db.get_single_value", return_value="Chemical Store - ST")
    @patch("frappe.db.exists", return_value=False)
    def test_chemical_materials_skipped_when_item_missing(self, mock_exists, mock_wh):
        dm = _dm(chemical_materials_qty_kg=21.74)
        items = BOMService._get_chemical_items(dm)
        codes = [i["item_code"] for i in items]
        self.assertNotIn("Chemical Materials", codes)


class TestMakeBomItemPinsUpstreamBom(unittest.TestCase):
    """Without bom_no, ERPNext's multi-level BOM explosion falls back to
    whichever BOM currently happens to be flagged default for a shared
    item name (e.g. "Grey Roll") — wrong the moment more than one design
    shares that item. _make_bom_item must pin the exact upstream BOM."""

    def test_bom_no_included_when_given(self):
        item = BOMService._make_bom_item("Grey Roll", 1, "Nos", "WH-1", bom_no="BOM-Grey Roll-007")
        self.assertEqual(item["bom_no"], "BOM-Grey Roll-007")

    def test_bom_no_omitted_for_raw_materials(self):
        item = BOMService._make_bom_item("Yarn-100-2-White", 100, "Kg", "WH-1")
        self.assertNotIn("bom_no", item)


class TestLegacyChainPinsUpstreamBom(unittest.TestCase):
    """Legacy _create_bom_grey_roll/_finished_roll/_shemagh must thread the
    caller-supplied upstream bom_no into their single input row."""

    @patch("frappe.db.get_single_value", return_value="WH-1")
    @patch.object(BOMService, "_insert_and_submit_bom", return_value="BOM-Grey Roll-XXX")
    def test_grey_roll_pins_warping_beam_bom(self, mock_insert, mock_wh):
        BOMService._create_bom_grey_roll(_dm(), warping_beam_bom="BOM-Warping Beam-009")
        data = mock_insert.call_args[0][0]
        self.assertEqual(data["items"][0]["bom_no"], "BOM-Warping Beam-009")

    @patch("frappe.db.get_single_value", return_value="WH-1")
    @patch.object(BOMService, "_insert_and_submit_bom", return_value="BOM-Finished Roll-XXX")
    def test_finished_roll_pins_grey_roll_bom(self, mock_insert, mock_wh):
        BOMService._create_bom_finished_roll(_dm(), grey_roll_bom="BOM-Grey Roll-010")
        data = mock_insert.call_args[0][0]
        self.assertEqual(data["items"][0]["bom_no"], "BOM-Grey Roll-010")

    @patch("frappe.db.exists", return_value=True)
    @patch("frappe.db.get_single_value", return_value="WH-1")
    @patch.object(BOMService, "_insert_and_submit_bom", return_value="BOM-Shemagh-XXX")
    def test_shemagh_pins_finished_roll_bom(self, mock_insert, mock_wh, mock_exists):
        BOMService._create_bom_shemagh(_dm(article_name="Atlas"), finished_roll_bom="BOM-Finished Roll-011")
        data = mock_insert.call_args[0][0]
        self.assertEqual(data["items"][0]["bom_no"], "BOM-Finished Roll-011")


class TestDynamicModeChainsBomNoAcrossStages(unittest.TestCase):
    """Reproduces the live bug: a stage's BOM references the previous
    stage's bom_no, and ERPNext refuses that reference until the previous
    BOM is submitted. Since BOMs are created in Draft for manual review
    (not auto-submitted), _create_boms_dynamic must create ONE stage's BOM
    per call and stop — never attempt a stage whose predecessor isn't
    submitted yet, and never build two stages' BOMs in the same call."""

    def _stage(self, seq, name, output_item, bom_no=None, is_final=False):
        return frappe._dict({
            "stage_seq": seq, "stage_name": name, "output_item": output_item,
            "output_qty": 1, "bom_no": bom_no, "is_final_stage": is_final,
            "name": f"row-{seq}",
        })

    @patch("frappe.db.set_value")
    @patch("frappe.msgprint")
    @patch.object(BOMService, "_get_default_workstation", return_value="WS-1")
    @patch.object(BOMService, "_get_source_wh_for_stage", return_value="WH-1")
    @patch.object(BOMService, "_insert_and_submit_bom")
    def test_first_call_creates_only_first_stage_and_stops(self, mock_insert, mock_source_wh, mock_ws, mock_msg, mock_set_value):
        mock_insert.return_value = "BOM-Warping-XXX"
        dm = _dm(
            design_no="561", article_name="Atlas", warp_recipe=None,
            stage_configuration=[
                self._stage(1, "Warping", "Warping Beam"),
                self._stage(2, "Grey Roll", "Grey Roll"),
            ],
        )
        results = BOMService._create_boms_dynamic(dm)

        mock_insert.assert_called_once()
        self.assertEqual(results, {"Warping": "BOM-Warping-XXX"})

    @patch("frappe.db.set_value")
    @patch("frappe.msgprint")
    @patch.object(BOMService, "_get_default_workstation", return_value="WS-1")
    @patch.object(BOMService, "_get_source_wh_for_stage", return_value="WH-1")
    @patch.object(BOMService, "_insert_and_submit_bom")
    def test_second_stage_pins_first_stages_bom_once_first_is_submitted(self, mock_insert, mock_source_wh, mock_ws, mock_msg, mock_set_value):
        """Once stage 1's BOM is confirmed SUBMITTED (docstatus=1), the next
        call creates stage 2's BOM referencing it via bom_no."""
        mock_insert.return_value = "BOM-Grey-XXX"
        dm = _dm(
            design_no="561", article_name="Atlas", warp_recipe=None,
            stage_configuration=[
                self._stage(1, "Warping", "Warping Beam", bom_no="BOM-Warping-XXX"),
                self._stage(2, "Grey Roll", "Grey Roll"),
            ],
        )
        with patch("frappe.db.exists", return_value=True), \
             patch("frappe.db.get_value", return_value=1):  # docstatus=1, submitted
            results = BOMService._create_boms_dynamic(dm)

        mock_insert.assert_called_once()
        grey_roll_call = mock_insert.call_args[0][0]
        self.assertEqual(grey_roll_call["items"][0]["bom_no"], "BOM-Warping-XXX")
        # results includes stage 1 (already-submitted, confirmed) AND stage 2 (newly created)
        self.assertEqual(results, {"Warping": "BOM-Warping-XXX", "Grey Roll": "BOM-Grey-XXX"})

    @patch("frappe.db.set_value")
    @patch("frappe.msgprint")
    @patch.object(BOMService, "_insert_and_submit_bom")
    def test_stops_and_does_not_create_next_stage_while_previous_is_draft(self, mock_insert, mock_msg, mock_set_value):
        """Stage 1's BOM exists but is still Draft (docstatus=0) — must NOT
        attempt stage 2's BOM at all, and must tell the user to submit stage
        1 first."""
        dm = _dm(
            design_no="561", article_name="Atlas", warp_recipe=None,
            stage_configuration=[
                self._stage(1, "Warping", "Warping Beam", bom_no="BOM-Warping-DRAFT"),
                self._stage(2, "Grey Roll", "Grey Roll"),
            ],
        )
        with patch("frappe.db.exists", return_value=True), \
             patch("frappe.db.get_value", return_value=0):  # docstatus=0, still Draft
            results = BOMService._create_boms_dynamic(dm)

        mock_insert.assert_not_called()
        self.assertEqual(results, {})
        mock_msg.assert_called_once()
        self.assertIn("Draft", mock_msg.call_args[0][0])
