"""
v15-compatible batch utilities.
In ERPNext v15, batch_no is stored in Serial and Batch Bundle, not on the stock entry row.
This module provides helper functions to extract batch information reliably.
"""
import frappe


def get_batch_from_row(row):
    """Extract batch_no from a stock entry row (v15 compatible).

    In v15, batch info is in the linked Serial and Batch Bundle document.
    Falls back to direct batch_no field for v14 compatibility.
    """
    # v15: check Serial and Batch Bundle first
    bundle_name = row.get("serial_and_batch_bundle")
    if bundle_name:
        try:
            entries = frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": bundle_name},
                fields=["batch_no"],
                limit=1,
            )
            if entries and entries[0].get("batch_no"):
                return entries[0].batch_no
        except Exception:
            pass

    # Fallback: direct batch_no field (v14 style or manual entry)
    if row.get("batch_no"):
        return row.batch_no

    return None


def get_all_batches_from_row(row):
    """Get all batch_nos from a stock entry row (for rows with multiple batches)."""
    batches = []
    bundle_name = row.get("serial_and_batch_bundle")
    if bundle_name:
        try:
            entries = frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": bundle_name},
                fields=["batch_no", "qty"],
            )
            for entry in entries:
                if entry.get("batch_no"):
                    batches.append({"batch_no": entry.batch_no, "qty": entry.qty})
        except Exception:
            pass

    if not batches and row.get("batch_no"):
        batches.append({"batch_no": row.batch_no, "qty": row.qty})

    return batches


def get_batch_from_sle(item_code, warehouse):
    """Get the latest batch for an item in a warehouse via Stock Ledger."""
    result = frappe.db.sql("""
        SELECT sbe.batch_no
        FROM `tabSerial and Batch Entry` sbe
        INNER JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
        INNER JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
        WHERE sle.item_code = %s AND sle.warehouse = %s
        AND sle.is_cancelled = 0
        ORDER BY sle.posting_date DESC, sle.posting_time DESC
        LIMIT 1
    """, (item_code, warehouse), as_dict=True)

    return result[0].batch_no if result else None


def get_batch_qty(batch_no, item_code=None, warehouse=None):
    """Get the current quantity of a batch across warehouses."""
    filters = {"batch_no": batch_no}
    if item_code:
        filters["item_code"] = item_code
    if warehouse:
        filters["warehouse"] = warehouse

    result = frappe.db.sql("""
        SELECT SUM(actual_qty) as qty
        FROM `tabStock Ledger Entry`
        WHERE batch_no = %s AND is_cancelled = 0
        {warehouse_filter}
    """.format(
        warehouse_filter="AND warehouse = %s" if warehouse else ""
    ), tuple(filter(None, [batch_no, warehouse])), as_dict=True)

    return result[0].qty if result and result[0].qty else 0
