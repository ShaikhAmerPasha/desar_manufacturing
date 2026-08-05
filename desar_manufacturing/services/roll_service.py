"""
DESAR Roll Service v6

Handles all production stage transitions for individual rolls.

Each stage is 2-step to accommodate Job Card completion:
  Step 1: Submit WO + Transfer SE  (Job Cards created)
  Step 2: Manufacture SE + QI      (after Job Cards completed)

Grey Roll:     start_grey_roll → [complete job card] → complete_grey_roll
Finished Roll: start_finished_roll → [complete job card] → complete_finished_roll
Packing:       start_packing → [complete job card] → complete_packing → [submit SE] → finalize_packing
"""
import frappe
from frappe import _
from frappe.utils import nowdate

from desar_manufacturing.services import batch_service, qi_service, stock_entry_service
from desar_manufacturing.utils.validation_utils import resolve_by_keyword
from desar_manufacturing.utils.doc_utils import is_submitted


# ── Grey Roll ─────────────────────────────────────────────────────────────────


def start_grey_roll(production_order: str, roll_no: int) -> dict:
	"""
	Step 1: Submit Grey Roll WO + auto Transfer SE.
	Job Cards are created at WO submit. Operator completes them,
	then calls complete_grey_roll.
	"""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if roll.grey_roll_status != "Not Started":
		frappe.throw(_("Grey Roll for Roll {0} is already {1}.").format(roll_no, roll.grey_roll_status))
	if not roll.beam_roll_batch:
		frappe.throw(_("Beam Roll batch not assigned to Roll {0}. Complete Beam Split first.").format(roll_no))
	if not roll.grey_roll_wo:
		frappe.throw(_("No Grey Roll Work Order linked to Roll {0}.").format(roll_no))

	wo = frappe.get_doc("Work Order", roll.grey_roll_wo)
	_configure_wo(wo, po, "grey")
	if wo.docstatus == 0:
		wo.save(ignore_permissions=True)
		wo.submit()

	# Auto Transfer SE using beam roll batch
	se_transfer = stock_entry_service.make_transfer_se_auto(
		wo, prev_batch=roll.beam_roll_batch, prev_item="Beam Roll"
	)

	_update_roll(roll, {
		"grey_roll_status": "In Progress",
		"roll_status":      "In Progress",
	})
	_refresh_po_status(po)

	return {
		"status":      "in_progress",
		"transfer_se": se_transfer.name,
		"message":     _("Grey Roll WO submitted. Complete Job Cards then click Complete Grey Roll."),
	}


def complete_grey_roll(production_order: str, roll_no: int) -> dict:
	"""
	Step 2: Create Manufacture SE + QI after Job Cards are completed.
	"""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if roll.grey_roll_status != "In Progress":
		frappe.throw(_("Start Grey Roll first."))
	# If batch already exists (SE was created), just create QI
	if roll.grey_roll_batch:
		if roll.grey_roll_qi:
			frappe.throw(_("Grey Roll QI already created for Roll {0}.").format(roll_no))
		qi = _create_roll_qi(po, roll, "Grey Roll", roll.grey_roll_batch, roll.grey_roll_wo)
		roll_ticket = frappe.db.get_value("Roll Ticket", {"roll_batch": roll.grey_roll_batch}, "name") or ""
		_update_roll(roll, {"grey_roll_qi": qi, "roll_ticket": roll_ticket})
		_refresh_po_status(po)
		return {"status": "awaiting_inspection", "batch_no": roll.grey_roll_batch, "qi": qi}

	_validate_job_cards(roll.grey_roll_wo, "Grey Roll")

	wo      = frappe.get_doc("Work Order", roll.grey_roll_wo)
	se_mfg  = stock_entry_service.make_manufacture_se_auto(
		wo, prev_batch=roll.beam_roll_batch, prev_item="Beam Roll"
	)
	se_mfg.reload()

	batch_no    = batch_service.get_batch_from_stock_entry(se_mfg)
	roll_ticket = frappe.db.get_value("Roll Ticket", {"roll_batch": batch_no}, "name") or ""
	qi          = _create_roll_qi(po, roll, "Grey Roll", batch_no, roll.grey_roll_wo)

	_update_roll(roll, {
		"grey_roll_batch":  batch_no,
		"grey_roll_qi":     qi,
		"roll_ticket":      roll_ticket,
	})
	_refresh_po_status(po)

	return {"status": "awaiting_inspection", "batch_no": batch_no, "qi": qi}


