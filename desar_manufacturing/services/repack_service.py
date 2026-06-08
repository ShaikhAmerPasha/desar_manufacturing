"""
DESAR Manufacturing — Repack Service

Auto-creates Repack Stock Entry after Final Packing QI submission.
Grade split with correct valuation:
  Grade A → Full production cost (val_rate)
  Grade B → 60% of Grade A (industry standard for B-grade textile)
  Scrap   → 5% of Grade A (scrap recovery value)
"""
import frappe
from frappe import _
from frappe.utils import nowdate, flt
from typing import Optional, Tuple

from desar_manufacturing.constants import QIFields, SHEMAGH_SCRAP
from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.repositories.stock_entry_repository import StockEntryRepository
from desar_manufacturing.repositories.work_order_repository import WorkOrderRepository
from desar_manufacturing.utils.validation_utils import derive_grade_b_item


class RepackService:
    """
    Creates the grade-split Repack Stock Entry.

    Structure of Repack SE:
      Row 1 (source):  item_a,  s_warehouse=cutting_packing,  qty=total
      Row 2 (target):  item_a,  t_warehouse=fg_grade_a,       qty=grade_a
      Row 3 (target):  item_b,  t_warehouse=fg_grade_b,       qty=grade_b
      Row 4 (target):  scrap,   t_warehouse=scrap_yard,        qty=grade_c
    """

    # Valuation ratios
    GRADE_B_RATIO = 0.60   # Grade B = 60% of Grade A cost
    SCRAP_RATIO   = 0.05   # Scrap   =  5% of Grade A cost

    @classmethod
    def create_from_final_qi(cls, qi_doc) -> Optional[str]:
        """
        Auto-create Repack SE from a submitted Final Packing QI.

        Called only when custom_cutted_qty_* fields have data (final QI).

        Args:
            qi_doc: Submitted Quality Inspection document

        Returns:
            Stock Entry name if created, None if skipped or failed
        """
        if not SettingsManager.is_auto_repack_enabled():
            return None

        grade_a = flt(qi_doc.get(QIFields.FINAL_A))
        grade_b = flt(qi_doc.get(QIFields.FINAL_B))
        grade_c = flt(qi_doc.get(QIFields.FINAL_C))
        total   = grade_a + grade_b + grade_c

        if not total:
            return None

        # Get warehouses — raises descriptive error if any not configured
        wh_src = SettingsManager.get_warehouse("cutting_packing_warehouse")
        wh_a   = SettingsManager.get_warehouse("fg_grade_a_warehouse")
        wh_b   = SettingsManager.get_warehouse("fg_grade_b_warehouse")
        wh_sc  = SettingsManager.get_warehouse("scrap_warehouse")
        company = SettingsManager.get_company()

        # Resolve Grade A and Grade B item codes
        item_a, item_b = cls._resolve_grade_items(qi_doc)
        if not item_a:
            frappe.msgprint(
                _("Cannot determine Grade A item for Repack. Please create manually."),
                alert=True,
                indicator="orange",
            )
            return None

        # Validate Grade B item exists if grade_b > 0
        if grade_b and item_b and not frappe.db.exists("Item", item_b):
            frappe.msgprint(
                _("Grade B item <b>{0}</b> does not exist in ERPNext. "
                  "Grade B will be skipped in Repack. Create the item and repack manually.").format(item_b),
                alert=True,
                indicator="orange",
            )
            item_b = None

        # Valuation rate from source warehouse SLE
        val_rate = StockEntryRepository.get_valuation_rate(item_a, wh_src)

        # Build items
        items = cls._build_items(
            item_a=item_a,
            item_b=item_b,
            wh_src=wh_src,
            wh_a=wh_a,
            wh_b=wh_b,
            wh_sc=wh_sc,
            total=total,
            grade_a=grade_a,
            grade_b=grade_b,
            grade_c=grade_c,
            val_rate=val_rate,
        )

        try:
            se = frappe.get_doc({
                "doctype":          "Stock Entry",
                "stock_entry_type": "Repack",
                "purpose":          "Repack",
                "posting_date":     nowdate(),
                "company":          company,
                "custom_source_qi": qi_doc.name,
                "items":            items,
            })
            se.insert(ignore_permissions=True)

            frappe.msgprint(
                _("Repack Stock Entry <b>{0}</b> created — review and submit.").format(
                    frappe.utils.get_link_to_form("Stock Entry", se.name)
                ),
            )
            return se.name

        except Exception:
            frappe.log_error(
                title="DESAR: Repack SE creation failed",
                message=frappe.get_traceback(),
            )
            frappe.msgprint(
                _("Repack could not be auto-created. Please create it manually."),
                alert=True,
                indicator="orange",
            )
            return None

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _resolve_grade_items(cls, qi_doc) -> Tuple[Optional[str], Optional[str]]:
        """
        Determine Grade A and Grade B item codes.

        Source chain:
          1. QI reference SE → Work Order → production_item  (most reliable)
          2. QI item_code field                               (fallback)
        """
        item_a = None

        if qi_doc.reference_type == "Stock Entry" and qi_doc.reference_name:
            wo_name = StockEntryRepository.get_work_order(qi_doc.reference_name)
            if wo_name:
                context = WorkOrderRepository.get_design_context(wo_name)
                item_a = context.get("production_item") or ""

        if not item_a:
            item_a = qi_doc.item_code or ""

        item_b = derive_grade_b_item(item_a) if item_a else None

        return item_a or None, item_b

    @classmethod
    def _build_items(
        cls,
        item_a: str,
        item_b: Optional[str],
        wh_src: str,
        wh_a: str,
        wh_b: str,
        wh_sc: str,
        total: float,
        grade_a: float,
        grade_b: float,
        grade_c: float,
        val_rate: float,
    ) -> list:
        """
        Build the Repack SE items list.

        Row 1: Source — consumes all pieces from Cutting & Packing Floor
        Row 2: Grade A output → Finished Goods Grade A (full cost)
        Row 3: Grade B output → Finished Goods Grade B (60% cost)
        Row 4: Scrap output   → Scrap Yard              (5% cost)
        """
        items = [
            {
                "item_code":   item_a,
                "s_warehouse": wh_src,
                "qty":         total,
                "uom":         "Pcs",
            },
        ]

        if grade_a and item_a:
            items.append({
                "item_code":              item_a,
                "t_warehouse":            wh_a,
                "qty":                    grade_a,
                "uom":                    "Pcs",
                "is_finished_item":       1,
                "set_basic_rate_manually": 1,
                "basic_rate":             val_rate,
            })

        if grade_b and item_b:
            items.append({
                "item_code":              item_b,
                "t_warehouse":            wh_b,
                "qty":                    grade_b,
                "uom":                    "Pcs",
                "is_finished_item":       1,
                "set_basic_rate_manually": 1,
                "basic_rate":             round(val_rate * cls.GRADE_B_RATIO, 2),
            })

        if grade_c:
            items.append({
                "item_code":              SHEMAGH_SCRAP,
                "t_warehouse":            wh_sc,
                "qty":                    grade_c,
                "uom":                    "Pcs",
                "is_finished_item":       1,
                "set_basic_rate_manually": 1,
                "basic_rate":             round(val_rate * cls.SCRAP_RATIO, 2),
            })

        return items
