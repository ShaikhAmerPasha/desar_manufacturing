"""
DESAR Warping Service v6

Handles Stage 1 (Warping) and Stage 2 (Beam Split).

Warping: 1 WO → 1 Warping Beam (shared across all rolls)
Beam Split: 1 Repack SE → N Beam Rolls → assigned to roll chain rows
"""
import frappe
from frappe import _
from frappe.utils import nowdate

from desar_manufacturing.services import batch_service, stock_entry_service


# ── Warping ───────────────────────────────────────────────────────────────────


def start_warping(production_order: str) -> dict:
	"""
	Submit Warping WO and create draft Transfer SE.

	Draft SE allows store worker to review raw material
	quantities before issuing to the warping machine.
	"""
	po = frappe.get_doc("DESAR Production Order", production_order)

	if po.warping_status != "Not Started":
		frappe.throw(_("Warping is already {0}.").format(po.warping_status))
	if not po.warping_wo:
		frappe.throw(_("No Warping Work Order linked. Create Work Orders from Production Plan first."))

	wo = frappe.get_doc("Work Order", po.warping_wo)

	# Force qty=1 (1 beam regardless of roll count)
	if wo.qty != 1:
		wo.qty = 1

	_configure_warping_wo(wo, po)
	if wo.docstatus == 0:
		wo.save(ignore_permissions=True)
		wo.submit()

	# Draft Transfer SE — store worker reviews before submitting
	se = stock_entry_service.make_transfer_se_draft(wo)

	po.db_set("warping_transfer_se", se.name, update_modified=False)
	po.db_set("warping_status", "In Progress", update_modified=True)
	frappe.db.commit()

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
	po = frappe.get_doc("DESAR Production Order", production_order)

	if po.warping_status != "In Progress":
		frappe.throw(_("Start Warping first."))
	if not po.warping_transfer_se:
		frappe.throw(_("No Transfer SE found."))
	if not _is_submitted("Stock Entry", po.warping_transfer_se):
		frappe.throw(_("Submit the Warping Transfer SE first (store worker must approve)."))
	if po.warping_manufacture_se:
		frappe.throw(_("Warping already completed."))

	wo = frappe.get_doc("Work Order", po.warping_wo)
	se_mfg = stock_entry_service.make_manufacture_se_auto(wo)
	se_mfg.reload()

	batch_no = batch_service.get_batch_from_stock_entry(se_mfg)

	po.db_set("warping_manufacture_se", se_mfg.name, update_modified=False)
	po.db_set("warping_batch",          batch_no,    update_modified=False)
	po.db_set("warping_status",         "Completed", update_modified=True)
	frappe.db.commit()

	return {"status": "completed", "batch_no": batch_no}


# ── Beam Split ────────────────────────────────────────────────────────────────


def split_beam(production_order: str, roll_count: int) -> dict:
	"""
	Split 1 Warping Beam into N Beam Rolls via Repack SE.

	Supervisor decides roll_count at this point.
	Each Beam Roll batch is assigned to one row in roll_chains.
	If roll_chains has fewer rows than roll_count, new rows are appended.
	"""
	po = frappe.get_doc("DESAR Production Order", production_order)

	if po.warping_status != "Completed":
		frappe.throw(_("Complete Warping before splitting beam."))
	if po.beam_split_status == "Completed":
		frappe.throw(_("Beam already split."))
	if roll_count < 1:
		frappe.throw(_("Roll count must be at least 1."))
	if not po.warping_batch:
		frappe.throw(_("No Warping Beam batch found."))

	settings   = frappe.get_cached_doc("DESAR Settings")
	warping_wh = settings.get("warping_wip_warehouse") or ""

	se_name, batches = _create_repack_se(
		beam_batch=po.warping_batch,
		beam_item="Warping Beam",
		roll_count=roll_count,
		warehouse=warping_wh,
		po_name=production_order,
	)

	if not batches:
		frappe.throw(_("Beam split SE created but no Beam Roll batches detected. Check SE {0}.").format(se_name))

	# Ensure roll_chains has enough rows
	existing_rolls = len(po.roll_chains)
	if existing_rolls < roll_count:
		for i in range(existing_rolls, roll_count):
			frappe.get_doc({
				"doctype":             "DESAR Roll Chain",
				"parent":              production_order,
				"parentfield":         "roll_chains",
				"parenttype":          "DESAR Production Order",
				"roll_no":             i + 1,
				"grey_roll_status":    "Not Started",
				"finished_roll_status": "Locked",
				"packing_status":      "Locked",
				"roll_status":         "Not Started",
			}).insert(ignore_permissions=True)
		po.reload()

	# Assign beam roll batches to roll chain rows
	for i, roll in enumerate(po.roll_chains):
		if i < len(batches):
			frappe.db.set_value(
				"DESAR Roll Chain", roll.name,
				"beam_roll_batch", batches[i],
				update_modified=False,
			)

	po.db_set("beam_split_se",     se_name,    update_modified=False)
	po.db_set("roll_count",        roll_count, update_modified=False)
	po.db_set("beam_split_status", "Completed", update_modified=True)
	frappe.db.commit()

	return {
		"repack_se":         se_name,
		"beam_roll_batches": batches,
		"roll_count":        roll_count,
	}


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


def _configure_warping_wo(wo, po) -> None:
	settings = frappe.get_cached_doc("DESAR Settings")

	if settings.get("warping_wip_warehouse"):
		wo.wip_warehouse = settings.warping_wip_warehouse
	if settings.get("scrap_warehouse"):
		wo.scrap_warehouse = settings.scrap_warehouse

	wo.sales_order         = ""
	wo.custom_design_master = po.design_master
	wo.custom_design_no    = po.design_no
	wo.custom_article_name = po.article_name


def _is_submitted(doctype: str, name: str) -> bool:
	return frappe.db.get_value(doctype, name, "docstatus") == 1