# ── Finished Roll ─────────────────────────────────────────────────────────────


def start_finished_roll(production_order: str, roll_no: int) -> dict:
	"""Step 1: Submit Finished Roll WO + Transfer SE."""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if roll.finished_roll_status != "Not Started":
		frappe.throw(_("Finished Roll for Roll {0} is already {1}.").format(roll_no, roll.finished_roll_status))
	if not roll.grey_roll_batch:
		frappe.throw(_("Grey Roll not completed for Roll {0}.").format(roll_no))
	if not roll.finished_roll_wo:
		frappe.throw(_("No Finished Roll Work Order linked to Roll {0}.").format(roll_no))

	wo = frappe.get_doc("Work Order", roll.finished_roll_wo)
	_configure_wo(wo, po, "finish")
	if wo.docstatus == 0:
		wo.save(ignore_permissions=True)
		wo.submit()

	se_transfer = stock_entry_service.make_transfer_se_auto(
		wo, prev_batch=roll.grey_roll_batch, prev_item="Grey Roll"
	)

	_update_roll(roll, {"finished_roll_status": "In Progress"})
	_refresh_po_status(po)

	return {
		"status":      "in_progress",
		"transfer_se": se_transfer.name,
		"message":     _("Finished Roll WO submitted. Complete Job Cards then click Complete Finished Roll."),
	}


def complete_finished_roll(production_order: str, roll_no: int) -> dict:
	"""Step 2: Manufacture SE + QI after Job Cards completed."""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if roll.finished_roll_status != "In Progress":
		frappe.throw(_("Start Finished Roll first."))
	if roll.finished_roll_batch:
		frappe.throw(_("Finished Roll already completed for Roll {0}.").format(roll_no))

	_validate_job_cards(roll.finished_roll_wo, "Finished Roll")

	wo     = frappe.get_doc("Work Order", roll.finished_roll_wo)
	se_mfg = stock_entry_service.make_manufacture_se_auto(
		wo, prev_batch=roll.grey_roll_batch, prev_item="Grey Roll"
	)
	se_mfg.reload()

	batch_no = batch_service.get_batch_from_stock_entry(se_mfg)
	qi       = _create_roll_qi(po, roll, "Finished Roll", batch_no, roll.finished_roll_wo)

	_update_roll(roll, {
		"finished_roll_batch":  batch_no,
		"finished_roll_qi":     qi,
		"packing_status":       "Not Started",
	})
	_refresh_po_status(po)

	return {"status": "awaiting_inspection", "batch_no": batch_no, "qi": qi}


# ── Packing ───────────────────────────────────────────────────────────────────


def start_packing(production_order: str, roll_no: int) -> dict:
	"""Step 1: Submit Packing WO + Transfer SE + draft Manufacture SE."""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if roll.packing_status != "Not Started":
		frappe.throw(_("Packing for Roll {0} is already {1}.").format(roll_no, roll.packing_status))
	if not roll.finished_roll_batch:
		frappe.throw(_("Finished Roll not completed for Roll {0}.").format(roll_no))
	if not roll.packing_wo:
		frappe.throw(_("No Packing Work Order linked to Roll {0}.").format(roll_no))

	wo = frappe.get_doc("Work Order", roll.packing_wo)
	_configure_wo(wo, po, "pack", is_final=True)
	if wo.docstatus == 0:
		wo.save(ignore_permissions=True)
		wo.submit()

	se_transfer = stock_entry_service.make_transfer_se_auto(
		wo, prev_batch=roll.finished_roll_batch, prev_item="Finished Roll"
	)

	_update_roll(roll, {"packing_status": "In Progress"})
	_refresh_po_status(po)

	return {
		"status":      "in_progress",
		"transfer_se": se_transfer.name,
		"message":     _("Packing WO submitted. Complete Job Cards then click Complete Packing."),
	}


