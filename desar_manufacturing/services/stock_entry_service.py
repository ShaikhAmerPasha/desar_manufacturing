"""
DESAR Stock Entry Service

Creates Transfer and Manufacture Stock Entries for Work Orders.

make_stock_entry returns a frappe._dict — must wrap in frappe.get_doc()
to get a proper Document with .save() and .submit() methods.
"""
import frappe
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry


def _to_doc(se_dict) -> object:
	"""Convert frappe._dict from make_stock_entry into a saveable Document."""
	return frappe.get_doc(se_dict)


def make_transfer_se_draft(wo) -> object:
	"""Create a draft Material Transfer SE. Store worker reviews before submitting."""
	se = _to_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", wo.qty))
	se.save(ignore_permissions=True)
	return se


def make_transfer_se_auto(wo, prev_batch: str = "", prev_item: str = "") -> object:
	"""Create and auto-submit a Material Transfer SE.

	Overrides s_warehouse for the prev_item to match the WO's required_items
	source_warehouse, which _configure_wo already set to the correct location.
	"""
	se = _to_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", wo.qty))

	# Build a map of item_code → source_warehouse from the WO's required_items
	src_wh_map = {}
	for ri in wo.get("required_items") or []:
		if ri.source_warehouse:
			src_wh_map[ri.item_code] = ri.source_warehouse

	for row in se.items:
		# Override source warehouse from WO required_items
		if row.item_code in src_wh_map:
			row.s_warehouse = src_wh_map[row.item_code]
		# Set batch for the previous stage's output item
		if prev_batch and prev_item and row.item_code == prev_item and not row.batch_no:
			row.batch_no = prev_batch
			row.use_serial_batch_fields = 1

	se.save(ignore_permissions=True)
	se.submit()
	return se


def make_manufacture_se_draft(wo, prev_batch: str = "", prev_item: str = "") -> object:
	"""Create a draft Manufacture SE. Packing supervisor reviews before submitting."""
	se = _to_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))

	if prev_batch and prev_item:
		for row in se.items:
			if row.item_code == prev_item and row.s_warehouse and not row.batch_no:
				row.batch_no = prev_batch
				row.use_serial_batch_fields = 1

	se.save(ignore_permissions=True)
	return se


def make_manufacture_se_auto(wo, prev_batch: str = "", prev_item: str = "") -> object:
	"""Create and auto-submit a Manufacture SE."""
	se = _to_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))

	if prev_batch and prev_item:
		for row in se.items:
			if row.item_code == prev_item and row.s_warehouse and not row.batch_no:
				row.batch_no = prev_batch
				row.use_serial_batch_fields = 1

	se.save(ignore_permissions=True)
	se.submit()
	return se