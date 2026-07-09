"""
DESAR Production Plan Service v6

Creates ONE DESAR Production Order per Sales Order line.

Key responsibility:
  - Takes combined WOs from Production Plan (qty=N)
  - Splits per-roll WOs (Grey Roll, Finished Roll, Packing) into qty=1 each
  - Forces Warping WO qty=1
  - Groups everything into roll chains
  - Creates 1 DESAR PO
"""
import frappe
from frappe import _
from frappe.utils import cint


# ── Public ────────────────────────────────────────────────────────────────────


def create_desar_po_from_plan(production_plan: str) -> dict:
	"""
	Create one DESAR Production Order from a Production Plan.

	Steps:
	  1. Determine Design Master from WOs
	  2. Split combined per-roll WOs into qty=1 individual WOs
	  3. Force Warping WO qty=1
	  4. Build roll chains and create DESAR PO
	"""
	if frappe.db.exists(
		"DESAR Production Order",
		{"production_plan": production_plan, "docstatus": 1},
	):
		frappe.throw(_("DESAR Production Order already exists for this Production Plan."))

	design_master = _get_design_master(production_plan)
	if not design_master:
		frappe.throw(_(
			"Cannot determine Design Master. "
			"Set custom_design_master on at least one Work Order."
		))

	dm              = frappe.get_cached_doc("Design Master", design_master)
	stage_configs   = {sc.output_item: sc for sc in dm.stage_configuration}
	pieces_per_roll = cint(dm.pieces_per_roll) or 50

	wos = _load_plan_wos(production_plan)

	warping_item  = _find_item_by_keywords(stage_configs, ("warp",))
	grey_item     = _find_item_by_keywords(stage_configs, ("grey", "weav", "loom"))
	finished_item = _find_item_by_keywords(stage_configs, ("finish", "dye"))
	packing_item  = _find_final_item(stage_configs)

	# Determine roll count from grey roll WO qty
	grey_combined_wo = _find_combined_wo(wos, grey_item)
	roll_count = cint(
		frappe.db.get_value("Work Order", grey_combined_wo, "qty")
		if grey_combined_wo else 0
	)
	if roll_count < 1:
		frappe.throw(_("Cannot determine roll count. No Grey Roll Work Order found."))

	# Split combined WOs into per-roll WOs (qty=1 for sub-assembly, qty=pieces_per_roll for final packing)
	grey_wos     = _split_or_reuse(wos, grey_item,     roll_count, production_plan, design_master, dm, 1)
	finished_wos = _split_or_reuse(wos, finished_item, roll_count, production_plan, design_master, dm, 1)
	packing_wos  = _split_or_reuse(wos, packing_item,  roll_count, production_plan, design_master, dm, pieces_per_roll)

	# Warping WO — force qty=1
	warping_wo = _find_combined_wo(wos, warping_item) or _find_combined_wo(wos, "Beam Roll")
	if warping_wo:
		frappe.db.set_value("Work Order", warping_wo, "qty", 1, update_modified=False)

	# Beam Roll WO — delete (beam rolls are created via Repack SE, not WO)
	beam_roll_wo = _find_combined_wo(wos, "Beam Roll")
	if beam_roll_wo and beam_roll_wo != warping_wo:
		try:
			frappe.delete_doc("Work Order", beam_roll_wo, force=True, ignore_permissions=True)
		except Exception:
			pass

	# Determine SO
	sales_order = _get_sales_order(production_plan)
	total_qty   = roll_count * pieces_per_roll

	# Create DESAR PO
	po = frappe.get_doc({
		"doctype":          "DESAR Production Order",
		"production_plan":  production_plan,
		"sales_order":      sales_order,
		"design_master":    design_master,
		"article_name":     dm.article_name,
		"design_no":        dm.design_no,
		"total_qty":        total_qty,
		"pieces_per_roll":  pieces_per_roll,
		"warping_wo":       warping_wo or "",
		"warping_status":   "Not Started",
		"beam_split_status": "Not Started",
	})

	for i in range(roll_count):
		po.append("roll_chains", {
			"roll_no":              i + 1,
			"grey_roll_wo":         grey_wos[i]     if i < len(grey_wos)     else "",
			"finished_roll_wo":     finished_wos[i] if i < len(finished_wos) else "",
			"packing_wo":           packing_wos[i]  if i < len(packing_wos)  else "",
			"grey_roll_status":     "Not Started",
			"finished_roll_status": "Locked",
			"packing_status":       "Locked",
			"roll_status":          "Not Started",
		})

	po.insert(ignore_permissions=True)
	po.submit()

	# Stamp design master on all remaining WOs
	_stamp_design_master(production_plan, design_master, dm)

	frappe.db.commit()

	return {
		"production_order": po.name,
		"roll_count":       roll_count,
		"total_qty":        total_qty,
	}


