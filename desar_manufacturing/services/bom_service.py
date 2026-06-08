"""
DESAR Manufacturing — BOM Service

Auto-creates all 4 BOMs from a Design Master document.
Uses Warp Recipe for yarn items, Design Master for chemical quantities.
"""
import frappe
from frappe import _
from frappe.utils import flt
from typing import Optional

from desar_manufacturing.constants import (
    WARPING_BEAM, GREY_ROLL, FINISHED_ROLL
)


class BOMService:
    """Creates all 4 BOMs for a DESAR Design Master."""

    @classmethod
    def create_all_boms(cls, design_master_name: str) -> dict:
        """
        Create all 4 BOMs from a Design Master.
        Skips any BOM level that already exists on the Design Master.

        Returns:
            Dict of BOM names: {bom_level_1: "BOM-...", bom_level_2: "BOM-...", ...}
        """
        dm = frappe.get_doc("Design Master", design_master_name)

        cls._validate_design_master(dm)

        results = {}

        if not dm.bom_level_1:
            bom1 = cls._create_bom_warping_beam(dm)
            if bom1:
                frappe.db.set_value("Design Master", dm.name, "bom_level_1", bom1)
                results["bom_level_1"] = bom1

        if not dm.bom_level_2:
            bom2 = cls._create_bom_grey_roll(dm)
            if bom2:
                frappe.db.set_value("Design Master", dm.name, "bom_level_2", bom2)
                results["bom_level_2"] = bom2

        if not dm.bom_level_3:
            bom3 = cls._create_bom_finished_roll(dm)
            if bom3:
                frappe.db.set_value("Design Master", dm.name, "bom_level_3", bom3)
                results["bom_level_3"] = bom3

        if not dm.bom_level_4:
            bom4 = cls._create_bom_shemagh(dm)
            if bom4:
                frappe.db.set_value("Design Master", dm.name, "bom_level_4", bom4)
                results["bom_level_4"] = bom4

        if results:
            frappe.msgprint(
                _("Created {0} BOM(s): {1}").format(
                    len(results), ", ".join(results.values())
                ),
                alert=True,
            )
        else:
            frappe.msgprint(_("All BOMs already exist for this Design Master"), alert=True)

        return results

    # ── Private BOM builders ──────────────────────────────────────────────────

    @classmethod
    def _create_bom_warping_beam(cls, dm) -> Optional[str]:
        """BOM 1: Yarn items from Warp Recipe → Warping Beam."""
        if not dm.warp_recipe:
            frappe.throw(_("Warp Recipe is required on Design Master to create BOM 1"))

        wr = frappe.get_doc("Warp Recipe", dm.warp_recipe)
        if not wr.yarn_items:
            frappe.throw(_("Warp Recipe {0} has no yarn items").format(dm.warp_recipe))

        bom_items = []
        for item in wr.yarn_items:
            if not frappe.db.exists("Item", item.yarn_item):
                frappe.throw(
                    _("Item {0} from Warp Recipe does not exist in ERPNext").format(
                        item.yarn_item
                    )
                )
            bom_items.append({
                "item_code": item.yarn_item,
                "qty": flt(item.qty_kg),
                "uom": "Kg",
                "source_warehouse": frappe.db.get_single_value(
                    "DESAR Settings", "yarn_warehouse"
                ) or "",
            })

        return cls._insert_and_submit_bom({
            "item": WARPING_BEAM,
            "quantity": 1,
            "items": bom_items,
            "operations": [
                {
                    "operation": "Warping",
                    "workstation": "Warping Machine",
                    "time_in_mins": 120,
                }
            ],
            "custom_design_no": dm.design_no,
            "custom_article_name": dm.article_name,
            "custom_design_master": dm.name,
        })

    @classmethod
    def _create_bom_grey_roll(cls, dm) -> Optional[str]:
        """BOM 2: Warping Beam → Grey Roll."""
        return cls._insert_and_submit_bom({
            "item": GREY_ROLL,
            "quantity": 1,
            "items": [
                {
                    "item_code": WARPING_BEAM,
                    "qty": 1,
                    "uom": "Nos",
                    "source_warehouse": frappe.db.get_single_value("DESAR Settings", "warping_wip_warehouse") or "",
                }
            ],
            "operations": [
                {"operation": "Loom Loading", "workstation": "Loom 62", "time_in_mins": 30},
                {"operation": "Weaving", "workstation": "Loom 62", "time_in_mins": 480},
            ],
            "custom_design_no": dm.design_no,
            "custom_article_name": dm.article_name,
            "custom_design_master": dm.name,
        })

    @classmethod
    def _create_bom_finished_roll(cls, dm) -> Optional[str]:
        """BOM 3: Grey Roll + Chemicals → Finished Roll."""
        chemical_wh = frappe.db.get_single_value("DESAR Settings", "chemical_warehouse") or ""
        grey_roll_wh = frappe.db.get_single_value("DESAR Settings", "grey_roll_warehouse") or ""

        items = [
            {
                "item_code": GREY_ROLL,
                "qty": 1,
                "uom": "Nos",
                "source_warehouse": grey_roll_wh,
            }
        ]

        # Add chemicals from Design Master quantities
        chemical_items = [
            ("WashAgent", flt(dm.wash_agent_qty), "Litre"),
            ("FinishChem", flt(dm.finish_chem_qty), "Litre"),
            ("FlowerChem", flt(dm.flower_chem_qty), "Litre"),
        ]
        for item_code, qty, uom in chemical_items:
            if qty and frappe.db.exists("Item", item_code):
                items.append({
                    "item_code": item_code,
                    "qty": qty,
                    "uom": uom,
                    "source_warehouse": chemical_wh,
                })

        return cls._insert_and_submit_bom({
            "item": FINISHED_ROLL,
            "quantity": 1,
            "items": items,
            "operations": [
                {"operation": "Washing", "workstation": "Finishing Machine", "time_in_mins": 45},
                {"operation": "Chemical Finishing", "workstation": "Finishing Machine", "time_in_mins": 60},
                {"operation": "Flower Application", "workstation": "Finishing Machine", "time_in_mins": 30},
            ],
            "custom_design_no": dm.design_no,
            "custom_article_name": dm.article_name,
            "custom_design_master": dm.name,
        })

    @classmethod
    def _create_bom_shemagh(cls, dm) -> Optional[str]:
        """BOM 4: Finished Roll + Accessories → Shemagh pieces."""
        pcs = int(dm.pieces_per_roll or 50)
        size = dm.default_size or "60"
        article_code = (dm.article_name or "VIC")[:3].upper()
        item_code = "Shemagh-{0}-{1}-A".format(article_code, size)

        if not frappe.db.exists("Item", item_code):
            frappe.throw(
                _("Item <b>{0}</b> does not exist. "
                  "Create the item variant first, then retry.").format(item_code)
            )

        finished_roll_wh = frappe.db.get_single_value("DESAR Settings", "finished_roll_warehouse") or ""
        accessories_wh = frappe.db.get_single_value("DESAR Settings", "accessories_warehouse") or ""

        items = [
            {
                "item_code": FINISHED_ROLL,
                "qty": 1,
                "uom": "Nos",
                "source_warehouse": finished_roll_wh,
            }
        ]

        # Accessories
        box_item = dm.branded_box_item or "BrandedBox-{0}".format(size)
        label_item = dm.label_item or "LabelStamp"

        for acc_item in [box_item, label_item]:
            if frappe.db.exists("Item", acc_item):
                items.append({
                    "item_code": acc_item,
                    "qty": pcs,
                    "uom": "Nos",
                    "source_warehouse": accessories_wh,
                })

        return cls._insert_and_submit_bom({
            "item": item_code,
            "quantity": pcs,
            "items": items,
            "operations": [
                {"operation": "Cutting", "workstation": "Cutting Table", "time_in_mins": 30},
                {"operation": "Stitching and Trimming", "workstation": "Sewing Station", "time_in_mins": 45},
                {"operation": "Steaming", "workstation": "Steam Press", "time_in_mins": 20},
                {"operation": "Ironing", "workstation": "Iron Station", "time_in_mins": 40},
                {"operation": "Stamping", "workstation": "Stamp Press", "time_in_mins": 15},
                {"operation": "Final QC", "workstation": "QC Table", "time_in_mins": 20},
                {"operation": "Sorting", "workstation": "Sorting Table", "time_in_mins": 15},
                {"operation": "Boxing", "workstation": "Packing Station", "time_in_mins": 20},
            ],
            "custom_design_no": dm.design_no,
            "custom_article_name": dm.article_name,
            "custom_design_master": dm.name,
        })

    @classmethod
    def _insert_and_submit_bom(cls, data: dict) -> str:
        """Insert a BOM document and submit it."""
        bom = frappe.get_doc({
            "doctype": "BOM",
            "is_default": 1,
            "is_active": 1,
            "with_operations": 1,
            **data,
        })
        bom.insert(ignore_permissions=True)
        bom.submit()
        return bom.name

    @classmethod
    def _validate_design_master(cls, dm):
        """Validate Design Master has required fields before BOM creation."""
        errors = []
        if not dm.design_no:
            errors.append("Design No.")
        if not dm.article_name:
            errors.append("Article Name")
        if not dm.warp_recipe:
            errors.append("Warp Recipe")
        if not dm.weft_recipe:
            errors.append("Weft Recipe")
        if errors:
            frappe.throw(
                _("The following fields are required on Design Master: "
                  "<b>{0}</b>").format(", ".join(errors))
            )
