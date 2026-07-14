"""
DESAR Warping Service v7

Handles Stage 1 (Warping) and Stage 2 (Beam Split).

Warping: 1 WO → 1 Warping Beam (shared across all rolls)
Beam Split: 1 Repack SE → N Beam Rolls, sized per the supervisor's
split rows (qty_to_split x pieces_per_split), not a uniform guess.
"""
import frappe
from frappe import _
from frappe.utils import cint, nowdate

from desar_manufacturing.services import batch_service, stock_entry_service, wo_split_helpers as wo


# ── Warping ───────────────────────────────────────────────────────────────────


def start_warping(production_order: str) -> dict:
	"""
	Submit Warping WO and create draft Transfer SE.

	Draft SE allows store worker to review raw material
	quantities before issuing to the warping machine.
	"""
	po = frappe.get_doc("DESAR Production Order", production_order, for_update=True)

	if po.warping_status != "Not Started":
		frappe.throw(_("Warping is already {0}.").format(po.warping_status))
	if not po.warping_wo:
		frappe.throw(_("No Warping Work Order linked. Create Work Orders from Production Plan first."))

	work_order = frappe.get_doc("Work Order", po.warping_wo)

	# Force qty=1 (1 beam regardless of roll count)
	if work_order.qty != 1:
		work_order.qty = 1

	_configure_warping_wo(work_order, po)
	if work_order.docstatus == 0:
		work_order.save(ignore_permissions=True)
		work_order.submit()

	# Draft Transfer SE — store worker reviews before submitting
	se = stock_entry_service.make_transfer_se_draft(work_order)

	po.db_set("warping_transfer_se", se.name, update_modified=False)
	po.db_set("warping_status", "In Progress", update_modified=True)

	return {
		"status":      "awaiting_transfer",
		"transfer_se": se.name,
		"message":     _("Transfer SE created. Store worker must review and submit before completing warping."),
	}


def complete_warping(production_order: str) -> dict:
	"""
	Complete Warping after Transfer SE is submitted.
	Creates Manufacture SE auto and captures beam batch.
	"""
	po = frappe.get_doc("DESAR Production Order", production_order, for_update=True)

	if po.warping_status != "In Progress":
		frappe.throw(_("Start Warping first."))
	if not po.warping_transfer_se:
		frappe.throw(_("No Transfer SE found."))
	if not _is_submitted("Stock Entry", po.warping_transfer_se):
		frappe.throw(_("Submit the Warping Transfer SE first (store worker must approve)."))
	if po.warping_manufacture_se:
		frappe.throw(_("Warping already completed."))

	work_order = frappe.get_doc("Work Order", po.warping_wo)
	se_mfg = stock_entry_service.make_manufacture_se_auto(work_order)
	se_mfg.reload()

	batch_no = batch_service.get_batch_from_stock_entry(se_mfg)

	po.db_set("warping_manufacture_se", se_mfg.name, update_modified=False)
	po.db_set("warping_batch",          batch_no,    update_modified=False)
	po.db_set("warping_status",         "Completed", update_modified=True)

	return {"status": "completed", "batch_no": batch_no}


# ── Beam Split ────────────────────────────────────────────────────────────────


def split_beam(production_order: str, rows: list) -> dict:
	"""
	Split 1 Warping Beam into rolls sized by the supervisor's split rows.

	Each row is {qty_to_split, pieces_per_split}: qty_to_split rolls,
	each carrying pieces_per_split pieces. Rows must add up to exactly
	po.total_qty. Roll count is derived from the rows, never guessed.
	"""
	po = frappe.get_doc("DESAR Production Order", production_order, for_update=True)

	if po.warping_status != "Completed":
		frappe.throw(_("Complete Warping before splitting beam."))
	if po.beam_split_status == "Completed":
		frappe.throw(_("Beam already split."))
	if not po.warping_batch:
		frappe.throw(_("No Warping Beam batch found."))

	flat_qtys  = _validate_split_rows(rows, po)
	roll_count = len(flat_qtys)

	settings   = frappe.get_cached_doc("DESAR Settings")
	warping_wh = settings.get("warping_wip_warehouse") or ""

	savepoint = "desar_split_beam"
	frappe.db.savepoint(savepoint)

	se_name, batches = _create_repack_se(
		beam_batch=po.warping_batch,
		beam_item="Warping Beam",
		roll_count=roll_count,
		warehouse=warping_wh,
		po_name=production_order,
	)

	try:
		if len(batches) != roll_count:
			frappe.throw(_(
				"Expected {0} Beam Roll batches but got {1}. Check SE {2}."
			).format(roll_count, len(batches), se_name))

		is_legacy = bool(po.roll_chains) and bool(po.roll_chains[0].grey_roll_wo)
		roll_plan = (
			_apply_legacy_split(po, flat_qtys, batches) if is_legacy
			else _apply_fresh_split(po, flat_qtys, batches)
		)

		po.db_set("beam_split_se",     se_name,     update_modified=False)
		po.db_set("roll_count",        roll_count,  update_modified=False)
		po.db_set("beam_split_status", "Completed", update_modified=True)
	except Exception:
		# Savepoint was set before the Repack SE was created, so rolling back
		# to it erases the SE (and its stock ledger entries) entirely rather
		# than leaving a submitted document with no roll_chains behind it.
		frappe.db.rollback(save_point=savepoint)
		raise

	return {
		"repack_se":         se_name,
		"beam_roll_batches": batches,
		"roll_count":        roll_count,
		"roll_plan":         roll_plan,
	}


