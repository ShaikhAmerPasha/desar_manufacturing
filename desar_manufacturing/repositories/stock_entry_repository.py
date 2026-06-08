"""
DESAR Manufacturing — Stock Entry Repository
"""
import frappe
from typing import Optional
from desar_manufacturing.utils.batch_utils import get_batch_from_row
from desar_manufacturing.constants import WARPING_BEAM


class StockEntryRepository:

    @classmethod
    def get_finished_item_batch(cls, se_name: str, item_code: str) -> Optional[str]:
        """
        Get the batch number of a finished item from a Stock Entry.

        Reads from Stock Ledger Entry — reliable in v15 because SLE is
        written before on_submit fires, unlike serial_and_batch_bundle
        on the SE row which may not be linked yet at event time.
        """
        # Method 1: Direct batch_no on SLE
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

        # Method 2: Via Serial and Batch Bundle on SLE
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

    @classmethod
    def get_consumed_beam_batch(cls, se_name: str) -> Optional[str]:
        """Get the Warping Beam batch consumed in a Stock Entry."""
        try:
            se = frappe.get_doc("Stock Entry", se_name)
            for row in se.items:
                if row.item_code == WARPING_BEAM and not row.is_finished_item:
                    return get_batch_from_row(row)
        except frappe.DoesNotExistError:
            pass
        return None

    @classmethod
    def get_work_order(cls, se_name: str) -> Optional[str]:
        """Get the Work Order linked to a Stock Entry."""
        return frappe.db.get_value("Stock Entry", se_name, "work_order")

    @classmethod
    def get_valuation_rate(cls, item_code: str, warehouse: str) -> float:
        """Get the most recent valuation rate for an item in a warehouse."""
        result = frappe.db.get_value(
            "Stock Ledger Entry",
            filters={
                "item_code": item_code,
                "warehouse": warehouse,
                "is_cancelled": 0,
            },
            fieldname="valuation_rate",
            order_by="posting_date desc, posting_time desc",
        )
        return float(result or 0)
