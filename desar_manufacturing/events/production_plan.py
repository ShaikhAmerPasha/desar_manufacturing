"""
DESAR Manufacturing — Production Plan Event Handlers

validate: round sub_assembly_items qty up to a whole number for
whole-number-UOM items. ERPNext's own MRP explosion computes these
via a plain BOM-ratio division with no rounding, so a Sales Order
qty that isn't an exact multiple of the BOM ratio leaves a fractional
requirement that later blocks Work Order creation entirely.

Also applies an optional Production Buffer % (custom_production_buffer_pct)
to po_items.planned_qty, so a manufacturing-loss allowance doesn't have to
be hand-typed onto every line.
"""
import frappe
from frappe.utils import flt

from desar_manufacturing.utils.validation_utils import round_up_if_needed

# Sub-assembly items are shared WIP items across every design (Warping Beam,
# Grey Roll, ...) — "Get Sub Assembly Items" only fills fg_warehouse when the
# whole plan has one uniform Sub Assembly Warehouse set, which doesn't fit a
# multi-stage flow where each item sits in a different physical warehouse.
SUB_ASSEMBLY_WAREHOUSE_FIELD = {
	"Warping Beam": "warping_wip_warehouse",
	"Beam Roll": "warping_wip_warehouse",
	"Grey Roll": "loom_floor_warehouse",
	"Finished Roll": "finishing_wip_warehouse",
}


def validate(doc, method=None):
	for row in doc.get("sub_assembly_items") or []:
		_round_row_qty(row)
		_autofill_sub_assembly_warehouse(row)
	_apply_production_buffer(doc)


def _round_row_qty(row):
	if not row.stock_uom or not row.qty:
		return
	must_be_whole = frappe.get_cached_value("UOM", row.stock_uom, "must_be_whole_number")
	rounded = round_up_if_needed(row.qty, bool(must_be_whole))
	if rounded != row.qty:
		row.qty = rounded


def _autofill_sub_assembly_warehouse(row):
	"""Always enforces the correct warehouse for these shared WIP items —
	not just when blank. Item Default/core fallback resolution can leave a
	stale or generic warehouse here that isn't blank but is still wrong for
	this app's stage layout, and there's exactly one correct answer per item."""
	field = SUB_ASSEMBLY_WAREHOUSE_FIELD.get(row.production_item)
	if not field:
		return
	warehouse = frappe.db.get_single_value("DESAR Settings", field)
	if warehouse:
		row.fg_warehouse = warehouse


def _apply_production_buffer(doc):
	"""Only while still Draft. Anchored to the Sales Order Item's own qty,
	NOT row.pending_qty — core's set_pending_qty_in_row_without_reference()
	(production_plan.py) has an `or` where it should have an `and`
	(`if not item.sales_order or not item.material_request`), so it fires
	for every normal SO-linked row too (they never have material_request
	set) and resets pending_qty = planned_qty on every single save. Reading
	pending_qty here would compound the buffer on each resave (500 -> 575
	-> 661.25 -> ...). The Sales Order Item's qty is never touched by any
	of this, so it's the only stable base to multiply."""
	buffer_pct = flt(doc.get("custom_production_buffer_pct"))
	if not buffer_pct or doc.docstatus != 0:
		return
	for row in doc.get("po_items") or []:
		if row.sales_order and row.sales_order_item:
			so_qty = flt(frappe.db.get_value("Sales Order Item", row.sales_order_item, "qty"))
			if so_qty:
				row.planned_qty = round(so_qty * (1 + buffer_pct / 100))
