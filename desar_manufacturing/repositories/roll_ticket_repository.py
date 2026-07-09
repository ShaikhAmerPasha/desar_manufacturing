"""
DESAR Manufacturing — Roll Ticket Repository

All database operations for Roll Ticket.

v3.0: Removed update_grey_grades, update_finishing_grades, update_final_grades.
Grade updates now go through stage_grades child table via RollTicketService.
"""
import frappe
from frappe.utils import flt
from typing import Optional
from desar_manufacturing.constants import RollStatus


class RollTicketRepository:

    DOCTYPE = "Roll Ticket"

    @classmethod
    def exists_for_batch(cls, batch_no: str) -> bool:
        return bool(frappe.db.exists(cls.DOCTYPE, {"roll_batch": batch_no}))

    @classmethod
    def find_by_batch(cls, batch_no: str) -> Optional[str]:
        return frappe.db.get_value(cls.DOCTYPE, {"roll_batch": batch_no}, "name")

    @classmethod
    def find_active_by_design(cls, design_no: str, article_name: str) -> Optional[str]:
        return frappe.db.get_value(
            cls.DOCTYPE,
            {
                "design_no":    design_no,
                "article_name": article_name,
                "roll_status":  ["!=", RollStatus.COMPLETED],
            },
            "name",
            order_by="creation desc",
        )

    @classmethod
    def create(cls, data: dict) -> str:
        doc = frappe.get_doc({"doctype": cls.DOCTYPE, **data})
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def get_wip_count(cls) -> int:
        return frappe.db.count(cls.DOCTYPE, {"roll_status": ["in", RollStatus.WIP]})

    @classmethod
    def get_completed_count(cls) -> int:
        return frappe.db.count(cls.DOCTYPE, {"roll_status": RollStatus.COMPLETED})