def complete_packing(production_order: str, roll_no: int) -> dict:
	"""Step 2: Create draft Manufacture SE after Job Cards completed."""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if roll.packing_status != "In Progress":
		frappe.throw(_("Start Packing first."))
	if roll.packing_manufacture_se:
		frappe.throw(_("Manufacture SE already created for Packing Roll {0}.").format(roll_no))

	_validate_job_cards(roll.packing_wo, "Packing")

	wo     = frappe.get_doc("Work Order", roll.packing_wo)
	se_mfg = stock_entry_service.make_manufacture_se_draft(
		wo, prev_batch=roll.finished_roll_batch, prev_item="Finished Roll"
	)

	_update_roll(roll, {"packing_manufacture_se": se_mfg.name})
	_refresh_po_status(po)

	return {
		"status":         "awaiting_manufacture",
		"manufacture_se": se_mfg.name,
		"message":        _("Manufacture SE created as draft. Packing supervisor must review and submit."),
	}


def finalize_packing(production_order: str, roll_no: int) -> dict:
	"""Step 3: Create QI after Manufacture SE is submitted."""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if not roll.packing_manufacture_se:
		frappe.throw(_("No Manufacture SE found for Packing Roll {0}.").format(roll_no))
	if not is_submitted("Stock Entry", roll.packing_manufacture_se):
		frappe.throw(_("Submit the Packing Manufacture SE first."))
	if roll.packing_qi:
		frappe.throw(_("QI already created for Packing Roll {0}.").format(roll_no))

	se       = frappe.get_doc("Stock Entry", roll.packing_manufacture_se)
	batch_no = batch_service.get_batch_from_stock_entry(se)
	qi       = _create_roll_qi(po, roll, "Packing", batch_no, roll.packing_wo)

	_update_roll(roll, {"packing_qi": qi})
	_refresh_po_status(po)

	return {"status": "awaiting_inspection", "qi": qi}


def complete_roll(production_order: str, roll_no: int) -> dict:
	"""Mark roll as fully completed after packing QI is submitted."""
	po   = frappe.get_doc("DESAR Production Order", production_order, for_update=True)
	_guard_po_submitted(po)
	roll = _get_roll(po, roll_no)

	if not roll.packing_qi:
		frappe.throw(_("No Packing QI found for Roll {0}.").format(roll_no))
	if not is_submitted("Quality Inspection", roll.packing_qi):
		frappe.throw(_("Submit the Packing QI first."))

	_update_roll(roll, {
		"packing_status": "Completed",
		"roll_status":    "Completed",
	})
	_refresh_po_status(po)
	return {"status": "completed"}


# ── Cancel reconciliation ───────────────────────────────────────────────────────


def revert_qi_reference(qi_name: str) -> None:
	"""
	On Quality Inspection cancel: clear whichever DESAR Roll Chain field
	referenced this QI and roll that stage back to "In Progress" so it can
	be redone. Refuses (frappe.throw) if the next stage already started —
	reversing then would leave that stage pointing at data that no longer
	has a valid inspection behind it.
	"""
	rows = frappe.get_all(
		"DESAR Roll Chain",
		or_filters={
			"grey_roll_qi":     qi_name,
			"finished_roll_qi": qi_name,
			"packing_qi":       qi_name,
		},
		fields=[
			"name", "parent", "grey_roll_qi", "finished_roll_qi", "packing_qi",
			"finished_roll_status", "packing_status", "roll_status",
		],
	)
	for row in rows:
		po = frappe.get_doc("DESAR Production Order", row.parent, for_update=True)
		if row.grey_roll_qi == qi_name:
			_guard_next_stage_not_started(row.finished_roll_status, "Grey Roll")
			_update_roll(row, {"grey_roll_qi": "", "grey_roll_status": "In Progress"})
		elif row.finished_roll_qi == qi_name:
			_guard_next_stage_not_started(row.packing_status, "Finished Roll")
			_update_roll(row, {"finished_roll_qi": "", "finished_roll_status": "In Progress"})
		elif row.packing_qi == qi_name:
			updates = {"packing_qi": "", "packing_status": "In Progress"}
			if row.roll_status == "Completed":
				updates["roll_status"] = "In Progress"
			_update_roll(row, updates)
		_refresh_po_status(po)


