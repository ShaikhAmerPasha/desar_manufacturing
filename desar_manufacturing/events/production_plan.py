"""
DESAR Manufacturing — Production Plan Event Handlers

validate: round sub_assembly_items qty up to a whole number for
whole-number-UOM items. ERPNext's own MRP explosion computes these
via a plain BOM-ratio division with no rounding, so a Sales Order
qty that isn't an exact multiple of the BOM ratio leaves a fractional
requirement that later blocks Work Order creation entirely.
"""
import frappe

from desar_manufacturing.utils.validation_utils import round_up_if_needed


def validate(doc, method=None):
	for row in doc.get("sub_assembly_items") or []:
		_round_row_qty(row)


def _round_row_qty(row):
	if not row.stock_uom or not row.qty:
		return
	must_be_whole = frappe.get_cached_value("UOM", row.stock_uom, "must_be_whole_number")
	rounded = round_up_if_needed(row.qty, bool(must_be_whole))
	if rounded != row.qty:
		row.qty = rounded