def _validate_split_rows(rows: list, po) -> list:
	"""Flatten split rows into a per-roll pieces list, validated against total_qty."""
	if not rows:
		frappe.throw(_("Add at least one split row."))

	flat_qtys = []
	for row in rows:
		qty_to_split     = cint(row.get("qty_to_split"))
		pieces_per_split = cint(row.get("pieces_per_split"))
		if qty_to_split < 1 or pieces_per_split < 1:
			frappe.throw(_("Each row needs No. of Rolls and Pieces per Roll of at least 1."))
		flat_qtys.extend([pieces_per_split] * qty_to_split)

	_check_total_matches(sum(flat_qtys), po.total_qty)
	return flat_qtys


def _check_total_matches(total_pieces: int, target_qty: int) -> None:
	if total_pieces == target_qty:
		return
	if total_pieces < target_qty:
		frappe.throw(_(
			"Split rows total {0} pieces, {1} short of the order qty {2}."
		).format(total_pieces, target_qty - total_pieces, target_qty))
	frappe.throw(_(
		"Split rows total {0} pieces, {1} over the order qty {2}."
	).format(total_pieces, total_pieces - target_qty, target_qty))


def _apply_legacy_split(po, flat_qtys: list, batches: list) -> list:
	"""In-flight PO: rolls already provisioned at Production-Plan time — redistribute only."""
	if len(flat_qtys) != len(po.roll_chains):
		frappe.throw(_(
			"This split has {0} rolls but {1} roll slots were already provisioned at planning. "
			"Rows must match the existing roll count for in-flight orders."
		).format(len(flat_qtys), len(po.roll_chains)))

	roll_plan = []
	for roll, batch, qty in zip(po.roll_chains, batches, flat_qtys):
		frappe.db.set_value(
			"DESAR Roll Chain", roll.name,
			{"beam_roll_batch": batch, "planned_qty": qty},
			update_modified=False,
		)
		_resize_packing_wo(roll.packing_wo, qty)
		roll_plan.append({"roll_no": roll.roll_no, "planned_qty": qty, "beam_roll_batch": batch})
	return roll_plan


def _resize_packing_wo(packing_wo: str, qty: int) -> None:
	if not packing_wo:
		return
	# Lock the row before checking docstatus so a concurrent submit can't
	# land between the check and the save below.
	wo_doc = frappe.get_doc("Work Order", packing_wo, for_update=True)
	if wo_doc.docstatus != 0:
		frappe.throw(_("Packing WO {0} already started; cannot resize.").format(packing_wo))

	wo_doc.qty = qty
	wo_doc.set_required_items()
	wo_doc.save(ignore_permissions=True)