def revert_stock_entry_reference(se_name: str) -> None:
	"""
	On Manufacture Stock Entry cancel: clear any DESAR Roll Chain field that
	pointed at this SE (directly for Packing, or via the batch it produced
	for Grey/Finished Roll) so the stage can be redone instead of silently
	referencing cancelled stock.
	"""
	batch_no = batch_service.get_batch_from_stock_entry(frappe.get_doc("Stock Entry", se_name))
	or_filters = {"packing_manufacture_se": se_name}
	if batch_no:
		or_filters["grey_roll_batch"] = batch_no
		or_filters["finished_roll_batch"] = batch_no

	rows = frappe.get_all(
		"DESAR Roll Chain",
		or_filters=or_filters,
		fields=[
			"name", "parent", "grey_roll_batch", "finished_roll_batch",
			"packing_manufacture_se", "finished_roll_status", "packing_status",
		],
	)
	for row in rows:
		po = frappe.get_doc("DESAR Production Order", row.parent, for_update=True)
		if row.packing_manufacture_se == se_name:
			_update_roll(row, {
				"packing_manufacture_se": "", "packing_qi": "", "packing_status": "In Progress",
			})
		elif batch_no and row.grey_roll_batch == batch_no:
			_guard_next_stage_not_started(row.finished_roll_status, "Grey Roll")
			_update_roll(row, {
				"grey_roll_batch": "", "grey_roll_qi": "", "grey_roll_status": "In Progress",
			})
		elif batch_no and row.finished_roll_batch == batch_no:
			_guard_next_stage_not_started(row.packing_status, "Finished Roll")
			_update_roll(row, {
				"finished_roll_batch": "", "finished_roll_qi": "", "finished_roll_status": "In Progress",
			})
		_refresh_po_status(po)


def revert_work_order_reference(wo_name: str) -> None:
	"""
	On Work Order cancel: reset whichever DESAR Roll Chain stage this WO
	belonged to back to "Not Started" and clear the WO link, so the
	operator must link a fresh Work Order before restarting that stage
	instead of the flow silently trying to reuse a cancelled one.
	"""
	rows = frappe.get_all(
		"DESAR Roll Chain",
		or_filters={
			"grey_roll_wo":     wo_name,
			"finished_roll_wo": wo_name,
			"packing_wo":       wo_name,
		},
		fields=[
			"name", "parent", "grey_roll_wo", "finished_roll_wo", "packing_wo",
			"finished_roll_status", "packing_status",
		],
	)
	for row in rows:
		po = frappe.get_doc("DESAR Production Order", row.parent, for_update=True)
		if row.grey_roll_wo == wo_name:
			_guard_next_stage_not_started(row.finished_roll_status, "Grey Roll")
			_update_roll(row, {"grey_roll_wo": "", "grey_roll_status": "Not Started"})
		elif row.finished_roll_wo == wo_name:
			_guard_next_stage_not_started(row.packing_status, "Finished Roll")
			_update_roll(row, {"finished_roll_wo": "", "finished_roll_status": "Not Started"})
		elif row.packing_wo == wo_name:
			_update_roll(row, {"packing_wo": "", "packing_status": "Not Started"})
		_refresh_po_status(po)


def _guard_po_submitted(po) -> None:
	if po.docstatus != 1:
		frappe.throw(_("Production Order {0} is not submitted.").format(po.name))


def _guard_next_stage_not_started(next_stage_status: str, stage_label: str) -> None:
	if next_stage_status and next_stage_status != "Not Started":
		frappe.throw(
			_("Cannot cancel {0} — its next stage has already started. Reverse the next stage first.").format(stage_label)
		)


# ── Refresh ───────────────────────────────────────────────────────────────────


