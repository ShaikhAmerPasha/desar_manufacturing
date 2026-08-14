"""
Patch: one-time data correction for two bugs fixed in the code this same
release —

1. DESAR Stage Configuration rows for the Grey Roll stage were sometimes
   labelled stage_name="Grey Roll" instead of "Weaving". Every warehouse-
   routing function in this app keyword-matches stage_name looking for
   "weav"/"grey" — a row saying "Grey Roll" doesn't match, so it silently
   fell through to a generic fallback.

2. That fallback (before this release) used to write a hardcoded
   "<Purpose> - ST" placeholder warehouse name (left over from this app's
   original development site) onto the Work Order — a warehouse that does
   not exist on any other site. This corrupted Draft Work Orders' warehouse
   fields. Submitted Work Orders can't have this problem: ERPNext's own
   submit validation would have rejected a reference to a nonexistent
   warehouse, so only Draft (docstatus=0) rows are ever touched here.

Idempotent — safe to run again; already-correct rows are left untouched.
"""
import frappe

# Exact placeholder strings the old code used to hardcode, mapped to the
# DESAR Settings field holding the real warehouse for that same purpose.
BROKEN_WAREHOUSE_TO_SETTINGS_FIELD = {
    "Yarn Store - ST":                 "yarn_warehouse",
    "Chemical Store - ST":             "chemical_warehouse",
    "Accessories Store - ST":          "accessories_warehouse",
    "Warping WIP - ST":                "warping_wip_warehouse",
    "Loom Floor - ST":                 "loom_floor_warehouse",
    "Grey Roll Store - ST":            "grey_roll_warehouse",
    "Finishing WIP - ST":              "finishing_wip_warehouse",
    "Finished Roll Store - ST":        "finished_roll_warehouse",
    "Cutting and Packing Floor - ST":  "cutting_packing_warehouse",
    "Finished Goods Grade A - ST":     "fg_grade_a_warehouse",
    "Scrap Yard - ST":                 "scrap_warehouse",
}
# The old unmatched-stage fallback used a different literal and pulled from
# Manufacturing Settings instead of DESAR Settings.
GENERIC_FALLBACK_WAREHOUSE = "Work In Progress - ST"

WAREHOUSE_FIELDS = ["wip_warehouse", "source_warehouse", "fg_warehouse", "scrap_warehouse"]


def execute():
    if not frappe.db.exists("DocType", "DESAR Stage Configuration"):
        return  # app not installed on this site
    if not frappe.db.exists("DocType", "Work Order"):
        return

    _fix_weaving_stage_name()
    _fix_placeholder_warehouses()


def _fix_weaving_stage_name():
    bad_rows = frappe.get_all(
        "DESAR Stage Configuration",
        filters={"output_item": "Grey Roll", "stage_name": ["!=", "Weaving"]},
        pluck="name",
    )
    for name in bad_rows:
        frappe.db.set_value("DESAR Stage Configuration", name, "stage_name", "Weaving", update_modified=False)

    if bad_rows:
        frappe.db.commit()
        frappe.logger().info(
            f"DESAR patch: corrected stage_name -> 'Weaving' on {len(bad_rows)} "
            f"DESAR Stage Configuration row(s): {bad_rows}"
        )


def _fix_placeholder_warehouses():
    if not frappe.db.exists("DocType", "DESAR Settings"):
        return

    settings = frappe.db.get_singles_dict("DESAR Settings") or {}
    mfg_default_wip = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")

    broken_wos = frappe.get_all(
        "Work Order",
        filters={"docstatus": 0},
        or_filters=[[f, "like", "%- ST"] for f in WAREHOUSE_FIELDS],
        fields=["name"] + WAREHOUSE_FIELDS,
    )

    fixed_names = []
    skipped = []

    for wo in broken_wos:
        updates = {}
        for f in WAREHOUSE_FIELDS:
            value = wo.get(f)
            if not value or not value.endswith(" - ST"):
                continue

            if value == GENERIC_FALLBACK_WAREHOUSE:
                real_value = mfg_default_wip
            else:
                settings_field = BROKEN_WAREHOUSE_TO_SETTINGS_FIELD.get(value)
                real_value = settings.get(settings_field) if settings_field else None

            if real_value and frappe.db.exists("Warehouse", real_value):
                updates[f] = real_value
            else:
                skipped.append((wo.name, f, value))

        for f, v in updates.items():
            frappe.db.set_value("Work Order", wo.name, f, v, update_modified=False)
        if updates:
            fixed_names.append(wo.name)

    if fixed_names or skipped:
        frappe.db.commit()
        frappe.log_error(
            title="DESAR patch: fixed placeholder '- ST' warehouses on Work Orders",
            message=(
                f"Corrected {len(fixed_names)} Draft Work Order(s): {fixed_names}\n\n"
                f"Could NOT auto-resolve (that DESAR Settings field is itself blank "
                f"on this site — needs manual configuration, then re-save these "
                f"Work Orders by hand): {skipped}"
            ),
        )
