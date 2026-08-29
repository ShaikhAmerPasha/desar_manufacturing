"""
DESAR Stage Status Service

Single source of truth for DESAR Production Order's `status` and
`current_stage` fields. Called after every stage-transition write in
warping_service.py and roll_service.py so the list view always reflects
where the order actually is, not just Draft/Submitted/Completed.
"""
from collections import Counter

import frappe

# Direct Stock Entry link fields, in the doctypes that hold them.
_PO_SE_FIELDS = ["warping_transfer_se", "warping_manufacture_se", "beam_split_se"]
_ROLL_CHAIN_SE_FIELDS = ["repack_se", "packing_manufacture_se"]
_ROLL_CHAIN_WO_FIELDS = ["grey_roll_wo", "finished_roll_wo", "packing_wo"]


def find_production_order_for_stock_entry(stock_entry: str) -> str | None:
	"""Reverse-lookup: which DESAR Production Order does this Stock Entry
	belong to? Grey/Finished/Packing Transfer + Manufacture SEs aren't stored
	by name anywhere (the roll dashboard fetches them live by work_order), so
	those are matched via the Stock Entry's own work_order field instead."""
	work_order = frappe.db.get_value("Stock Entry", stock_entry, "work_order")
	if work_order:
		po = frappe.db.get_value("DESAR Production Order", {"warping_wo": work_order}, "name")
		if po:
			return po
		for fieldname in _ROLL_CHAIN_WO_FIELDS:
			parent = frappe.db.get_value("DESAR Roll Chain", {fieldname: work_order}, "parent")
			if parent:
				return parent

	for fieldname in _PO_SE_FIELDS:
		po = frappe.db.get_value("DESAR Production Order", {fieldname: stock_entry}, "name")
		if po:
			return po

	for fieldname in _ROLL_CHAIN_SE_FIELDS:
		parent = frappe.db.get_value("DESAR Roll Chain", {fieldname: stock_entry}, "parent")
		if parent:
			return parent

	return None


def find_production_order_for_quality_inspection(quality_inspection: str) -> str | None:
	"""qi_service.make_roll_qi always points reference_type/reference_name at
	the roll's Manufacture SE — reuse the Stock Entry lookup via that."""
	row = frappe.db.get_value(
		"Quality Inspection", quality_inspection, ["reference_type", "reference_name"], as_dict=True
	)
	if not row or row.reference_type != "Stock Entry" or not row.reference_name:
		return None
	return find_production_order_for_stock_entry(row.reference_name)


def refresh_stage_status(po) -> None:
	"""Reload po, recompute status + current_stage, write if changed."""
	po.reload()

	new_status = _compute_status(po)
	new_stage = _compute_current_stage(po)

	if po.status != new_status:
		po.db_set("status", new_status, update_modified=True)
	if po.current_stage != new_stage:
		po.db_set("current_stage", new_stage, update_modified=False)


def _compute_status(po) -> str:
	rolls = po.roll_chains
	if not rolls:
		if po.warping_status in ("In Progress", "Completed") or po.beam_split_status == "Completed":
			return "In Progress"
		return "Submitted"

	all_done = all(r.roll_status == "Completed" for r in rolls)
	any_progress = any(r.roll_status in ("In Progress", "Completed") for r in rolls)

	if all_done and po.warping_status == "Completed" and po.beam_split_status == "Completed":
		return "Completed"
	if any_progress or po.warping_status in ("In Progress", "Completed"):
		return "In Progress"
	return "Submitted"


def _compute_current_stage(po) -> str:
	if po.warping_status != "Completed":
		return "Warping"
	if po.beam_split_status != "Completed":
		return "Beam Split"
	if not po.roll_chains:
		return "Beam Split"

	labels = [_roll_stage_label(r) for r in po.roll_chains]
	distinct = set(labels)
	if len(distinct) == 1:
		return labels[0]

	counts = Counter(labels)
	return ", ".join(f"{label}: {count}" for label, count in counts.most_common())


def _roll_stage_label(roll) -> str:
	"""Mirrors the stage precedence used by _add_roll_buttons in
	desar_production_order.js, so list view and form dashboard agree."""
	if roll.roll_status == "Completed":
		return "Completed"
	if roll.packing_status == "In Progress" or (
		roll.finished_roll_status == "Completed" and roll.packing_status == "Not Started"
	):
		return "Packing"
	if roll.finished_roll_status == "In Progress" or (
		roll.grey_roll_status == "Completed" and roll.finished_roll_status == "Not Started"
	):
		return "Finished Roll"
	return "Grey Roll"
