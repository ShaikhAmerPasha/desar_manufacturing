"""
Stock Entry event handlers.
THIN layer — validates trigger conditions, delegates to services.
No business logic here.

Supports both dynamic (Stage Configuration) and legacy (hardcoded Grey Roll) modes.
"""
import frappe
from desar_manufacturing.constants import GREY_ROLL


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
