"""
DESAR Manufacturing — Work Order Event Handlers v3.4
before_validate:
1. Round qty / required_items qty for whole-number UOMs
2. Auto-fill Design context from BOM
3. Auto-set source_warehouse per stage (yarn/chemical/accessories store)
4. Auto-set wip_warehouse per stage
5. Auto-set target_warehouse per stage
6. Auto-set scrap_warehouse from DESAR Settings
7. Auto-set skip_transfer based on Stage Configuration

All of the above live in before_validate, not validate — Production Plan's
own create_work_order() sets wo.flags.ignore_validate = True before every
insert() it makes (erpnext/manufacturing/doctype/production_plan/production_plan.py),
which skips validate() (and any hooks.py-registered "validate" handler)
entirely. before_validate is NOT gated by that flag (Frappe's
run_before_save_methods() calls it first, then checks ignore_validate before
proceeding to validate) — confirmed by testing directly against Work Orders
created via Production Plan's bulk creation: a "validate" handler never ran,
custom_design_master stayed blank on all of them, while calling the same
logic directly always worked. This is the same reasoning already applied to
qty-rounding below; design-context/warehouse autofill needed the same fix.
"""
import frappe
from frappe import _

from desar_manufacturing.utils.validation_utils import round_up_if_needed


def before_insert(doc, method=None):
    """Insert-time alias for before_validate (see there for why)."""
    before_validate(doc, method)


def before_validate(doc, method=None):
    """
    Round qty up to a whole number before ERPNext's own validate_qty()/
    validate_uom_is_integer() can reject a fractional qty for a
    whole-number UOM.

    Must run at before_validate, not validate — Document.run_before_save_methods()
    calls before_validate before validate() for BOTH "save" and "submit"
    actions, and validate() bundles the core controller's own checks
    together with any hooks.py-registered validate handler, so a
    hooks-registered validate never gets a turn before the core one throws.

    before_validate (unlike before_insert) also fires on every later
    .save()/.submit() of an EXISTING document — needed because
    warping_service._resize_packing_wo resizes an already-inserted draft
    Work Order via .save(), not .insert(), and set_required_items() can
    reintroduce a fractional required_qty each time it recomputes.
    """
    _round_wo_qty(doc)
    _round_required_items_qty(doc)
    _autofill_design_context(doc)
    _autofill_warehouses(doc)
    _apply_skip_transfer(doc)


def _round_wo_qty(doc) -> None:
    if not doc.stock_uom or not doc.qty:
        return
    must_be_whole = frappe.get_cached_value("UOM", doc.stock_uom, "must_be_whole_number")
    rounded = round_up_if_needed(doc.qty, bool(must_be_whole))
    if rounded != doc.qty:
        doc.qty = rounded


def _round_required_items_qty(doc) -> None:
    """
    Same fractional-qty problem, one level down: ERPNext's own
    validate_uom_is_integer (work_order.py:169) checks required_qty on
    every required_items row the same way it checks the WO's own qty —
    BOM-ratio math (e.g. set_required_items() after cloning a WO to a
    smaller qty, as warping_service's beam-split does) can leave a
    fractional required_qty even when the row's stock_uom demands a
    whole number.
    """
    for row in doc.get("required_items") or []:
        if not row.stock_uom or not row.required_qty:
            continue
        must_be_whole = frappe.get_cached_value("UOM", row.stock_uom, "must_be_whole_number")
        rounded = round_up_if_needed(row.required_qty, bool(must_be_whole))
        if rounded != row.required_qty:
            row.required_qty = rounded


def validate(doc, method=None):
    """Skipped entirely when Production Plan bulk-creates a Work Order
    (ignore_validate=True) — see module docstring — so before_validate is
    what makes design context/warehouses/skip_transfer reliable. Re-running
    them here too, for a normal (non-Production-Plan) save/submit: this runs
    after core WorkOrder.validate() may have applied its own default
    warehouses, and our before_validate pass ran before that — re-applying
    here lets our stage-specific values win over a generic core default."""
    _autofill_design_context(doc)
    _autofill_warehouses(doc)
    _apply_skip_transfer(doc)
    # ERPNext's own WorkOrder.validate() checks required_qty for whole-number
    # UOMs BEFORE recomputing it via set_required_items() — see work_order.py
    # lines 169-174. That recompute can silently reintroduce a fraction
    # AFTER the check already passed, so before_validate's rounding alone
    # isn't enough for a normal (non-Production-Plan) save/submit — round
    # again here to catch the post-recompute value before it's persisted.
    _round_required_items_qty(doc)
    _reapply_forced_input_qty(doc)


def _reapply_forced_input_qty(doc) -> None:
    """
    roll_service._configure_wo forces the primary roll-input item's
    required_qty to 1 (a stage always consumes exactly one upstream roll,
    never a BOM ratio) and stashes which item_code via doc.flags, since
    set_required_items() would otherwise overwrite that qty right after.
    Re-apply it here, after that recompute has already happened.
    """
    item_code = doc.flags.get("desar_force_qty_1_item")
    if not item_code:
        return
    for row in doc.get("required_items") or []:
        if row.item_code == item_code:
            row.required_qty = 1


def before_submit(doc, method=None):
    """Ensure fields are updated/saved during submit."""
    validate(doc)


def on_cancel(doc, method=None):
    """Reset the DESAR Roll Chain stage this WO belonged to, if any."""
    from desar_manufacturing.services.roll_service import revert_work_order_reference
    revert_work_order_reference(doc.name)


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
        wh = _get_warehouses_for_stage(stage_lower, settings, default_wip)

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


def _get_warehouses_for_stage(stage_lower: str, settings, default_wip: str = "") -> dict:
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
        # Unrecognized stage_name (doesn't contain warp/weav/dye/finish/pack) —
        # fall back to the site's real Manufacturing Settings default WIP
        # warehouse instead of a hardcoded placeholder that may not exist on
        # this site (was "Work In Progress - ST", never created outside the
        # original dev environment).
        frappe.log_error(
            title="DESAR: unrecognized WO stage for warehouse autofill",
            message=f"stage_lower={stage_lower!r} did not match any known stage "
                    f"keyword; falling back to default WIP warehouse {default_wip!r}. "
                    f"Check DESAR Stage Configuration.stage_name for this item.",
        )
        return {
            "source": "",
            "wip":    default_wip,
            "target": default_wip,
        }
