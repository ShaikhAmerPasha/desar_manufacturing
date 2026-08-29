"""
Patch: backfill the new `current_stage` field on DESAR Production Order.

`current_stage` is computed by stage_status_service.refresh_stage_status(),
which is only called from warping_service/roll_service stage-transition
actions. Orders submitted before this release never had it set. Runs once
on migrate to populate it for every already-submitted order.

Idempotent — safe to run again.
"""
import frappe

from desar_manufacturing.services.stage_status_service import refresh_stage_status


def execute():
	if not frappe.db.exists("DocType", "DESAR Production Order"):
		return

	names = frappe.get_all(
		"DESAR Production Order",
		filters={"docstatus": 1},
		pluck="name",
	)
	for name in names:
		po = frappe.get_doc("DESAR Production Order", name)
		refresh_stage_status(po)

	if names:
		frappe.db.commit()
		frappe.logger().info(
			f"DESAR patch: backfilled current_stage on {len(names)} Production Order(s)"
		)
