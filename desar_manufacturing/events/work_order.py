"""
DESAR Manufacturing — Work Order Event Handlers v3.3
validate / before_submit:
1. Auto-fill Design context from BOM
2. Auto-set source_warehouse per stage (yarn/chemical/accessories store)
3. Auto-set wip_warehouse per stage
4. Auto-set target_warehouse per stage
5. Auto-set scrap_warehouse from DESAR Settings
6. Auto-set skip_transfer based on Stage Configuration
"""
import frappe
from frappe import _


def validate(doc, method=None):
    """Auto-fill all warehouse, design, and skip_transfer fields before save."""
    _autofill_design_context(doc)
    _autofill_warehouses(doc)
    _apply_skip_transfer(doc)


def before_submit(doc, method=None):
    """Ensure fields are updated/saved during submit."""
    validate(doc)


def _autofill_design_context(doc):
    """Auto-fill Design No, Article Name, Design Master from BOM."""
    if doc.get("custom_design_no") and doc.get("custom_article_name"):
        return
    if not doc.bom_no:
        return
    try:
        if not frappe.db.has_column("BOM", "custom_design_no"):
            return
        bom_data = frappe.db.get_value(
            "BOM", doc.bom_no,
            ["custom_design_no", "custom_article_name", "custom_design_master"],
            as_dict=True,
        )
        if not bom_data:
            return
        if bom_data.custom_design_no and not doc.get("custom_design_no"):
            doc.custom_design_no = bom_data.custom_design_no
        if bom_data.custom_article_name and not doc.get("custom_article_name"):
            doc.custom_article_name = bom_data.custom_article_name
        if bom_data.custom_design_master and not doc.get("custom_design_master"):
            doc.custom_design_master = bom_data.custom_design_master
    except Exception:
        frappe.log_error(title="DESAR: WO design context auto-fill failed",
                        message=frappe.get_traceback())


def _autofill_warehouses(doc):
    """
    Auto-set source, wip, target, scrap warehouses based on stage.
    Only fills if not already set by user or if they match system defaults.
    """
    try:
        settings = frappe.get_cached_doc("DESAR Settings")
        mfg_settings = frappe.get_cached_doc("Manufacturing Settings")
        default_fg = mfg_settings.get("default_fg_warehouse")
        default_wip = mfg_settings.get("default_wip_warehouse")

        production_item = doc.production_item or ""
        design_master = doc.get("custom_design_master")

        stage_name = ""
        if design_master:
            stage_name = frappe.db.get_value(
                "DESAR Stage Configuration",
                {"parent": design_master, "output_item": production_item},
                "stage_name"
            ) or ""

        stage_lower = stage_name.lower()
        wh = _get_warehouses_for_stage(stage_lower, settings)

        if (not doc.source_warehouse) and wh.get("source"):
            doc.source_warehouse = wh["source"]
        if (not doc.wip_warehouse or doc.wip_warehouse == default_wip) and wh.get("wip"):
            doc.wip_warehouse = wh["wip"]
        if (not doc.fg_warehouse or doc.fg_warehouse == default_fg) and wh.get("target"):
            doc.fg_warehouse = wh["target"]
        if not doc.scrap_warehouse:
            doc.scrap_warehouse = settings.get("scrap_warehouse") or "Scrap Yard - ST"

    except Exception:
        frappe.log_error(title="DESAR: WO warehouse auto-fill failed",
                        message=frappe.get_traceback())


def _apply_skip_transfer(doc):
    """Set skip_transfer based on Stage Configuration — server-side."""
    design_master = doc.get("custom_design_master")
    production_item = doc.production_item or ""
    if not design_master or not production_item:
        return
    try:
        stage = frappe.db.get_value(
            "DESAR Stage Configuration",
            {"parent": design_master, "output_item": production_item},
            ["stage_name", "skip_transfer"],
            as_dict=True
        )
        if not stage:
            return
        should_skip = 0
        if stage.get("skip_transfer"):
            should_skip = 1
        else:
            stage_lower = (stage.get("stage_name") or "").lower()
            if "warp" in stage_lower:
                should_skip = 1
        doc.skip_transfer = should_skip
    except Exception:
        frappe.log_error(title="DESAR: WO skip_transfer logic failed",
                        message=frappe.get_traceback())


def _get_warehouses_for_stage(stage_lower: str, settings) -> dict:
    """Return source/wip/target warehouses for a stage."""
    def s(field, fallback):
        return settings.get(field) or fallback

    if "warp" in stage_lower:
        return {
            "source": s("yarn_warehouse", "Yarn Store - ST"),
            "wip":    s("warping_wip_warehouse", "Warping WIP - ST"),
            "target": s("warping_wip_warehouse", "Warping WIP - ST"),
        }
    elif "weav" in stage_lower:
        return {
            "source": s("warping_wip_warehouse", "Warping WIP - ST"),
            "wip":    s("loom_floor_warehouse", "Loom Floor - ST"),
            "target": s("grey_roll_warehouse", "Grey Roll Store - ST"),
        }
    elif "dye" in stage_lower:
        return {
            "source": s("chemical_warehouse", "Chemical Store - ST"),
            "wip":    s("finishing_wip_warehouse", "Finishing WIP - ST"),
            "target": s("finishing_wip_warehouse", "Finishing WIP - ST"),
        }
    elif "finish" in stage_lower:
        return {
            "source": s("chemical_warehouse", "Chemical Store - ST"),
            "wip":    s("finishing_wip_warehouse", "Finishing WIP - ST"),
            "target": s("finished_roll_warehouse", "Finished Roll Store - ST"),
        }
    elif "pack" in stage_lower:
        return {
            "source": s("accessories_warehouse", "Accessories Store - ST"),
            "wip":    s("cutting_packing_warehouse", "Cutting and Packing Floor - ST"),
            "target": s("fg_grade_a_warehouse", "Finished Goods Grade A - ST"),
        }
    else:
        return {
            "source": "",
            "wip":    "Work In Progress - ST",
            "target": "Work In Progress - ST",
        }
