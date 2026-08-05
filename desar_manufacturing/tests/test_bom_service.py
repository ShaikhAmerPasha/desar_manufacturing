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
    """Reproduces the live bug: with 2 designs sharing "Grey Roll" as an
    output item, the 2nd design's Finished Roll BOM must reference its OWN
    Grey Roll BOM, not whichever one is currently the item's default."""

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
    def test_second_stage_pins_first_stages_bom(self, mock_insert, mock_source_wh, mock_ws, mock_msg, mock_set_value):
        mock_insert.side_effect = ["BOM-Warping-XXX", "BOM-Grey-XXX"]
        dm = _dm(
            design_no="561", article_name="Atlas", warp_recipe=None,
            stage_configuration=[
                self._stage(1, "Warping", "Warping Beam"),
                self._stage(2, "Grey Roll", "Grey Roll"),
            ],
        )
        BOMService._create_boms_dynamic(dm)

        grey_roll_call = mock_insert.call_args_list[1][0][0]
        self.assertEqual(grey_roll_call["items"][0]["bom_no"], "BOM-Warping-XXX")

    @patch("frappe.db.set_value")
    @patch("frappe.msgprint")
    def test_existing_stage_bom_still_chains_to_next(self, mock_msg, mock_set_value):
        """A stage whose BOM already exists (skipped, not recreated) must
        still hand its bom_no down to the next stage."""
        with patch("frappe.db.exists", return_value=True), \
             patch.object(BOMService, "_get_source_wh_for_stage", return_value="WH-1"), \
             patch.object(BOMService, "_insert_and_submit_bom", return_value="BOM-Grey-NEW") as mock_insert:
            dm = _dm(
                design_no="561", article_name="Atlas", warp_recipe=None,
                stage_configuration=[
                    self._stage(1, "Warping", "Warping Beam", bom_no="BOM-Warping-EXISTING"),
                    self._stage(2, "Grey Roll", "Grey Roll"),
                ],
            )
            BOMService._create_boms_dynamic(dm)
            data = mock_insert.call_args[0][0]
            self.assertEqual(data["items"][0]["bom_no"], "BOM-Warping-EXISTING")
