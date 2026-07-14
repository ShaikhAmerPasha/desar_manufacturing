"""
Shared Work Order lookup/split helpers.

Used by production_plan_service (resolves the Warping WO at PO-creation
time) and warping_service (resolves and splits Grey/Finished/Packing WOs
at Beam Split time, once the real per-roll quantities are known).
"""
import frappe
from frappe import _


def load_plan_wos(production_plan: str) -> list:
	return frappe.get_all(
		"Work Order",
		filters={"production_plan": production_plan, "docstatus": ["!=", 2]},
		fields=["name", "production_item", "qty", "custom_design_master"],
		order_by="qty desc, name asc",
	)


def find_item_by_keywords(stage_configs: dict, keywords: tuple) -> str:
	for item, sc in stage_configs.items():
		if any(k in (sc.stage_name or "").lower() for k in keywords):
			return item
	return ""


def find_final_item(stage_configs: dict) -> str:
	for item, sc in stage_configs.items():
		if sc.is_final_stage:
			return item
	return ""


def find_combined_wo(wos: list, item: str) -> str:
	"""Find the highest-qty WO for an item (the not-yet-split one)."""
	matches = [w for w in wos if w.production_item == item]
	if not matches:
		return ""
	return max(matches, key=lambda x: x.qty).name


def split_wo_per_roll(
	wos: list, item: str, qtys: list,
	production_plan: str, design_master: str, dm,
) -> list:
	"""Split the combined WO for `item` into one WO per entry in `qtys`."""
	combined_wo = find_combined_wo(wos, item)
	if not combined_wo:
		frappe.throw(_("No Work Order found for {0}.").format(item))

	combined = frappe.get_doc("Work Order", combined_wo)
	new_wos = [_clone_combined_wo(combined, qty, production_plan, design_master, dm) for qty in qtys]
	delete_if_draft("Work Order", combined_wo)
	return new_wos


def _clone_combined_wo(combined, qty: int, production_plan: str, design_master: str, dm) -> str:
	clone = frappe.copy_doc(combined)
	clone.qty                  = qty
	clone.set_required_items()
	clone.production_plan      = production_plan
	clone.custom_design_master = design_master
	clone.custom_design_no     = dm.design_no
	clone.custom_article_name  = dm.article_name
	clone.sales_order          = ""  # sub-assembly WOs must not link SO (OverProductionError)
	clone.docstatus            = 0
	clone.insert(ignore_permissions=True)
	return clone.name


def delete_if_draft(doctype: str, name: str) -> None:
	if frappe.db.get_value(doctype, name, "docstatus") == 0:
		try:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"DESAR: could not delete draft {doctype} {name}",
				message=frappe.get_traceback(),
			)
