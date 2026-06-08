"""
DESAR Manufacturing — Roll Ticket Service

All Roll Ticket business logic.
Uses repositories for all DB access.
Uses constants for all strings — no magic strings here.
"""
import frappe
from frappe import _
from frappe.utils import flt
from typing import Optional

from desar_manufacturing.constants import (
    QIFields, QIStage, RollStatus
)
from desar_manufacturing.repositories.roll_ticket_repository import RollTicketRepository
from desar_manufacturing.repositories.work_order_repository import WorkOrderRepository
from desar_manufacturing.repositories.stock_entry_repository import StockEntryRepository
from desar_manufacturing.config.settings_manager import SettingsManager


class RollTicketService:
    """
    Business logic for Roll Ticket lifecycle.

    Lifecycle:
      1. create_for_grey_roll()  — called when Grey Roll Manufacture SE submits
      2. update_from_qi()        — called when any QI submits
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
        Create a Roll Ticket when a Grey Roll batch is produced.

        Idempotent — skips silently if Roll Ticket already exists for batch.
        Does NOT block SE submission on failure — logs error and continues.

        Args:
            stock_entry_name: Manufacture Stock Entry name
            batch_no: Grey Roll batch number (from Serial and Batch Bundle)
            qty: Quantity produced (from SE row)
            uom: Unit of measure

        Returns:
            Roll Ticket name if created, None otherwise
        """
        if not SettingsManager.is_auto_roll_ticket_enabled():
            return None

        # Idempotency guard
        if RollTicketRepository.exists_for_batch(batch_no):
            frappe.logger().debug(
                f"DESAR: Roll Ticket already exists for batch {batch_no} — skipping"
            )
            return None

        # Gather context from linked Work Order
        wo_name = StockEntryRepository.get_work_order(stock_entry_name)
        wo_context = WorkOrderRepository.get_design_context(wo_name) if wo_name else {}

        # Get parent beam batch from consumed items in this SE
        parent_beam = StockEntryRepository.get_consumed_beam_batch(stock_entry_name)

        # Get machine from Weaving Job Card — may be None if Job Card not complete yet
        machine_no = (
            WorkOrderRepository.get_weaving_workstation(wo_name)
            if wo_name else None
        )

        data = {
            "roll_batch":       batch_no,
            "design_no":        wo_context.get("design_no") or "",
            "article_name":     wo_context.get("article_name") or "",
            # size is not on WO — left blank, inspector fills on Roll Ticket manually
            # or it can be derived from production_item name in future
            "size":             "",
            "sales_order_ref":  wo_context.get("sales_order") or "",
            "roll_status":      RollStatus.IN_GREY_STORE,
            "qty_in_roll":      flt(qty),
            "uom":              uom or "Nos",
            "parent_beam_batch": parent_beam or "",
            "machine_no":       machine_no or "",
        }

        try:
            rt_name = RollTicketRepository.create(data)
            frappe.msgprint(
                _("Roll Ticket <b>{0}</b> created for batch {1}").format(rt_name, batch_no),
                alert=True,
            )
            return rt_name

        except frappe.DuplicateEntryError:
            # Race condition — another worker created it at the same time
            return RollTicketRepository.find_by_batch(batch_no)

        except Exception:
            # Never block SE submission due to Roll Ticket failure
            frappe.log_error(
                title=f"DESAR: Roll Ticket creation failed — batch {batch_no}",
                message=frappe.get_traceback(),
            )
            return None

    @classmethod
    def update_from_qi(cls, qi_doc) -> Optional[str]:
        """
        Update Roll Ticket grade counts from a submitted Quality Inspection.

        Detects the QI stage from which custom grade fields have data.
        Finds Roll Ticket by batch number (primary) or design+article chain (fallback).

        Args:
            qi_doc: Submitted Quality Inspection document

        Returns:
            Roll Ticket name if updated, None if no matching Roll Ticket found
        """
        rt_name = cls._find_roll_ticket_for_qi(qi_doc)
        if not rt_name:
            frappe.logger().debug(
                f"DESAR: No Roll Ticket found for QI {qi_doc.name} — nothing to update"
            )
            return None

        stage = cls._detect_qi_stage(qi_doc)

        if stage == QIStage.GREY:
            RollTicketRepository.update_grey_grades(
                rt_name,
                qty_a=flt(qi_doc.get(QIFields.GREY_A)),
                qty_b=flt(qi_doc.get(QIFields.GREY_B)),
                qty_c=flt(qi_doc.get(QIFields.GREY_C)),
            )
        elif stage == QIStage.FINISHING:
            RollTicketRepository.update_finishing_grades(
                rt_name,
                qty_a=flt(qi_doc.get(QIFields.FIN_A)),
                qty_b=flt(qi_doc.get(QIFields.FIN_B)),
                qty_c=flt(qi_doc.get(QIFields.FIN_C)),
            )
        elif stage == QIStage.FINAL:
            RollTicketRepository.update_final_grades(
                rt_name,
                qty_a=flt(qi_doc.get(QIFields.FINAL_A)),
                qty_b=flt(qi_doc.get(QIFields.FINAL_B)),
                qty_c=flt(qi_doc.get(QIFields.FINAL_C)),
            )
        else:
            # QI has no grade data — not a DESAR grading QI
            return None

        frappe.msgprint(
            _("Roll Ticket <b>{0}</b> updated — stage: {1}").format(rt_name, stage),
            alert=True,
        )
        return rt_name

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _detect_qi_stage(cls, qi_doc) -> str:
        """
        Detect which QI stage this inspection belongs to.

        Each inspector fills only their stage's custom fields:
          - Grey inspector    → fills custom_grey_qty_*
          - Finishing inspector → fills custom_finished_qty_*
          - Packing inspector → fills custom_cutted_qty_*

        Priority: Final > Finishing > Grey (most specific first)
        """
        if flt(qi_doc.get(QIFields.FINAL_A)) + flt(qi_doc.get(QIFields.FINAL_B)) + flt(qi_doc.get(QIFields.FINAL_C)):
            return QIStage.FINAL

        if flt(qi_doc.get(QIFields.FIN_A)) + flt(qi_doc.get(QIFields.FIN_B)) + flt(qi_doc.get(QIFields.FIN_C)):
            return QIStage.FINISHING

        if flt(qi_doc.get(QIFields.GREY_A)) + flt(qi_doc.get(QIFields.GREY_B)) + flt(qi_doc.get(QIFields.GREY_C)):
            return QIStage.GREY

        return QIStage.UNKNOWN

    @classmethod
    def _find_roll_ticket_for_qi(cls, qi_doc) -> Optional[str]:
        """
        Find Roll Ticket for a QI document.

        Strategy 1 (primary): custom_roll_ticket field on QI.
            Set explicitly at QI creation time by create_quality_inspection() API.
            Single field read — no chain traversal. Fast and reliable.

        Strategy 2 (fallback): qi.batch_no → direct batch lookup.
            For manually created QIs or old QIs without custom_roll_ticket.

        The previous 4-strategy chain traversal approach has been replaced
        by Option 1 — explicit linking at QI creation time.
        Cleaner, faster, upgrade-safe.
        """
        # Strategy 1 — explicit link set at creation time
        rt_name = qi_doc.get("custom_roll_ticket") or ""
        if rt_name:
            return rt_name

        # Strategy 2 — batch fallback for manually created QIs
        batch_no = qi_doc.get("batch_no") or ""
        if batch_no:
            rt_name = RollTicketRepository.find_by_batch(batch_no)
            if rt_name:
                return rt_name

        return None

    @classmethod
    def _find_roll_ticket_via_finished_roll(cls, se_name: str) -> Optional[str]:
        """
        Strategy 4: Shemagh SE → consumed Finished Roll batch
        → find SE that produced that Finished Roll batch
        → consumed Grey Roll batch in that SE
        → find Roll Ticket by Grey Roll batch

        Used for Final Packing QI where the reference SE is the
        Shemagh Manufacture SE which consumes Finished Roll.
        """
        from desar_manufacturing.constants import FINISHED_ROLL, GREY_ROLL

        # Step 1: Find Finished Roll batch consumed in Shemagh SE
        finished_batch = cls._get_batch_from_sle_consumed(se_name, FINISHED_ROLL)
        if not finished_batch:
            return None

        # Step 2: Find SE that produced that Finished Roll batch
        producing_se = frappe.db.sql("""
            SELECT sle.voucher_no
            FROM `tabStock Ledger Entry` sle
            JOIN `tabSerial and Batch Entry` sbe
                ON sbe.parent = sle.serial_and_batch_bundle
            WHERE sbe.batch_no = %s
            AND sle.actual_qty > 0
            AND sle.is_cancelled = 0
            LIMIT 1
        """, (finished_batch,), as_dict=True)

        if not producing_se:
            # Try direct batch_no on SLE (v14 style)
            producing_se_name = frappe.db.get_value(
                "Stock Ledger Entry",
                filters={
                    "item_code": FINISHED_ROLL,
                    "batch_no": finished_batch,
                    "actual_qty": [">", 0],
                    "is_cancelled": 0,
                },
                fieldname="voucher_no",
            )
            if not producing_se_name:
                return None
        else:
            producing_se_name = producing_se[0].voucher_no

        # Step 3: Find Grey Roll batch consumed in Finished Roll SE
        grey_batch = cls._find_consumed_grey_batch(producing_se_name)
        if not grey_batch:
            return None

        # Step 4: Find Roll Ticket by Grey Roll batch
        return RollTicketRepository.find_by_batch(grey_batch)

    @classmethod
    def _get_batch_from_sle_consumed(cls, se_name: str, item_code: str) -> Optional[str]:
        """
        Get batch of a consumed item (actual_qty < 0) from SLE.
        Checks both direct batch_no and Serial and Batch Bundle.
        """
        # Direct batch_no
        result = frappe.db.get_value(
            "Stock Ledger Entry",
            filters={
                "voucher_no": se_name,
                "item_code": item_code,
                "actual_qty": ["<", 0],
                "is_cancelled": 0,
            },
            fieldname="batch_no",
        )
        if result:
            return result

        # Via bundle
        bundle = frappe.db.get_value(
            "Stock Ledger Entry",
            filters={
                "voucher_no": se_name,
                "item_code": item_code,
                "actual_qty": ["<", 0],
                "is_cancelled": 0,
            },
            fieldname="serial_and_batch_bundle",
        )
        if bundle:
            return frappe.db.get_value(
                "Serial and Batch Entry",
                filters={"parent": bundle},
                fieldname="batch_no",
            )
        return None

    @classmethod
    def _find_consumed_grey_batch(cls, se_name: str) -> Optional[str]:
        """
        Find the Grey Roll batch consumed in a Stock Entry.
        Used as Strategy 3 fallback to trace Roll Ticket from downstream SEs.
        """
        from desar_manufacturing.constants import GREY_ROLL

        # Check direct batch_no on SLE (v14 style)
        result = frappe.db.get_value(
            "Stock Ledger Entry",
            filters={
                "voucher_no": se_name,
                "item_code": GREY_ROLL,
                "actual_qty": ["<", 0],  # consumed = negative qty
                "is_cancelled": 0,
            },
            fieldname="batch_no",
        )
        if result:
            return result

        # Check via Serial and Batch Bundle on SLE
        sle_bundle = frappe.db.get_value(
            "Stock Ledger Entry",
            filters={
                "voucher_no": se_name,
                "item_code": GREY_ROLL,
                "actual_qty": ["<", 0],
                "is_cancelled": 0,
            },
            fieldname="serial_and_batch_bundle",
        )
        if sle_bundle:
            batch = frappe.db.get_value(
                "Serial and Batch Entry",
                filters={"parent": sle_bundle},
                fieldname="batch_no",
            )
            if batch:
                return batch

        return None