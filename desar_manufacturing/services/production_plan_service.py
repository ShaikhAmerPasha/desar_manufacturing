"""
DESAR Production Plan Service v7

Creates ONE DESAR Production Order per Sales Order line.

Key responsibility:
  - Forces Warping WO qty=1, drops the auto-created Beam Roll WO
  - Leaves Grey/Finished/Packing WOs untouched (still combined) —
    Beam Split decides real roll count and per-roll qty later
  - Creates 1 DESAR PO with the real Sales Order qty as total_qty
"""
import frappe
from frappe import _
from frappe.utils import cint

from desar_manufacturing.services import wo_split_helpers as wo


# ── Public ────────────────────────────────────────────────────────────────────


def create_desar_po_from_plan(production_plan: str, design_master: str = None) -> dict:
	"""
	Create one DESAR Production Order from a Production Plan, for one design.

	`design_master` is optional — omit it for a single-design plan (resolved
	automatically, exactly as before). Pass it explicitly when a plan holds
	Work Orders for multiple designs (e.g. one Sales Order with several
	design lines combined into one Production Plan by ERPNext's MRP tooling)
	— call this once per design_master from list_design_masters_for_plan().

	Roll count and per-roll qty are NOT decided here — Beam Split
	(warping_service.split_beam) owns that, once the supervisor has
	seen the physical beam. This only sets up Warping and total_qty.
	"""
	design_master = design_master or _get_design_master(production_plan)
	if not design_master:
		frappe.throw(_(
			"Cannot determine Design Master. "
			"Set custom_design_master on at least one Work Order."
		))

	if frappe.db.exists(
		"DESAR Production Order",
		{"production_plan": production_plan, "design_master": design_master, "docstatus": 1},
	):
		frappe.throw(_("DESAR Production Order already exists for this Production Plan and Design Master."))

	dm              = frappe.get_cached_doc("Design Master", design_master)
	stage_configs   = {sc.output_item: sc for sc in dm.stage_configuration}
	pieces_per_roll = cint(dm.pieces_per_roll) or 50

	wos          = _load_design_wos(production_plan, design_master)
	warping_item = wo.find_item_by_keywords(stage_configs, ("warp",))
	packing_item = wo.find_final_item(stage_configs)

	_configure_warping_wo(wos, warping_item)

	sales_order = _get_sales_order(production_plan)
	total_qty   = _resolve_total_qty(production_plan, packing_item, wos, stage_configs, pieces_per_roll)

	po = frappe.get_doc({
		"doctype":          "DESAR Production Order",
		"production_plan":  production_plan,
		"sales_order":      sales_order,
		"design_master":    design_master,
		"article_name":     dm.article_name,
		"design_no":        dm.design_no,
		"total_qty":        total_qty,
		"pieces_per_roll":  pieces_per_roll,
		"warping_wo":       wo.find_combined_wo(wos, warping_item) or "",
		"warping_status":   "Not Started",
		"beam_split_status": "Not Started",
	})
	po.insert(ignore_permissions=True)
	po.submit()

	_stamp_design_master(design_master, dm, [w.name for w in wos])

	return {"production_order": po.name, "total_qty": total_qty}


def preview_plan(production_plan: str, design_master: str = None) -> dict:
	"""Return preview info for confirmation dialog."""
	design_master = design_master or _get_design_master(production_plan)
	if not design_master:
		return {"error": "Cannot determine Design Master"}

	dm              = frappe.get_cached_doc("Design Master", design_master)
	stage_configs   = {sc.output_item: sc for sc in dm.stage_configuration}
	pieces_per_roll = cint(dm.pieces_per_roll) or 50
	packing_item    = wo.find_final_item(stage_configs)
	wos             = _load_design_wos(production_plan, design_master)

	already_exists = frappe.db.exists(
		"DESAR Production Order",
		{"production_plan": production_plan, "design_master": design_master, "docstatus": 1},
	)

	return {
		"design_master":   design_master,
		"article_name":    dm.article_name,
		"design_no":       dm.design_no,
		"pieces_per_roll": pieces_per_roll,
		"total_qty":       _resolve_total_qty(production_plan, packing_item, wos, stage_configs, pieces_per_roll),
		"already_exists":  bool(already_exists),
	}


def list_design_masters_for_plan(production_plan: str) -> list:
	"""Distinct Design Masters across this plan's Work Orders — lets a
	multi-design Sales Order/Production Plan create one DESAR PO per design."""
	wos = frappe.get_all(
		"Work Order",
		filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
		fields=["custom_design_master"],
		distinct=True,
	)
	return sorted({w.custom_design_master for w in wos if w.custom_design_master})


# ── Warping WO setup ──────────────────────────────────────────────────────────


def _configure_warping_wo(wos: list, warping_item: str) -> None:
	"""Force the Warping WO to qty=1 and drop the auto Beam Roll WO."""
	warping_wo = wo.find_combined_wo(wos, warping_item) or wo.find_combined_wo(wos, "Beam Roll")
	if warping_wo:
		frappe.db.set_value("Work Order", warping_wo, "qty", 1, update_modified=False)

	beam_roll_wo = wo.find_combined_wo(wos, "Beam Roll")
	if beam_roll_wo and beam_roll_wo != warping_wo:
		wo.delete_if_draft("Work Order", beam_roll_wo)


# ── total_qty resolution ──────────────────────────────────────────────────────


def _resolve_total_qty(production_plan: str, packing_item: str, wos: list, stage_configs: dict, pieces_per_roll: int) -> int:
	"""
	Real Sales Order qty for this plan's packing item, so total_qty
	always matches what was actually ordered (not an MRP roll estimate).
	Falls back to the old roll-estimate formula only if no match is found.
	"""
	plan = frappe.get_doc("Production Plan", production_plan)
	for item in plan.get("po_items", []):
		if item.get("sales_order") and item.item_code == packing_item:
			qty = cint(item.get("planned_qty"))
			if qty:
				return qty

	grey_item = wo.find_item_by_keywords(stage_configs, ("grey", "weav", "loom"))
	grey_wo   = wo.find_combined_wo(wos, grey_item) if grey_item else ""
	roll_estimate = cint(frappe.db.get_value("Work Order", grey_wo, "qty")) if grey_wo else 0
	return (roll_estimate * pieces_per_roll) or pieces_per_roll


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_design_master(production_plan: str) -> str:
	wos = frappe.get_all(
		"Work Order",
		filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
		fields=["custom_design_master"],
	)
	for wo_row in wos:
		if wo_row.custom_design_master:
			return wo_row.custom_design_master
	return ""


def _load_design_wos(production_plan: str, design_master: str) -> list:
	"""This plan's Work Orders belonging to one design. Each WO's own
	custom_design_master is set independently from its own BOM (events/
	work_order.py), so this filter is correct even before this design's
	DESAR PO exists — and a no-op filter for a single-design plan."""
	return [w for w in wo.load_plan_wos(production_plan) if w.custom_design_master == design_master]


def _get_sales_order(production_plan: str) -> str:
	plan = frappe.get_doc("Production Plan", production_plan)
	for item in plan.get("po_items", []):
		if item.get("sales_order"):
			return item.sales_order
	return ""


def _stamp_design_master(design_master: str, dm, wo_names: list) -> None:
	"""Set design context on this design's own WOs only — never another
	design's WOs sharing the same Production Plan."""
	for wo_name in wo_names:
		frappe.db.set_value("Work Order", wo_name, {
			"custom_design_master": design_master,
			"custom_design_no":     dm.design_no,
			"custom_article_name":  dm.article_name,
		}, update_modified=False)