def refresh_roll(production_order: str, roll_no: int) -> dict:
	"""Auto-detect externally submitted QIs and advance roll status."""
	po   = frappe.get_doc("DESAR Production Order", production_order)
	roll = _get_roll(po, roll_no)
	changed = False

	# Grey Roll QI submitted → unlock Finished Roll
	if (roll.grey_roll_status == "In Progress"
			and roll.grey_roll_qi
			and is_submitted("Quality Inspection", roll.grey_roll_qi)):
		_update_roll(roll, {
			"grey_roll_status":     "Completed",
			"finished_roll_status": "Not Started",
		})
		po.reload()
		roll = _get_roll(po, roll_no)
		changed = True

	# Finished Roll QI submitted → unlock Packing
	if (roll.finished_roll_status == "In Progress"
			and roll.finished_roll_qi
			and is_submitted("Quality Inspection", roll.finished_roll_qi)):
		_update_roll(roll, {
			"finished_roll_status": "Completed",
			"packing_status":       "Not Started",
		})
		po.reload()
		roll = _get_roll(po, roll_no)
		changed = True

	# Packing Manufacture SE submitted → auto-create QI
	if (roll.packing_status == "In Progress"
			and roll.packing_manufacture_se
			and not roll.packing_qi
			and is_submitted("Stock Entry", roll.packing_manufacture_se)):
		se       = frappe.get_doc("Stock Entry", roll.packing_manufacture_se)
		batch_no = batch_service.get_batch_from_stock_entry(se)
		qi       = _create_roll_qi(po, roll, "Packing", batch_no, roll.packing_wo)
		_update_roll(roll, {"packing_qi": qi})
		po.reload()
		roll = _get_roll(po, roll_no)
		changed = True

	# Packing QI submitted → complete roll
	if (roll.packing_status == "In Progress"
			and roll.packing_qi
			and is_submitted("Quality Inspection", roll.packing_qi)):
		_update_roll(roll, {
			"packing_status": "Completed",
			"roll_status":    "Completed",
		})
		changed = True

	if changed:
		_refresh_po_status(po)

	po.reload()
	return _roll_dict(_get_roll(po, roll_no))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_roll(po, roll_no: int):
	for r in po.roll_chains:
		if r.roll_no == roll_no or r.idx == roll_no:
			return r
	frappe.throw(_("Roll {0} not found in Production Order.").format(roll_no))


def _update_roll(roll, updates: dict) -> None:
	for field, value in updates.items():
		frappe.db.set_value(
			"DESAR Roll Chain", roll.name, field, value, update_modified=False
		)


def _refresh_po_status(po) -> None:
	po.reload()
	rolls = po.roll_chains
	if not rolls:
		return
	all_done     = all(r.roll_status == "Completed" for r in rolls)
	any_progress = any(r.roll_status in ("In Progress", "Completed") for r in rolls)

	if all_done and po.warping_status == "Completed" and po.beam_split_status == "Completed":
		new_status = "Completed"
	elif any_progress or po.warping_status in ("In Progress", "Completed"):
		new_status = "In Progress"
	else:
		new_status = "Submitted"

	if po.status != new_status:
		po.db_set("status", new_status, update_modified=True)


