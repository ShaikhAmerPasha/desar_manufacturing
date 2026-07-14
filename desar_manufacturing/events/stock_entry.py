"""
Stock Entry event handlers.
THIN layer — validates trigger conditions, delegates to services.
No business logic here.

Supports both dynamic (Stage Configuration) and legacy (hardcoded Grey Roll) modes.
"""
import frappe
from desar_manufacturing.constants import GREY_ROLL
from desar_manufacturing.services import batch_service
from desar_manufacturing.utils.validation_utils import round_up_if_needed


def before_validate(doc, method=None):
    """
    Round each item row's qty/transfer_qty up to a whole number before
    ERPNext's own validate_uom_is_integer (stock_entry.py:215-216) can
    reject a fractional value for a whole-number UOM.

    Same class of bug as the Work Order fix in events/work_order.py:
    quantities generated from a BOM ratio off a beam-split roll count
    (e.g. 81 pieces / 50 per roll = 1.62) can be fractional even when the
    item's UOM demands a whole number. Stock Entries created from a Work
    Order (roll_service/warping_service via stock_entry_service) copy the
    Work Order's required_qty straight into qty, so this needs the same
    guard independently — must run at before_validate (fires before core
    validate(), where the check actually happens), not validate.
    """
    for row in doc.get("items") or []:
        if row.uom and row.qty:
            must_be_whole = frappe.get_cached_value("UOM", row.uom, "must_be_whole_number")
            rounded = round_up_if_needed(row.qty, bool(must_be_whole))
            if rounded != row.qty:
                row.qty = rounded
        if row.stock_uom and row.transfer_qty:
            must_be_whole = frappe.get_cached_value("UOM", row.stock_uom, "must_be_whole_number")
            rounded = round_up_if_needed(row.transfer_qty, bool(must_be_whole))
            if rounded != row.transfer_qty:
                row.transfer_qty = rounded


def on_submit(doc, method):
    """
    Trigger: Stock Entry on_submit
    Condition: Manufacture purpose + Roll Ticket trigger item as finished item
    Action: Delegate to RollTicketService

    Dynamic mode: reads roll_ticket_trigger from Stage Configuration.
    Legacy mode: only triggers for Grey Roll (backward compatible).

    NOTE: In ERPNext v15, serial_and_batch_bundle is not yet linked
    to the SE row at on_submit time. We read the batch from the
    Stock Ledger Entry instead, which is always written first.
    """
    if doc.purpose != "Manufacture":
        return

    # Get trigger items — dynamic or legacy
    trigger_items = _get_roll_ticket_trigger_items(doc)

    for row in doc.items:
        if not row.is_finished_item:
            continue
        if row.item_code not in trigger_items:
            continue

        batch_no = _get_batch_from_sle(doc.name, row.item_code)

        if not batch_no:
            frappe.log_error(
                title="DESAR: Roll Ticket — Batch Not Found",
                message=(
                    "Item {item} produced in SE {se} but batch could not be read from SLE.\n"
                    "Row idx: {idx}"
                ).format(se=doc.name, idx=row.idx, item=row.item_code),
            )
            continue

        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        RollTicketService.create_for_grey_roll(
            stock_entry_name=doc.name,
            batch_no=batch_no,
            qty=row.qty,
            uom=row.uom or "Nos",
        )


def on_cancel(doc, method=None):
    """
    Trigger: Stock Entry on_cancel (Manufacture purpose only)
    Reverses roll_service's DESAR Roll Chain references to this SE/batch,
    and deletes any Roll Ticket that was auto-created for the produced
    batch and has no stage progress recorded on it yet.
    """
    if doc.purpose != "Manufacture":
        return

    from desar_manufacturing.services.roll_ticket_service import RollTicketService
    from desar_manufacturing.services.roll_service import revert_stock_entry_reference

    if any(row.is_finished_item for row in doc.items):
        batch_no = batch_service.get_batch_from_stock_entry(doc)
        if batch_no:
            RollTicketService.revert_roll_ticket_creation(batch_no)

    revert_stock_entry_reference(doc.name)


def _get_roll_ticket_trigger_items(doc) -> set:
    """
    Get the set of items that should trigger Roll Ticket creation.

    Dynamic mode: reads roll_ticket_trigger=1 from Stage Configuration
    via the Work Order's linked Design Master.

    Legacy mode: returns {GREY_ROLL} for backward compatibility.
    """
    from desar_manufacturing.config.settings_manager import SettingsManager

    # Try dynamic mode first
    try:
        if doc.work_order:
            design_master = frappe.db.get_value(
                "Work Order", doc.work_order, "custom_design_master"
            )
            if design_master:
                trigger_items = frappe.db.get_all(
                    "DESAR Stage Configuration",
                    filters={
                        "parent": design_master,
                        "parenttype": "Design Master",
                        "roll_ticket_trigger": 1,
                    },
                    fields=["output_item"],
                    pluck="output_item",
                )
                if trigger_items:
                    return set(trigger_items)
    except Exception:
        pass

    # Legacy fallback
    return {GREY_ROLL}


def _get_batch_from_sle(se_name, item_code):
    """
    Read batch number from Stock Ledger Entry.
    v15 compatible — SLE is written before on_submit fires.
    """
    result = frappe.db.get_value(
        "Stock Ledger Entry",
        filters={
            "voucher_no": se_name,
            "item_code": item_code,
            "actual_qty": [">", 0],
            "is_cancelled": 0,
        },
        fieldname="batch_no",
    )
    if result:
        return result

    sle_bundle = frappe.db.get_value(
        "Stock Ledger Entry",
        filters={
            "voucher_no": se_name,
            "item_code": item_code,
            "actual_qty": [">", 0],
            "is_cancelled": 0,
        },
        fieldname="serial_and_batch_bundle",
    )
    if sle_bundle:
        batch = frappe.db.get_value(
            "Serial and Batch Entry",
            filters={"parent": sle_bundle},
            fieldname="batch_no",
        )
        if batch:
            return batch

    return None
