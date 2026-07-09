"""
DESAR Manufacturing — Roll Ticket Service

All Roll Ticket business logic.

v3.0: Fully dynamic — reads grade counts from DESAR QI Grade Readings
child table. Legacy static fields (grey_qty_a etc.) have been removed.
"""
import frappe
from frappe import _
from frappe.utils import flt
from typing import Optional

from desar_manufacturing.constants import RollStatus
from desar_manufacturing.repositories.roll_ticket_repository import RollTicketRepository
from desar_manufacturing.repositories.work_order_repository import WorkOrderRepository
from desar_manufacturing.repositories.stock_entry_repository import StockEntryRepository
from desar_manufacturing.config.settings_manager import SettingsManager


class RollTicketService:
    """
    Business logic for Roll Ticket lifecycle.

    Lifecycle:
      1. create_for_grey_roll() — called when roll_ticket_trigger item SE submits
      2. update_from_qi()       — called when any QI submits
    """

    @classmethod
    def create_for_grey_roll(
        cls,
        stock_entry_name: str,
        batch_no: str,
        qty: float,
        uom: str = "Nos",
    ) -> Optional[str]:
        """
        Create a Roll Ticket when a roll_ticket_trigger item is produced.
        Idempotent — skips silently if Roll Ticket already exists for batch.
        """
        if not SettingsManager.is_auto_roll_ticket_enabled():
            return None

        if RollTicketRepository.exists_for_batch(batch_no):
            frappe.logger().debug(
                f"DESAR: Roll Ticket already exists for batch {batch_no} — skipping"
            )
            return None

        wo_name = StockEntryRepository.get_work_order(stock_entry_name)
        wo_context = WorkOrderRepository.get_design_context(wo_name) if wo_name else {}
        parent_beam = StockEntryRepository.get_consumed_beam_batch(stock_entry_name)
        machine_no = (
            WorkOrderRepository.get_weaving_workstation(wo_name)
            if wo_name else None
        )

        data = {
            "roll_batch":        batch_no,
            "design_no":         wo_context.get("design_no") or "",
            "article_name":      wo_context.get("article_name") or "",
            "size":              "",
            "sales_order_ref":   wo_context.get("sales_order") or "",
            "roll_status":       RollStatus.IN_GREY_STORE,
            "qty_in_roll":       flt(qty),
            "uom":               uom or "Nos",
            "parent_beam_batch": parent_beam or "",
            "machine_no":        machine_no or "",
        }

        try:
            rt_name = RollTicketRepository.create(data)
            frappe.msgprint(
                _("Roll Ticket <b>{0}</b> created for batch {1}").format(rt_name, batch_no),
                alert=True,
            )
            return rt_name

        except frappe.DuplicateEntryError:
            return RollTicketRepository.find_by_batch(batch_no)

        except Exception:
            frappe.log_error(
                title=f"DESAR: Roll Ticket creation failed — batch {batch_no}",
                message=frappe.get_traceback(),
            )
            return None

    @classmethod
    def update_from_qi(cls, qi_doc) -> Optional[str]:
        """
        Update Roll Ticket stage grades from a submitted QI.

        Dynamic mode: reads from custom_desar_grade_readings child table.
        Updates stage_grades child table on Roll Ticket.
        Also updates roll_status based on stage sequence.
        """
        rt_name = cls._find_roll_ticket_for_qi(qi_doc)
        if not rt_name:
            frappe.logger().debug(
                f"DESAR: No Roll Ticket found for QI {qi_doc.name}"
            )
            return None

        # Read grade counts from dynamic child table
        grade_readings = qi_doc.get("custom_desar_grade_readings") or []
        stage_name = qi_doc.get("custom_desar_stage_name") or ""

        if grade_readings and stage_name:
            # Dynamic mode — update stage_grades child table
            cls._update_stage_grades(rt_name, qi_doc, stage_name, grade_readings)
        else:
            frappe.logger().debug(
                f"DESAR: QI {qi_doc.name} has no grade readings — nothing to update"
            )
            return None

        frappe.msgprint(
            _("Roll Ticket <b>{0}</b> updated — stage: {1}").format(rt_name, stage_name),
            alert=True,
        )
        return rt_name

    @classmethod
    def _update_stage_grades(cls, rt_name: str, qi_doc, stage_name: str, grade_readings: list):
        """
        Update Roll Ticket stage_grades child table.
        Also update roll_status based on is_final_stage.
        """
        rt = frappe.get_doc("Roll Ticket", rt_name)

        # Remove existing rows for this stage (idempotency)
        rt.stage_grades = [
            r for r in (rt.stage_grades or [])
            if r.stage_name != stage_name
        ]

        # Add new rows from QI grade readings
        for reading in grade_readings:
            qty = flt(reading.get("qty") or 0)
            row_data = {
                "stage_name":  stage_name,
                "grade_code":  reading.get("grade_code") or "",
                "grade_label": reading.get("grade_label") or "",
                "qty":         qty,
            }
            # Only set qi_reference if QI actually exists in DB
            # Avoids LinkValidationError in tests with mock QI names
            qi_name = qi_doc.name if hasattr(qi_doc, 'name') else ""
            if qi_name and frappe.db.exists("Quality Inspection", qi_name):
                row_data["qi_reference"] = qi_name
            rt.append("stage_grades", row_data)

        # Update roll_status based on stage
        new_status = cls._get_next_status(rt_name, stage_name, qi_doc)
        if new_status:
            rt.roll_status = new_status

        rt.save(ignore_permissions=True)

    @classmethod
    def _get_next_status(cls, rt_name: str, stage_name: str, qi_doc) -> Optional[str]:
        """
        Determine new roll_status after QI submission.

        Reads Stage Configuration to find next status.
        Final stage → Completed.
        Non-final stage → In {next_stage_name}.
        """
        # Check if this is final stage
        is_final = frappe.db.get_value(
            "DESAR Stage Configuration",
            filters={"stage_name": stage_name, "is_final_stage": 1},
            fieldname="name",
        )
        if is_final:
            return RollStatus.COMPLETED

        # Find next stage name
        current_seq = frappe.db.get_value(
            "DESAR Stage Configuration",
            filters={"stage_name": stage_name},
            fieldname="stage_seq",
        )
        if current_seq:
            next_stage = frappe.db.get_value(
                "DESAR Stage Configuration",
                filters={"stage_seq": int(current_seq) + 1},
                fieldname="stage_name",
            )
            if next_stage:
                return cls._stage_to_status(next_stage)

        # Fallback mapping
        stage_lower = stage_name.lower()
        if "weaving" in stage_lower or "grey" in stage_lower:
            return RollStatus.IN_FINISHING
        elif "dyeing" in stage_lower:
            return RollStatus.IN_FINISHING
        elif "finishing" in stage_lower:
            return RollStatus.IN_PACKING
        elif "packing" in stage_lower or "final" in stage_lower:
            return RollStatus.COMPLETED

        return RollStatus.IN_FINISHING  # safe default

    @classmethod
    def _stage_to_status(cls, stage_name: str) -> str:
        """Map stage name to valid Roll Ticket Select status option."""
        mapping = {
            "Warping":   RollStatus.IN_GREY_STORE,
            "Weaving":   RollStatus.IN_GREY_STORE,
            "Dyeing":    RollStatus.IN_FINISHING,
            "Finishing": RollStatus.IN_PACKING,
            "Packing":   RollStatus.COMPLETED,
        }
        # Check exact match first
        if stage_name in mapping:
            return mapping[stage_name]
        # Keyword fallback
        lower = stage_name.lower()
        if "pack" in lower or "final" in lower:
            return RollStatus.COMPLETED
        elif "finish" in lower:
            return RollStatus.IN_PACKING
        return RollStatus.IN_FINISHING  # safe default for unknown stages

    @classmethod
    def _find_roll_ticket_for_qi(cls, qi_doc) -> Optional[str]:
        """
        Find Roll Ticket for a QI.

        Strategy 1: custom_roll_ticket explicit link (set at QI creation)
        Strategy 2: batch_no direct lookup (fallback for manual QIs)
        """
        # Strategy 1 — explicit link
        rt_name = qi_doc.get("custom_roll_ticket") or ""
        if rt_name:
            return rt_name

        # Strategy 2 — batch fallback
        batch_no = qi_doc.get("batch_no") or ""
        if batch_no:
            rt_name = RollTicketRepository.find_by_batch(batch_no)
            if rt_name:
                return rt_name

        return None

    # ── Dynamic stage grade update (kept for explicit calls) ──────────────────

    @classmethod
    def update_stage_grades_dynamic(cls, rt_name: str, qi_doc, stage_name: str):
        """Public method for explicit stage grade update calls."""
        readings = qi_doc.get("custom_desar_grade_readings") or []
        if readings:
            cls._update_stage_grades(rt_name, qi_doc, stage_name, readings)