def _apply_fresh_split(po, flat_qtys: list, batches: list) -> list:
	"""New-style PO: rolls not yet created — build Grey/Finished/Packing WOs and roll_chains now."""
	dm            = frappe.get_cached_doc("Design Master", po.design_master)
	stage_configs = {sc.output_item: sc for sc in dm.stage_configuration}
	grey_item     = wo.find_item_by_keywords(stage_configs, ("grey", "weav", "loom"))
	finished_item = wo.find_item_by_keywords(stage_configs, ("finish", "dye"))
	packing_item  = wo.find_final_item(stage_configs)

	wos        = wo.load_plan_wos(po.production_plan)
	roll_count = len(flat_qtys)

	grey_wos     = wo.split_wo_per_roll(wos, grey_item,     [1] * roll_count, po.production_plan, po.design_master, dm)
	finished_wos = wo.split_wo_per_roll(wos, finished_item, [1] * roll_count, po.production_plan, po.design_master, dm)
	packing_wos  = wo.split_wo_per_roll(wos, packing_item,  flat_qtys,        po.production_plan, po.design_master, dm)

	roll_plan = []
	for i, (batch, qty) in enumerate(zip(batches, flat_qtys)):
		roll_no = i + 1
		_insert_roll_chain_row(po.name, roll_no, batch, qty, grey_wos[i], finished_wos[i], packing_wos[i])
		roll_plan.append({"roll_no": roll_no, "planned_qty": qty, "beam_roll_batch": batch})
	return roll_plan


def _insert_roll_chain_row(
	po_name: str, roll_no: int, batch: str, qty: int,
	grey_wo: str, finished_wo: str, packing_wo: str,
) -> None:
	frappe.get_doc({
		"doctype":              "DESAR Roll Chain",
		"parent":               po_name,
		"parentfield":          "roll_chains",
		"parenttype":           "DESAR Production Order",
		# Each row is inserted standalone (not via parent.append()+save()),
		# so Frappe never auto-assigns idx from list position — every row
		# was landing at idx=0, leaving display/fetch order undefined and
		# causing the wrong roll's card to render first (real user-facing
		# confusion: clicking the visually-first card silently operated on
		# a different roll_no than expected). idx must match roll_no so
		# rows always sort/display in roll order.
		"idx":                  roll_no,
		"roll_no":              roll_no,
		"beam_roll_batch":      batch,
		"planned_qty":          qty,
		"grey_roll_wo":         grey_wo,
		"finished_roll_wo":     finished_wo,
		"packing_wo":           packing_wo,
		"grey_roll_status":     "Not Started",
		"finished_roll_status": "Locked",
		"packing_status":       "Locked",
		"roll_status":          "Not Started",
	}).insert(ignore_permissions=True)


# ── Repack SE ─────────────────────────────────────────────────────────────────


def _create_repack_se(
	beam_batch: str,
	beam_item: str,
	roll_count: int,
	warehouse: str,
	po_name: str,
) -> tuple:
	"""1 Warping Beam → N Beam Rolls via Repack SE."""
	settings = frappe.get_cached_doc("DESAR Settings")
	company  = settings.default_company or frappe.defaults.get_defaults().get("company")

	se = frappe.get_doc({
		"doctype":          "Stock Entry",
		"stock_entry_type": "Repack",
		"company":          company,
		"posting_date":     nowdate(),
		"remarks":          f"Beam split for {po_name} — {roll_count} rolls",
	})

	se.append("items", {
		"item_code":               beam_item,
		"qty":                     1,
		"s_warehouse":             warehouse,
		"batch_no":                beam_batch,
		"use_serial_batch_fields": 1,
	})

	for _ in range(roll_count):
		se.append("items", {
			"item_code":        "Beam Roll",
			"qty":              1,
			"t_warehouse":      warehouse,
			"is_finished_item": 1,
		})

	se.save(ignore_permissions=True)
	se.submit()
	se.reload()

	batches = []
	for row in se.items:
		if row.t_warehouse and row.item_code == "Beam Roll":
			b = row.batch_no
			if not b and row.get("serial_and_batch_bundle"):
				b = frappe.db.get_value(
					"Serial and Batch Entry",
					{"parent": row.serial_and_batch_bundle},
					"batch_no",
				) or ""
			if b:
				batches.append(b)

	return se.name, batches


# ── Helpers ───────────────────────────────────────────────────────────────────


def _configure_warping_wo(work_order, po) -> None:
	settings = frappe.get_cached_doc("DESAR Settings")

	if settings.get("warping_wip_warehouse"):
		work_order.wip_warehouse = settings.warping_wip_warehouse
	if settings.get("scrap_warehouse"):
		work_order.scrap_warehouse = settings.scrap_warehouse

	work_order.sales_order          = ""
	work_order.custom_design_master = po.design_master
	work_order.custom_design_no     = po.design_no
	work_order.custom_article_name  = po.article_name


def _is_submitted(doctype: str, name: str) -> bool:
	return frappe.db.get_value(doctype, name, "docstatus") == 1
