"""
DESAR Manufacturing — Production Plan controller override

create_work_order: skip re-creating a Work Order for an (item, bom_no) pair
that already has a non-cancelled one on this Production Plan.

Core ERPNext's own dedup guard (ordered_qty, checked in
make_work_order_for_subassembly_items) only updates when a Work Order is
SUBMITTED (Work Order.update_ordered_qty() runs from on_submit/on_cancel,
never from plain insert — confirmed by reading work_order.py directly). This
app's shop-floor workflow leaves every Work Order in Draft until each
stage's own "Start X" action submits it, so there's a real window where
ordered_qty is still 0 for everything and re-clicking "Create Work Order"
duplicates the whole set. This override closes that gap directly at the one
choke point both make_work_order_for_finished_goods and
make_work_order_for_subassembly_items call through.
"""
import frappe
from frappe import _
from erpnext.manufacturing.doctype.production_plan.production_plan import ProductionPlan


class CustomProductionPlan(ProductionPlan):
    def create_work_order(self, item):
        existing = frappe.db.exists("Work Order", {
            "production_plan": self.name,
            "production_item": item.get("production_item"),
            "bom_no": item.get("bom_no"),
            "docstatus": ["!=", 2],
        })
        if existing:
            frappe.msgprint(
                _("Work Order {0} already exists for {1} on this Production Plan — skipped.").format(
                    frappe.utils.get_link_to_form("Work Order", existing),
                    item.get("production_item"),
                ),
                alert=True, indicator="orange",
            )
            return None
        return super().create_work_order(item)