def _configure_wo(wo, po, stage_keyword: str, is_final: bool = False) -> None:
	"""Configure Work Order warehouses for each production stage.

	ERPNext warehouse semantics:
	  Transfer SE:    source_warehouse → wip_warehouse
	  Manufacture SE: wip_warehouse    → fg_warehouse

	Each stage's primary input comes from the PREVIOUS stage's fg_warehouse.
	We override required_items[].source_warehouse so the Transfer SE sources
	material from where the previous stage actually deposited it, not from the
	BOM default which may point to the wrong warehouse.
	"""
	settings = frappe.get_cached_doc("DESAR Settings")

	# wip_warehouse: where Transfer SE deposits material (and Manufacture SE consumes from)
	wip_wh = resolve_by_keyword(stage_keyword, {
		"grey":   settings.get("loom_floor_warehouse"),
		"weav":   settings.get("loom_floor_warehouse"),
		"finish": settings.get("finishing_wip_warehouse"),
		"dye":    settings.get("finishing_wip_warehouse"),
		"pack":   settings.get("cutting_packing_warehouse"),
		"cut":    settings.get("cutting_packing_warehouse"),
	})
	if wip_wh:
		wo.wip_warehouse = wip_wh

	# fg_warehouse: where Manufacture SE outputs finished goods
	if is_final:
		if settings.get("fg_grade_a_warehouse"):
			wo.fg_warehouse = settings.fg_grade_a_warehouse
	else:
		fg_wh = resolve_by_keyword(stage_keyword, {
			"grey":   settings.get("loom_floor_warehouse"),
			"weav":   settings.get("loom_floor_warehouse"),
			"finish": settings.get("finished_roll_warehouse"),
			"dye":    settings.get("finished_roll_warehouse"),
			"pack":   settings.get("cutting_packing_warehouse"),
			"cut":    settings.get("cutting_packing_warehouse"),
		})
		if fg_wh:
			wo.fg_warehouse = fg_wh

	# Override source_warehouse on required_items for the primary input item
	# so that Transfer SE sources from the previous stage's output warehouse.
	# Without this override, the BOM default source_warehouse is used, which
	# may differ from where the batch was actually manufactured to.
	src_wh = resolve_by_keyword(stage_keyword, {
		"grey":   settings.get("warping_wip_warehouse") or settings.get("loom_floor_warehouse"),
		"weav":   settings.get("warping_wip_warehouse") or settings.get("loom_floor_warehouse"),
		"finish": settings.get("loom_floor_warehouse"),
		"dye":    settings.get("loom_floor_warehouse"),
		"pack":   settings.get("finished_roll_warehouse"),
		"cut":    settings.get("finished_roll_warehouse"),
	})
	input_item = resolve_by_keyword(stage_keyword, {
		"grey":   "Beam Roll",
		"weav":   "Beam Roll",
		"finish": "Grey Roll",
		"dye":    "Grey Roll",
		"pack":   "Finished Roll",
		"cut":    "Finished Roll",
	})
	if input_item:
		for ri in wo.get("required_items") or []:
			if ri.item_code != input_item:
				continue
			if src_wh:
				ri.source_warehouse = src_wh
			ri.required_qty = 1
		# ERPNext's WorkOrder.validate() recomputes required_items via
		# set_required_items() AFTER this function returns, which would
		# overwrite the qty=1 above with a BOM ratio again. Stash which
		# item needs forcing so events/work_order.py's validate hook
		# (which runs after that recompute — see its own comment) can
		# re-apply it. A stage always consumes exactly ONE upstream roll
		# regardless of how many pieces that roll holds; the BOM's
		# proportional ratio (output_qty / nominal_pieces_per_roll) doesn't
		# fit that "1 roll in, N pieces out" relationship and produces a
		# wrong (and sometimes fractional) required_qty whenever a
		# beam-split roll's actual piece count differs from the BOM's
		# nominal pieces-per-roll.
		wo.flags.desar_force_qty_1_item = input_item

	if settings.get("scrap_warehouse"):
		wo.scrap_warehouse = settings.scrap_warehouse
	if not is_final:
		wo.sales_order = ""

	wo.custom_design_master = po.design_master
	wo.custom_design_no     = po.design_no
	wo.custom_article_name  = po.article_name


def _validate_job_cards(work_order: str, stage_name: str) -> None:
	if not work_order:
		return
	open_jc = frappe.db.count("Job Card", filters={
		"work_order": work_order,
		"docstatus":  ["!=", 2],
		"status":     ["not in", ["Completed"]],
	})
	if open_jc:
		frappe.throw(
			_("Complete all Job Cards for {0} first. {1} open.").format(stage_name, open_jc)
		)


def _create_roll_qi(po, roll, stage_name: str, batch_no: str, work_order: str) -> str:
	qi = qi_service.make_roll_qi(po, roll, stage_name, batch_no, work_order)
	return qi.name


def _roll_dict(roll) -> dict:
	return {
		"roll_no":               roll.roll_no,
		"roll_status":           roll.roll_status,
		"beam_roll_batch":       roll.beam_roll_batch or "",
		"grey_roll_status":      roll.grey_roll_status,
		"grey_roll_batch":       roll.grey_roll_batch or "",
		"grey_roll_qi":          roll.grey_roll_qi or "",
		"finished_roll_status":  roll.finished_roll_status,
		"finished_roll_batch":   roll.finished_roll_batch or "",
		"finished_roll_qi":      roll.finished_roll_qi or "",
		"packing_status":        roll.packing_status,
		"packing_manufacture_se": roll.packing_manufacture_se or "",
		"packing_qi":            roll.packing_qi or "",
		"roll_ticket":           roll.roll_ticket or "",
	}
