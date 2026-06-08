"""
DESAR Manufacturing — Work Order Repository

All database operations for Work Order in one place.
"""
import frappe
from typing import Optional


class WorkOrderRepository:

    DOCTYPE = "Work Order"

    @classmethod
    def get_design_context(cls, work_order_name: str) -> dict:
        """
        Get DESAR custom fields from a Work Order.
        Returns empty dict if WO not found.
        """
        if not work_order_name:
            return {}
        try:
            wo = frappe.get_doc(cls.DOCTYPE, work_order_name)
            return {
                "design_no": wo.get("custom_design_no") or "",
                "article_name": wo.get("custom_article_name") or "",
                "sales_order": wo.sales_order or "",
                "production_item": wo.production_item or "",
                "qty": wo.qty or 0,
            }
        except frappe.DoesNotExistError:
            return {}

    @classmethod
    def get_manufacture_se(cls, work_order_name: str) -> Optional[str]:
        """Get the most recent submitted Manufacture SE for a Work Order."""
        return frappe.db.get_value(
            "Stock Entry",
            filters={
                "work_order": work_order_name,
                "stock_entry_type": "Manufacture",
                "docstatus": 1,
            },
            fieldname="name",
            order_by="creation desc",
        )

    @classmethod
    def has_manufacture_se(cls, work_order_name: str) -> bool:
        """Check if a submitted Manufacture SE exists for the Work Order."""
        return bool(cls.get_manufacture_se(work_order_name))

    @classmethod
    def get_weaving_workstation(cls, work_order_name: str) -> Optional[str]:
        """Get the workstation used for the Weaving operation Job Card."""
        return frappe.db.get_value(
            "Job Card",
            filters={
                "work_order": work_order_name,
                "operation": "Weaving",
                "docstatus": 1,
            },
            fieldname="workstation",
        )
