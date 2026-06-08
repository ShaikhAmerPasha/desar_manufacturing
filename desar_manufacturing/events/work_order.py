"""
Work Order event handlers.
THIN layer — delegates to services.
"""
import frappe
from frappe import _


def before_submit(doc, method):
    """
    Auto-fill Design No and Article from BOM → Design Master chain.
    Only fills if not already set by user or client script.

    Wrapped in try/except — custom fields may not exist if migrate
    has not been run. Never blocks WO submission.
    """
    if doc.get("custom_design_no") and doc.get("custom_article_name"):
        return  # Already filled — nothing to do

    if not doc.bom_no:
        return

    try:
        # Check if custom fields exist on BOM table before querying
        # This prevents OperationalError if migrate has not been run
        if not frappe.db.has_column("BOM", "custom_design_no"):
            return

        bom_data = frappe.db.get_value(
            "BOM",
            doc.bom_no,
            ["custom_design_no", "custom_article_name", "custom_design_master"],
            as_dict=True,
        )
        if not bom_data:
            return

        if bom_data.custom_design_no and not doc.get("custom_design_no"):
            doc.custom_design_no = bom_data.custom_design_no

        if bom_data.custom_article_name and not doc.get("custom_article_name"):
            doc.custom_article_name = bom_data.custom_article_name

        if bom_data.custom_design_master and not doc.get("custom_design_master"):
            doc.custom_design_master = bom_data.custom_design_master

    except Exception:
        # Never block WO submission due to custom field auto-fill failure
        frappe.log_error(
            title="DESAR: Work Order before_submit — auto-fill failed",
            message=frappe.get_traceback(),
        )