def preview_plan(production_plan: str) -> dict:
	"""Return preview info for confirmation dialog."""
	design_master = _get_design_master(production_plan)
	if not design_master:
		return {"error": "Cannot determine Design Master"}

	dm              = frappe.get_cached_doc("Design Master", design_master)
	stage_configs   = {sc.output_item: sc for sc in dm.stage_configuration}
	pieces_per_roll = cint(dm.pieces_per_roll) or 50

	wos      = _load_plan_wos(production_plan)
	grey_item = _find_item_by_keywords(stage_configs, ("grey", "weav", "loom"))
	grey_wo  = _find_combined_wo(wos, grey_item)
	roll_count = cint(frappe.db.get_value("Work Order", grey_wo, "qty")) if grey_wo else 0

	already_exists = frappe.db.exists(
		"DESAR Production Order",
		{"production_plan": production_plan, "docstatus": 1},
	)

	return {
		"design_master":   design_master,
		"article_name":    dm.article_name,
		"design_no":       dm.design_no,
		"roll_count":      roll_count,
		"pieces_per_roll": pieces_per_roll,
		"total_qty":       roll_count * pieces_per_roll,
		"already_exists":  bool(already_exists),
	}


# ── WO Splitting ──────────────────────────────────────────────────────────────


def _split_or_reuse(wos: list, item: str, roll_count: int,
					production_plan: str, design_master: str, dm, target_qty: int = 1) -> list:
	"""
	Return a list of roll_count WO names for item.

	If a combined WO exists, split it into
	roll_count individual WOs (qty=target_qty each) by cloning.
	If individual WOs already exist, reuse them.
	"""
	# Individual WOs already exist (qty=target_qty)
	individual = sorted(
		[w for w in wos if w.production_item == item and w.qty == target_qty],
		key=lambda x: x.name,
	)
	if len(individual) >= roll_count:
		return [w.name for w in individual[:roll_count]]

	# Combined WO exists — split it
	combined_wo = _find_combined_wo(wos, item)
	if not combined_wo:
		frappe.throw(_("No Work Order found for {0}.").format(item))

	combined = frappe.get_doc("Work Order", combined_wo)
	new_wos  = []

	for i in range(roll_count):
		clone = frappe.copy_doc(combined)
		clone.qty              = target_qty
		clone.set_required_items()
		clone.production_plan  = production_plan
		clone.custom_design_master = design_master
		clone.custom_design_no    = dm.design_no
		clone.custom_article_name = dm.article_name
		clone.sales_order = ""  # sub-assembly WOs must not link SO (OverProductionError)
		clone.docstatus   = 0
		clone.insert(ignore_permissions=True)
		new_wos.append(clone.name)

	# Delete the combined WO (draft only)
	if frappe.db.get_value("Work Order", combined_wo, "docstatus") == 0:
		try:
			frappe.delete_doc("Work Order", combined_wo, force=True, ignore_permissions=True)
		except Exception:
			pass

	return new_wos


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_plan_wos(production_plan: str) -> list:
	return frappe.get_all(
		"Work Order",
		filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
		fields=["name", "production_item", "qty", "custom_design_master"],
		order_by="qty desc, name asc",
	)


def _get_design_master(production_plan: str) -> str:
	wos = frappe.get_all(
		"Work Order",
		filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
		fields=["custom_design_master"],
	)
	for wo in wos:
		if wo.custom_design_master:
			return wo.custom_design_master
	return ""


def _find_item_by_keywords(stage_configs: dict, keywords: tuple) -> str:
	for item, sc in stage_configs.items():
		if any(k in (sc.stage_name or "").lower() for k in keywords):
			return item
	return ""


def _find_final_item(stage_configs: dict) -> str:
	for item, sc in stage_configs.items():
		if sc.is_final_stage:
			return item
	return ""


def _find_combined_wo(wos: list, item: str) -> str:
	"""Find the highest-qty WO for an item (the combined one)."""
	matches = [w for w in wos if w.production_item == item]
	if not matches:
		return ""
	return max(matches, key=lambda x: x.qty).name


def _get_sales_order(production_plan: str) -> str:
	plan = frappe.get_doc("Production Plan", production_plan)
	for item in plan.get("po_items", []):
		if item.get("sales_order"):
			return item.sales_order
	return ""


def _stamp_design_master(production_plan: str, design_master: str, dm) -> None:
	"""Set design context on all WOs linked to this PP."""
	wos = frappe.get_all(
		"Work Order",
		filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
		pluck="name",
	)
	for wo_name in wos:
		frappe.db.set_value("Work Order", wo_name, {
			"custom_design_master": design_master,
			"custom_design_no":     dm.design_no,
			"custom_article_name":  dm.article_name,
		}, update_modified=False)