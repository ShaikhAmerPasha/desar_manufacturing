"""
Stock Entry event handlers.
THIN layer — validates trigger conditions, delegates to services.
No business logic here.
"""
import frappe
from desar_manufacturing.constants import GREY_ROLL


def on_submit(doc, method):
    """
    Trigger: Stock Entry on_submit
    Condition: Manufacture purpose + Grey Roll as finished item
    Action: Delegate to RollTicketService

    NOTE: In ERPNext v15, serial_and_batch_bundle is not yet linked
    to the SE row at on_submit time. We read the batch from the
    Stock Ledger Entry instead, which is always written first.
    """
    if doc.purpose != "Manufacture":
        return

    for row in doc.items:
        if not row.is_finished_item:
            continue
        if row.item_code != GREY_ROLL:
            continue

        # Read batch from Stock Ledger Entry — reliable in v15
        batch_no = _get_batch_from_sle(doc.name, GREY_ROLL)

        if not batch_no:
            frappe.log_error(
                title="DESAR: Roll Ticket — Batch Not Found",
                message=(
                    "Grey Roll produced in SE {se} but batch could not be read from SLE.\n"
                    "Row idx: {idx}\n"
                    "Tried: Stock Ledger Entry for item={item}, se={se}"
                ).format(
                    se=doc.name,
                    idx=row.idx,
                    item=GREY_ROLL,
                ),
            )
            continue

        from desar_manufacturing.services.roll_ticket_service import RollTicketService
        RollTicketService.create_for_grey_roll(
            stock_entry_name=doc.name,
            batch_no=batch_no,
            qty=row.qty,
            uom=row.uom or "Nos",
        )


def _get_batch_from_sle(se_name, item_code):
    """
    Read batch number from Stock Ledger Entry.

    In v15, SLE is written before on_submit fires, making this
    more reliable than reading from serial_and_batch_bundle on the SE row.
    """
    # Method 1: Direct batch_no on SLE (v14 style, may still work)
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

    # Method 2: Via Serial and Batch Bundle linked on SLE
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
