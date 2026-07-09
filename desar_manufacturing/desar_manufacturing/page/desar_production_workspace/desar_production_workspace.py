"""
DESAR Production Workspace — Backend API
Provides data for the single-page production workspace.
"""
import frappe
from frappe import _
from frappe.utils import today, add_days


@frappe.whitelist()
def get_production_orders():
    """
    Returns active production orders grouped by Sales Order.
    Each group has all WOs with their current status.
    Includes today's and overdue orders.
    """
    # Get active Work Orders
    wos = frappe.get_all(
        "Work Order",
        filters={
            "docstatus": 1,
            "status": ["in", ["Not Started", "In Process"]],
        },
        fields=[
            "name", "production_item", "qty", "status",
            "planned_start_date", "custom_design_no",
            "custom_article_name", "custom_design_master",
            "bom_no", "sales_order",
        ],
        order_by="planned_start_date asc",
    )

    # Group by Sales Order
    groups = {}
    for wo in wos:
        so = wo.sales_order or "No Sales Order"
        if so not in groups:
            groups[so] = {
                "sales_order": so,
                "design_no": wo.custom_design_no or "",
                "article_name": wo.custom_article_name or "",
                "work_orders": [],
                "overall_status": "Not Started",
            }
        groups[so]["work_orders"].append(_enrich_wo(wo))

    # Compute overall status
    for so, group in groups.items():
        statuses = [w["status"] for w in group["work_orders"]]
        if all(s == "Completed" for s in statuses):
            group["overall_status"] = "Completed"
        elif any(s == "In Process" for s in statuses):
            group["overall_status"] = "In Process"
        else:
            group["overall_status"] = "Not Started"

    return list(groups.values())


def _enrich_wo(wo: dict) -> dict:
    """Add stage info, pending QIs, and actions to a WO dict."""
    wo = dict(wo)

    # Get stage name from Stage Configuration
    if wo.get("custom_design_master") and wo.get("production_item"):
        stage = frappe.db.get_value(
            "DESAR Stage Configuration",
            filters={
                "parent": wo["custom_design_master"],
                "output_item": wo["production_item"],
            },
            fieldname=["stage_name", "qi_required", "is_final_stage", "skip_transfer"],
            as_dict=True,
        )
        wo["stage_name"] = stage.stage_name if stage else ""
        wo["qi_required"] = stage.qi_required if stage else 0
        wo["is_final_stage"] = stage.is_final_stage if stage else 0
        wo["skip_transfer"] = stage.skip_transfer if stage else 0
    else:
        wo["stage_name"] = ""
        wo["qi_required"] = 0
        wo["is_final_stage"] = 0
        wo["skip_transfer"] = 0

    # Check if QI already exists
    wo["qi_exists"] = bool(frappe.db.get_value(
        "Quality Inspection",
        filters={"reference_type": "Stock Entry", "docstatus": ["!=", 2]},
        fieldname="name",
    )) if wo["qi_required"] else False

    # Check if Manufacture SE exists (WO finished)
    wo["manufacture_se"] = frappe.db.get_value(
        "Stock Entry",
        filters={
            "work_order": wo["name"],
            "stock_entry_type": "Manufacture",
            "docstatus": 1,
        },
        fieldname="name",
    ) or ""

    return wo


@frappe.whitelist()
def complete_stage(work_order):
    """
    Complete all job cards for a Work Order and finish it.
    Used from the Production Workspace.
    """
    wo = frappe.get_doc("Work Order", work_order)

    # Complete all open job cards
    job_cards = frappe.get_all(
        "Job Card",
        filters={"work_order": work_order, "docstatus": 0},
        fields=["name", "status"],
    )
    for jc in job_cards:
        if jc.status != "Completed":
            jc_doc = frappe.get_doc("Job Card", jc.name)
            jc_doc.status = "Completed"
            if not jc_doc.actual_start_time:
                jc_doc.actual_start_time = frappe.utils.now()
            if not jc_doc.actual_end_time:
                jc_doc.actual_end_time = frappe.utils.now()
            jc_doc.save(ignore_permissions=True)
            jc_doc.submit()

    return {"status": "ok", "work_order": work_order}


@frappe.whitelist()
def get_pending_inspections():
    """
    Returns pending QI opportunities — WOs completed but no QI yet.
    Used by QC Inspector view.
    """
    # Find completed WOs with qi_required stages and no QI
    completed_wos = frappe.get_all(
        "Work Order",
        filters={"docstatus": 1, "status": "Completed"},
        fields=["name", "production_item", "custom_design_master", "custom_design_no", "custom_article_name"],
        order_by="modified desc",
        limit=50,
    )

    pending = []
    for wo in completed_wos:
        if not wo.custom_design_master:
            continue

        stage = frappe.db.get_value(
            "DESAR Stage Configuration",
            filters={"parent": wo.custom_design_master, "output_item": wo.production_item},
            fieldname=["stage_name", "qi_required"],
            as_dict=True,
        )
        if not stage or not stage.qi_required:
            continue

        # Check if QI already created for this WO's Manufacture SE
        se = frappe.db.get_value(
            "Stock Entry",
            filters={"work_order": wo.name, "stock_entry_type": "Manufacture", "docstatus": 1},
            fieldname="name",
        )
        if not se:
            continue

        qi_exists = frappe.db.exists(
            "Quality Inspection",
            {"reference_name": se, "docstatus": ["!=", 2]},
        )
        if not qi_exists:
            pending.append({
                "work_order": wo.name,
                "production_item": wo.production_item,
                "stage_name": stage.stage_name,
                "design_no": wo.custom_design_no or "",
                "article_name": wo.custom_article_name or "",
                "manufacture_se": se,
            })

    return pending
