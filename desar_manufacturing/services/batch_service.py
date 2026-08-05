"""
DESAR Batch Service

Utilities for extracting batch numbers from Stock Entry documents.
"""
import frappe


def get_batch_from_stock_entry(se) -> str:
	"""
	Extract the output batch number from a submitted Manufacture SE.

	Checks in order:
	  1. Finished item row batch_no field
	  2. Serial and Batch Bundle linked to finished item row
	  3. SLE created by the SE for the target warehouse
	"""
	if not se or not se.name:
		return ""

	# Method 1: direct batch_no on finished item row
	for row in se.items:
		if row.t_warehouse and row.is_finished_item and row.batch_no:
			return row.batch_no

	# Method 2: Serial and Batch Bundle on finished item row
	for row in se.items:
		if row.t_warehouse and row.is_finished_item and row.get("serial_and_batch_bundle"):
			batch = frappe.db.get_value(
				"Serial and Batch Entry",
				{"parent": row.serial_and_batch_bundle},
				"batch_no",
			)
			if batch:
				return batch

	# Method 3: SLE for target warehouse
	if se.docstatus == 1:
		sle = frappe.db.get_value(
			"Stock Ledger Entry",
			{
				"voucher_no":   se.name,
				"voucher_type": "Stock Entry",
				"actual_qty":   [">", 0],
				"is_cancelled": 0,
			},
			["batch_no", "item_code"],
			as_dict=True,
		)
		if sle and sle.batch_no:
			return sle.batch_no

	return ""


def get_batch_from_se_row(se_name: str, row_idx: int) -> str:
	"""Get batch from a specific SE row by idx."""
	bundle = frappe.db.get_value(
		"Stock Entry Detail",
		{"parent": se_name, "idx": row_idx},
		"serial_and_batch_bundle",
	)
	if bundle:
		return frappe.db.get_value(
			"Serial and Batch Entry",
			{"parent": bundle},
			"batch_no",
		) or ""
	return ""
