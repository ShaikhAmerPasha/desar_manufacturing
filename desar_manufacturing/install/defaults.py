"""Default inspection stages and reasons. Idempotent: existing rows are never changed."""
import frappe

STAGES = [
    {"stage_name": "Gray", "sequence": 1, "entry_mode": "Count", "is_final": 0},
    {"stage_name": "Finishing", "sequence": 2, "entry_mode": "Movement", "is_final": 0},
    {"stage_name": "Final", "sequence": 3, "entry_mode": "Real Count", "is_final": 1},
]

MOVEMENT_REASONS = [
    "Chemical finishing improved", "Ironing or steaming corrected", "Re-inspection correction",
    "Damage in handling", "Damage in cutting", "Stain or burn", "Machine damage", "Other",
]
LOSS_REASONS = [
    "Shrinkage", "Cutting waste", "Edge or selvedge trimming",
    "Sample or test piece", "Unaccounted or missing", "Other loss",
]
COUNT_GAIN_REASONS = ["Cutting gave extra piece", "Recount correction"]


def seed_inspection_defaults() -> None:
    for stage in STAGES:
        _insert_if_missing("Inspection Stage", stage["stage_name"], stage)
    for kind, reasons in (("Movement", MOVEMENT_REASONS), ("Loss", LOSS_REASONS),
                          ("Count Gain", COUNT_GAIN_REASONS)):
        for reason in reasons:
            _insert_if_missing("Inspection Reason", reason, {"reason": reason, "kind": kind})


def _insert_if_missing(doctype: str, name: str, values: dict) -> None:
    if not frappe.db.exists(doctype, name):
        frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def seed_piece_wip_warehouse() -> None:
    """Default the piece based WIP warehouse to the packing floor warehouse when unset."""
    if frappe.db.get_single_value("DESAR Settings", "piece_wip_warehouse"):
        return
    fallback = frappe.db.get_single_value("DESAR Settings", "cutting_packing_warehouse")
    if fallback:
        frappe.db.set_single_value("DESAR Settings", "piece_wip_warehouse", fallback)


def seed_factory_worker_role() -> None:
    if not frappe.db.exists("Role", "DESAR Factory Worker"):
        frappe.get_doc({"doctype": "Role", "role_name": "DESAR Factory Worker", "desk_access": 0}
                       ).insert(ignore_permissions=True)
