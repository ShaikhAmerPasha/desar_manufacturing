"""
DESAR Manufacturing — Repack Service

Auto-creates Repack Stock Entry after Final Packing QI submission.

DYNAMIC MODE (when DESAR Settings → Grade Configuration is filled):
  Reads grades from configuration table — supports any number of grades.
  Client can add Grade D, E, F in settings — Repack adapts automatically.

LEGACY MODE (when Grade Configuration is empty):
  Falls back to hardcoded A/B/C behavior — backward compatible.
  Grade A → Full cost, Grade B → 60%, Scrap → 5%.
"""
import frappe
from frappe import _
from frappe.utils import nowdate, flt
from typing import Optional, Tuple, List

from desar_manufacturing.constants import QIFields, SHEMAGH_SCRAP
from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.repositories.stock_entry_repository import StockEntryRepository
from desar_manufacturing.repositories.work_order_repository import WorkOrderRepository
from desar_manufacturing.utils.validation_utils import derive_grade_b_item


class RepackService:
    """
    Creates the grade-split Repack Stock Entry.

    Supports both dynamic (Grade Configuration) and legacy (hardcoded A/B/C) modes.
    Dynamic mode is used when DESAR Settings has grade_configuration rows filled.
    """

    # Legacy valuation ratios — used only when Grade Configuration is empty
    GRADE_B_RATIO = 0.60
    SCRAP_RATIO   = 0.05

    @classmethod
    def create_from_final_qi(cls, qi_doc) -> Optional[str]:
        """
        Auto-create Repack SE from a submitted Final Packing QI.

        Detects whether to use dynamic or legacy grade configuration.
        """
        if not SettingsManager.is_auto_repack_enabled():
            return None

        company = SettingsManager.get_company()
        wh_src = SettingsManager.get_warehouse("cutting_packing_warehouse")

        # ── Choose mode ───────────────────────────────────────────────────
        grade_config = SettingsManager.get_grade_configuration()

        if grade_config:
            # Dynamic mode — read grades from configuration
            items, total = cls._build_items_dynamic(qi_doc, grade_config, wh_src)
        else:
            # Legacy mode — hardcoded A/B/C
            items, total = cls._build_items_legacy(qi_doc, wh_src)

        if not items or not total:
            return None

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

    # ── Dynamic mode ──────────────────────────────────────────────────────────

    @classmethod
    def _build_items_dynamic(cls, qi_doc, grade_config: list, wh_src: str):
        """
        Build Repack SE items dynamically from Grade Configuration.

        Reads grade counts from DESAR QI Grade Readings child table.
        Falls back to legacy fixed fields if child table is empty.
        """
        # Get base item from WO chain
        base_item = cls._get_base_item(qi_doc)
        if not base_item:
            frappe.msgprint(
                _("Cannot determine base item for Repack. Please create manually."),
                alert=True, indicator="orange",
            )
            return [], 0

        val_rate = StockEntryRepository.get_valuation_rate(base_item, wh_src)

        # Read grade counts from child table
        grade_readings = cls._read_grade_readings_from_qi(qi_doc)
        if not grade_readings:
            # Fallback: try legacy fields
            return cls._build_items_legacy(qi_doc, wh_src)

        total = sum(r["qty"] for r in grade_readings)
        if not total:
            return [], 0

        items = [{
            "item_code":   base_item,
            "s_warehouse": wh_src,
            "qty":         total,
            "uom":         "Pcs",
        }]

        for reading in grade_readings:
            qty = reading["qty"]
            if not qty:
                continue

            grade = next((g for g in grade_config if g.grade_code == reading["grade_code"]), None)
            if not grade:
                continue

            # Determine item code
            if grade.is_scrap and grade.scrap_item:
                item_code = grade.scrap_item
            elif grade.item_suffix:
                item_code = cls._derive_item_with_suffix(base_item, grade.item_suffix)
            else:
                continue

            if not item_code or not frappe.db.exists("Item", item_code):
                frappe.msgprint(
                    _("Item for Grade {0} not found — skipping in Repack.").format(grade.grade_code),
                    alert=True, indicator="orange",
                )
                continue

            items.append({
                "item_code":               item_code,
                "t_warehouse":             grade.target_warehouse,
                "qty":                     qty,
                "uom":                     "Pcs",
                "is_finished_item":        1,
                "set_basic_rate_manually": 1,
                "basic_rate":              round(val_rate * flt(grade.valuation_pct) / 100, 2),
            })

        return items, total

    @classmethod
    def _read_grade_readings_from_qi(cls, qi_doc) -> list:
        """
        Read grade counts from DESAR QI Grade Readings child table.
        Returns list of {grade_code, qty} dicts.
        Falls back to empty list if child table is not populated.
        """
        readings = qi_doc.get("custom_desar_grade_readings") or []
        if not readings:
            return []

        result = []
        for row in readings:
            qty = flt(row.get("qty") or 0)
            if qty > 0:
                result.append({
                    "grade_code": row.get("grade_code") or "",
                    "qty":        qty,
                })
        return result

    @classmethod
    def _derive_item_with_suffix(cls, base_item: str, suffix: str) -> str:
        """
        Derive item code by replacing existing grade suffix with new one.
        e.g. base_item="Shemagh-VIC-60-A", suffix="-B" → "Shemagh-VIC-60-B"
        """
        if not base_item or not suffix:
            return ""
        # Remove existing grade suffix (-A, -B etc.) and add new one
        for existing_suffix in ["-A", "-B", "-C", "-D", "-E", "-F"]:
            if base_item.endswith(existing_suffix):
                return base_item[:-len(existing_suffix)] + suffix
        # No existing suffix — just append
        return base_item + suffix

    @classmethod
    def _get_base_item(cls, qi_doc) -> str:
        """Get the Grade A / base item from QI reference chain."""
        if qi_doc.reference_type == "Stock Entry" and qi_doc.reference_name:
            wo_name = StockEntryRepository.get_work_order(qi_doc.reference_name)
            if wo_name:
                context = WorkOrderRepository.get_design_context(wo_name)
                item = context.get("production_item") or ""
                if item:
                    return item
        return qi_doc.item_code or ""

    # ── Legacy mode ───────────────────────────────────────────────────────────

    @classmethod
    def _build_items_legacy(cls, qi_doc, wh_src: str):
        """
        Legacy grade build — hardcoded A/B/C.
        Used when Grade Configuration is not set up in DESAR Settings.
        Kept for backward compatibility.
        """
        grade_a = flt(qi_doc.get(QIFields.FINAL_A))
        grade_b = flt(qi_doc.get(QIFields.FINAL_B))
        grade_c = flt(qi_doc.get(QIFields.FINAL_C))
        total   = grade_a + grade_b + grade_c

        if not total:
            return [], 0

        wh_a  = SettingsManager.get_warehouse("fg_grade_a_warehouse")
        wh_b  = SettingsManager.get_warehouse("fg_grade_b_warehouse")
        wh_sc = SettingsManager.get_warehouse("scrap_warehouse")

        item_a, item_b = cls._resolve_grade_items_legacy(qi_doc)
        if not item_a:
            frappe.msgprint(
                _("Cannot determine Grade A item for Repack. Please create manually."),
                alert=True, indicator="orange",
            )
            return [], 0

        if grade_b and item_b and not frappe.db.exists("Item", item_b):
            frappe.msgprint(
                _("Grade B item <b>{0}</b> does not exist. Grade B skipped.").format(item_b),
                alert=True, indicator="orange",
            )
            item_b = None

        val_rate = StockEntryRepository.get_valuation_rate(item_a, wh_src)

        items = [{"item_code": item_a, "s_warehouse": wh_src, "qty": total, "uom": "Pcs"}]

        if grade_a:
            items.append({
                "item_code": item_a, "t_warehouse": wh_a, "qty": grade_a, "uom": "Pcs",
                "is_finished_item": 1, "set_basic_rate_manually": 1, "basic_rate": val_rate,
            })
        if grade_b and item_b:
            items.append({
                "item_code": item_b, "t_warehouse": wh_b, "qty": grade_b, "uom": "Pcs",
                "is_finished_item": 1, "set_basic_rate_manually": 1,
                "basic_rate": round(val_rate * cls.GRADE_B_RATIO, 2),
            })
        if grade_c:
            items.append({
                "item_code": SHEMAGH_SCRAP, "t_warehouse": wh_sc, "qty": grade_c, "uom": "Pcs",
                "is_finished_item": 1, "set_basic_rate_manually": 1,
                "basic_rate": round(val_rate * cls.SCRAP_RATIO, 2),
            })

        return items, total

    @classmethod
    def _resolve_grade_items_legacy(cls, qi_doc) -> Tuple[Optional[str], Optional[str]]:
        item_a = cls._get_base_item(qi_doc)
        item_b = derive_grade_b_item(item_a) if item_a else None
        return item_a or None, item_b

    @classmethod
    def _build_items(
        cls,
        item_a, item_b, wh_src, wh_a, wh_b, wh_sc,
        total, grade_a, grade_b, grade_c, val_rate
    ) -> list:
        """
        Alias for backward compatibility with existing tests.
        Called by test_roll_ticket_service.py TestRepackServiceUnit tests.
        Builds legacy A/B/C items directly without reading from DB.
        """
        from desar_manufacturing.constants import SHEMAGH_SCRAP

        items = [{"item_code": item_a, "s_warehouse": wh_src, "qty": total, "uom": "Pcs"}]

        if grade_a and item_a:
            items.append({
                "item_code": item_a, "t_warehouse": wh_a, "qty": grade_a, "uom": "Pcs",
                "is_finished_item": 1, "set_basic_rate_manually": 1, "basic_rate": val_rate,
            })
        if grade_b and item_b:
            items.append({
                "item_code": item_b, "t_warehouse": wh_b, "qty": grade_b, "uom": "Pcs",
                "is_finished_item": 1, "set_basic_rate_manually": 1,
                "basic_rate": round(val_rate * cls.GRADE_B_RATIO, 2),
            })
        if grade_c:
            items.append({
                "item_code": SHEMAGH_SCRAP, "t_warehouse": wh_sc, "qty": grade_c, "uom": "Pcs",
                "is_finished_item": 1, "set_basic_rate_manually": 1,
                "basic_rate": round(val_rate * cls.SCRAP_RATIO, 2),
            })
        return items
