"""
DESAR Manufacturing — Roll Ticket Repository

All database operations for Roll Ticket in one place.
No business logic here — only data access.
"""
import frappe
from frappe.utils import flt
from typing import Optional
from desar_manufacturing.constants import RollStatus


class RollTicketRepository:
    """
    Data access layer for Roll Ticket doctype.
    All frappe.db calls for Roll Ticket go through here.
    """

    DOCTYPE = "Roll Ticket"

    @classmethod
    def exists_for_batch(cls, batch_no: str) -> bool:
        """Check if a Roll Ticket exists for the given batch."""
        return bool(frappe.db.exists(cls.DOCTYPE, {"roll_batch": batch_no}))

    @classmethod
    def find_by_batch(cls, batch_no: str) -> Optional[str]:
        """Find Roll Ticket name by batch number."""
        return frappe.db.get_value(
            cls.DOCTYPE,
            {"roll_batch": batch_no},
            "name",
        )

    @classmethod
    def find_active_by_design(cls, design_no: str, article_name: str) -> Optional[str]:
        """
        Find the most recent active (non-completed) Roll Ticket
        for a given design and article.
        Used as fallback when batch is not available on QI.
        """
        return frappe.db.get_value(
            cls.DOCTYPE,
            {
                "design_no": design_no,
                "article_name": article_name,
                "roll_status": ["!=", RollStatus.COMPLETED],
            },
            "name",
            order_by="creation desc",
        )

    @classmethod
    def create(cls, data: dict) -> str:
        """
        Create a new Roll Ticket.
        Returns the new document name.
        Raises DuplicateEntryError if roll_batch already exists.
        """
        doc = frappe.get_doc({"doctype": cls.DOCTYPE, **data})
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def update_grey_grades(cls, name: str, qty_a: float, qty_b: float, qty_c: float):
        """Update grey stage grade counts, total, and set status to In Finishing."""
        frappe.db.set_value(cls.DOCTYPE, name, {
            "grey_qty_a":  flt(qty_a),
            "grey_qty_b":  flt(qty_b),
            "grey_qty_c":  flt(qty_c),
            "grey_total":  flt(qty_a) + flt(qty_b) + flt(qty_c),
            "roll_status": RollStatus.IN_FINISHING,
        })

    @classmethod
    def update_finishing_grades(cls, name: str, qty_a: float, qty_b: float, qty_c: float):
        """Update finishing stage grade counts, total, and set status to In Packing."""
        frappe.db.set_value(cls.DOCTYPE, name, {
            "finished_qty_a": flt(qty_a),
            "finished_qty_b": flt(qty_b),
            "finished_qty_c": flt(qty_c),
            "finished_total": flt(qty_a) + flt(qty_b) + flt(qty_c),
            "roll_status":    RollStatus.IN_PACKING,
        })

    @classmethod
    def update_final_grades(cls, name: str, qty_a: float, qty_b: float, qty_c: float):
        """Update final (packing) grade counts, total, and set status to Completed."""
        frappe.db.set_value(cls.DOCTYPE, name, {
            "cutted_qty_a": flt(qty_a),
            "cutted_qty_b": flt(qty_b),
            "cutted_qty_c": flt(qty_c),
            "cutted_total": flt(qty_a) + flt(qty_b) + flt(qty_c),
            "roll_status":  RollStatus.COMPLETED,
        })

    @classmethod
    def get_wip_count(cls) -> int:
        """Count Roll Tickets currently in production (not completed)."""
        return frappe.db.count(
            cls.DOCTYPE,
            {"roll_status": ["in", RollStatus.WIP]},
        )

    @classmethod
    def get_completed_count(cls) -> int:
        """Count completed Roll Tickets."""
        return frappe.db.count(
            cls.DOCTYPE,
            {"roll_status": RollStatus.COMPLETED},
        )