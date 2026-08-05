"""
DESAR Supervisor — Production Status Page Backend
Shows all active production orders with stage completion status.
"""
import frappe
from frappe.utils import today

from desar_manufacturing.constants import SUPERVISOR_ROLES


@frappe.whitelist()
def get_production_status():
    """
    Returns active production orders grouped by Production Plan.
    Each group shows all 4 WOs with their status.
    """
    frappe.only_for(SUPERVISOR_ROLES)
    # Get active Work Orders from last 30 days
    wos = frappe.get_all(
        "Work Order",
        filters={
            "docstatus": 1,
            "status": ["in", ["Not Started", "In Process", "Completed"]],
            "production_plan": ["!=", ""],
        },
        fields=[
            "name", "production_item", "qty", "status",
            "production_plan", "sales_order",
            "custom_design_no", "custom_article_name", "custom_design_master",
            "planned_start_date",
        ],
        order_by="planned_start_date asc",
        limit=200,
    )

    # Group by Production Plan
    groups = {}
    for wo in wos:
        pp = wo.production_plan
        if pp not in groups:
            so = wo.sales_order or ""
            groups[pp] = {
                "production_plan": pp,
                "sales_order": so,
                "design_no": wo.custom_design_no or "",
                "article_name": wo.custom_article_name or "",
                "planned_date": str(wo.planned_start_date or ""),
                "work_orders": [],
                "total": 0,
                "completed": 0,
            }

        # Get stage name
        stage_name = ""
        if wo.custom_design_master and wo.production_item:
            stage_name = frappe.db.get_value(
                "DESAR Stage Configuration",
                {"parent": wo.custom_design_master, "output_item": wo.production_item},
                "stage_name"
            ) or wo.production_item

        groups[pp]["work_orders"].append({
            "name": wo.name,
            "production_item": wo.production_item,
            "stage_name": stage_name,
            "qty": wo.qty,
            "status": wo.status,
        })
        groups[pp]["total"] += 1
        if wo.status == "Completed":
            groups[pp]["completed"] += 1

    # Sort — in-progress first, then not started, then completed
    result = list(groups.values())
    def sort_key(g):
        if g["completed"] < g["total"] and g["completed"] > 0:
            return 0  # In progress
        elif g["completed"] == 0:
            return 1  # Not started
        else:
            return 2  # Completed
    result.sort(key=sort_key)

    return result
