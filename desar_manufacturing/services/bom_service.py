"""
DESAR Manufacturing — BOM Service

Auto-creates BOMs from a Design Master document.

DYNAMIC MODE (when Design Master has Stage Configuration filled):
  Creates one BOM per stage in sequence order.
  Reads operations from Stage Configuration operations child table.
  Supports any number of stages — client configures, no code change needed.

LEGACY MODE (when Stage Configuration is empty):
  Creates exactly 4 BOMs (Warping Beam, Grey Roll, Finished Roll, Shemagh).
  Backward compatible with existing Design Masters.
"""
import frappe
from frappe import _
from frappe.utils import flt
from typing import Optional

from desar_manufacturing.constants import (
    WARPING_BEAM, GREY_ROLL, FINISHED_ROLL
)


class BOMService:
    """Creates all BOMs for a DESAR Design Master."""

    @classmethod
    def create_all_boms(cls, design_master_name: str) -> dict:
        """
        Create all BOMs from a Design Master.

        Dynamic mode: reads Stage Configuration child table.
        Legacy mode: creates 4 fixed BOMs.

        Returns:
            Dict of stage name/level to BOM name
        """
        dm = frappe.get_doc("Design Master", design_master_name)
        cls._validate_design_master(dm)

        # Check if Stage Configuration is filled
        if dm.get("stage_configuration"):
            return cls._create_boms_dynamic(dm)
        else:
            return cls._create_boms_legacy(dm)

    # ── Dynamic mode ──────────────────────────────────────────────────────────

    @classmethod
    def _create_boms_dynamic(cls, dm) -> dict:
        """
        Create BOMs from Stage Configuration child table.
        Each stage row defines one BOM level.
        """
        results = {}
        stages = sorted(dm.stage_configuration, key=lambda s: s.stage_seq)

        for stage in stages:
            # Skip if BOM already exists for this stage
            if stage.bom_no and frappe.db.exists("BOM", stage.bom_no):
                continue

            bom_name = cls._create_bom_for_stage(dm, stage, stages)
            if bom_name:
                # Update bom_no on the stage row
                frappe.db.set_value(
                    "DESAR Stage Configuration",
                    stage.name,
                    "bom_no",
                    bom_name
                )
                results[f"stage_{stage.stage_seq}_{stage.stage_name}"] = bom_name

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

    @classmethod
    def _create_bom_for_stage(cls, dm, stage, all_stages) -> Optional[str]:
        """
        Create a single BOM for a stage.

        Input items are determined by:
        1. Previous stage's output item (if any)
        2. Warp Recipe items (for first stage)
        3. Chemical items (from Design Master)
        4. Accessories (from Design Master)
        """
        stage_seq = stage.stage_seq
        output_item = stage.output_item

        if not output_item:
            frappe.throw(_("Stage {0} has no output item defined.").format(stage.stage_name))

        # Build input items
        bom_items = []

        # Previous stage output becomes this stage's input
        prev_stages = [s for s in all_stages if s.stage_seq < stage_seq]
        if prev_stages:
            prev_stage = sorted(prev_stages, key=lambda s: s.stage_seq)[-1]
            bom_items.append(cls._make_bom_item(
                item_code=prev_stage.output_item,
                qty=1,
                uom="Nos",
                source_warehouse=cls._get_wip_warehouse_for_item(prev_stage.output_item),
            ))

        # First stage — add yarn from Warp Recipe
        if not prev_stages and dm.warp_recipe:
            bom_items.extend(cls._get_yarn_items(dm))

        # Chemical items (if this stage produces Finished Roll)
        if output_item == FINISHED_ROLL or "finish" in stage.stage_name.lower():
            bom_items.extend(cls._get_chemical_items(dm))

        # Accessories (if this is the final stage)
        if stage.is_final_stage:
            bom_items.extend(cls._get_accessory_items(dm, int(stage.output_qty or 50)))

        # Build operations from Stage Operations child table
        operations = []
        if stage.get("operations"):
            for op in sorted(stage.operations, key=lambda o: o.sequence_id or 0):
                operations.append({
                    "operation":    op.operation,
                    "workstation":  op.workstation,
                    "time_in_mins": flt(op.time_in_mins),
                })

        # If no operations defined in Stage Config, add a default one
        # named after the stage itself — client can update later
        if not operations:
            default_ws = cls._get_default_workstation(stage.stage_name)
            if default_ws:
                operations.append({
                    "operation":    stage.stage_name,
                    "workstation":  default_ws,
                    "time_in_mins": 60,
                })

        return cls._insert_and_submit_bom({
            "item":               output_item,
            "quantity":           flt(stage.output_qty) or 1,
            "items":              bom_items,
            "operations":         operations,
            "custom_design_no":   dm.design_no,
            "custom_article_name": dm.article_name,
            "custom_design_master": dm.name,
        })

    @classmethod
    def _get_wip_warehouse_for_item(cls, item_code: str) -> str:
        """Get appropriate source warehouse for an intermediate item."""
        if item_code == WARPING_BEAM:
            return frappe.db.get_single_value("DESAR Settings", "warping_wip_warehouse") or ""
        elif item_code == GREY_ROLL:
            return frappe.db.get_single_value("DESAR Settings", "grey_roll_warehouse") or ""
        elif item_code == FINISHED_ROLL:
            return frappe.db.get_single_value("DESAR Settings", "finished_roll_warehouse") or ""
        return ""

    @classmethod
    def _make_bom_item(cls, item_code, qty, uom, source_warehouse="") -> dict:
        return {
            "item_code":        item_code,
            "qty":              qty,
            "uom":              uom,
            "source_warehouse": source_warehouse,
        }

    @classmethod
    def _get_yarn_items(cls, dm) -> list:
        """Get yarn items from Warp Recipe."""
        wr = frappe.get_doc("Warp Recipe", dm.warp_recipe)
        yarn_wh = frappe.db.get_single_value("DESAR Settings", "yarn_warehouse") or ""
        return [
            cls._make_bom_item(item.yarn_item, flt(item.qty_kg), "Kg", yarn_wh)
            for item in wr.yarn_items
            if frappe.db.exists("Item", item.yarn_item)
        ]

    @classmethod
    def _get_chemical_items(cls, dm) -> list:
        """Get chemical items from Design Master."""
        chemical_wh = frappe.db.get_single_value("DESAR Settings", "chemical_warehouse") or ""
        items = []
        for item_code, qty, uom in [
            ("WashAgent",  flt(dm.wash_agent_qty),  "Litre"),
            ("FinishChem", flt(dm.finish_chem_qty), "Litre"),
            ("FlowerChem", flt(dm.flower_chem_qty), "Litre"),
        ]:
            if qty and frappe.db.exists("Item", item_code):
                items.append(cls._make_bom_item(item_code, qty, uom, chemical_wh))
        return items

    @classmethod
    def _get_accessory_items(cls, dm, pcs: int) -> list:
        """Get accessory items from Design Master."""
        accessories_wh = frappe.db.get_single_value("DESAR Settings", "accessories_warehouse") or ""
        items = []
        size = dm.default_size or "60"
        for item_code in [
            dm.branded_box_item or f"BrandedBox-{size}",
            dm.label_item or "LabelStamp",
        ]:
            if frappe.db.exists("Item", item_code):
                items.append(cls._make_bom_item(item_code, pcs, "Nos", accessories_wh))
        return items

    # ── Legacy mode ───────────────────────────────────────────────────────────

    @classmethod
    def _create_boms_legacy(cls, dm) -> dict:
        """
        Legacy BOM creation — exactly 4 fixed BOMs.
        Used when Stage Configuration is not filled.
        """
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

    @classmethod
    def _create_bom_warping_beam(cls, dm) -> Optional[str]:
        if not dm.warp_recipe:
            frappe.throw(_("Warp Recipe is required on Design Master to create BOM 1"))

        wr = frappe.get_doc("Warp Recipe", dm.warp_recipe)
        if not wr.yarn_items:
            frappe.throw(_("Warp Recipe {0} has no yarn items").format(dm.warp_recipe))

        yarn_wh = frappe.db.get_single_value("DESAR Settings", "yarn_warehouse") or ""
        bom_items = [
            {"item_code": item.yarn_item, "qty": flt(item.qty_kg), "uom": "Kg",
             "source_warehouse": yarn_wh}
            for item in wr.yarn_items
            if frappe.db.exists("Item", item.yarn_item)
        ]

        return cls._insert_and_submit_bom({
            "item": WARPING_BEAM, "quantity": 1,
            "items": bom_items,
            "operations": [{"operation": "Warping", "workstation": "Warping Machine", "time_in_mins": 120}],
            "custom_design_no": dm.design_no, "custom_article_name": dm.article_name, "custom_design_master": dm.name,
        })

    @classmethod
    def _create_bom_grey_roll(cls, dm) -> Optional[str]:
        wip_wh = frappe.db.get_single_value("DESAR Settings", "warping_wip_warehouse") or ""
        return cls._insert_and_submit_bom({
            "item": GREY_ROLL, "quantity": 1,
            "items": [{"item_code": WARPING_BEAM, "qty": 1, "uom": "Nos", "source_warehouse": wip_wh}],
            "operations": [
                {"operation": "Loom Loading", "workstation": "Loom 62", "time_in_mins": 30},
                {"operation": "Weaving", "workstation": "Loom 62", "time_in_mins": 480},
            ],
            "custom_design_no": dm.design_no, "custom_article_name": dm.article_name, "custom_design_master": dm.name,
        })

    @classmethod
    def _create_bom_finished_roll(cls, dm) -> Optional[str]:
        chemical_wh = frappe.db.get_single_value("DESAR Settings", "chemical_warehouse") or ""
        grey_wh = frappe.db.get_single_value("DESAR Settings", "grey_roll_warehouse") or ""
        items = [{"item_code": GREY_ROLL, "qty": 1, "uom": "Nos", "source_warehouse": grey_wh}]
        for item_code, qty, uom in [
            ("WashAgent", flt(dm.wash_agent_qty), "Litre"),
            ("FinishChem", flt(dm.finish_chem_qty), "Litre"),
            ("FlowerChem", flt(dm.flower_chem_qty), "Litre"),
        ]:
            if qty and frappe.db.exists("Item", item_code):
                items.append({"item_code": item_code, "qty": qty, "uom": uom, "source_warehouse": chemical_wh})

        return cls._insert_and_submit_bom({
            "item": FINISHED_ROLL, "quantity": 1, "items": items,
            "operations": [
                {"operation": "Washing", "workstation": "Finishing Machine", "time_in_mins": 45},
                {"operation": "Chemical Finishing", "workstation": "Finishing Machine", "time_in_mins": 60},
                {"operation": "Flower Application", "workstation": "Finishing Machine", "time_in_mins": 30},
            ],
            "custom_design_no": dm.design_no, "custom_article_name": dm.article_name, "custom_design_master": dm.name,
        })

    @classmethod
    def _create_bom_shemagh(cls, dm) -> Optional[str]:
        pcs = int(dm.pieces_per_roll or 50)
        size = dm.default_size or "60"
        article_code = (dm.article_name or "VIC")[:3].upper()
        item_code = "Shemagh-{0}-{1}-A".format(article_code, size)

        if not frappe.db.exists("Item", item_code):
            frappe.throw(
                _("Item <b>{0}</b> does not exist. Create the item variant first.").format(item_code)
            )

        finished_wh = frappe.db.get_single_value("DESAR Settings", "finished_roll_warehouse") or ""
        accessories_wh = frappe.db.get_single_value("DESAR Settings", "accessories_warehouse") or ""
        items = [{"item_code": FINISHED_ROLL, "qty": 1, "uom": "Nos", "source_warehouse": finished_wh}]

        for acc in [dm.branded_box_item or f"BrandedBox-{size}", dm.label_item or "LabelStamp"]:
            if frappe.db.exists("Item", acc):
                items.append({"item_code": acc, "qty": pcs, "uom": "Nos", "source_warehouse": accessories_wh})

        return cls._insert_and_submit_bom({
            "item": item_code, "quantity": pcs, "items": items,
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
            "custom_design_no": dm.design_no, "custom_article_name": dm.article_name, "custom_design_master": dm.name,
        })

    # ── Shared ────────────────────────────────────────────────────────────────

    @classmethod
    def _get_default_workstation(cls, stage_name: str) -> str:
        """
        Get a default workstation for a stage when none is defined
        in the Stage Operations child table.
        Tries to find an existing Operation with same name first.
        Falls back to first available workstation.
        """
        stage_lower = stage_name.lower()
        # Try to find operation matching stage name
        op = frappe.db.get_value("Operation", {"name": stage_name}, "workstation")
        if op:
            return op
        # Keyword-based defaults
        if "warp" in stage_lower:
            return "Warping Machine"
        elif "weav" in stage_lower or "loom" in stage_lower:
            return "Loom 62"
        elif "dye" in stage_lower:
            return "Dyeing Machine"
        elif "finish" in stage_lower or "wash" in stage_lower:
            return "Finishing Machine"
        elif "pack" in stage_lower or "cut" in stage_lower:
            return "Cutting Table"
        # Last resort: first workstation in DB
        return frappe.db.get_value("Workstation", {}, "name") or ""

    @classmethod
    def _insert_and_submit_bom(cls, data: dict) -> str:
        operations = data.get("operations") or []
        bom = frappe.get_doc({
            "doctype": "BOM",
            "is_default": 1,
            "is_active": 1,
            "with_operations": 1 if operations else 0,
            **data
        })
        bom.insert(ignore_permissions=True)
        # Keep in Draft — client reviews and submits manually
        # This allows editing BOM items, operations, quantities before activating
        return bom.name

    @classmethod
    def _validate_design_master(cls, dm):
        errors = []
        if not dm.design_no:
            errors.append("Design No.")
        if not dm.article_name:
            errors.append("Article Name")
        if not dm.warp_recipe:
            errors.append("Warp Recipe")
        if errors:
            frappe.throw(
                _("The following fields are required: <b>{0}</b>").format(", ".join(errors))
            )