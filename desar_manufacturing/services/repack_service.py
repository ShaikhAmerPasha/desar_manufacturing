"""
DESAR Manufacturing — Repack Service

Auto-creates Repack Stock Entry after Final Packing QI submission.

DYNAMIC MODE (when DESAR Settings → Grade Configuration is filled):
  Reads grades from configuration table — supports any number of grades.
  Client can add Grade D, E, F in settings — Repack adapts automatically.

LEGACY MODE (when Grade Configuration is empty):
  Falls back to hardcoded A/B behavior — backward compatible.
  Grade A → Full cost, Grade B → 60%.

Scrap (grade rows flagged is_scrap, or legacy Grade C) is disposed, never sold —
it is consumed from the source warehouse like the rest of the output but gets
no valued output row, so it carries no stock value. Its quantity is still
visible via DESAR Roll Ticket Stage Grade / the grade yield reports.
"""
import frappe
from frappe import _
from frappe.utils import nowdate, flt
from typing import Optional, Tuple, List

from desar_manufacturing.constants import QIFields
from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.repositories.stock_entry_repository import StockEntryRepository
from desar_manufacturing.repositories.work_order_repository import WorkOrderRepository
from desar_manufacturing.utils.validation_utils import derive_grade_b_item


class RepackService:
    """
    Creates the grade-split Repack Stock Entry.

    Supports both dynamic (Grade Configuration) and legacy (hardcoded A/B) modes.
    Dynamic mode is used when DESAR Settings has grade_configuration rows filled.
    """

    # Legacy valuation ratio — used only when Grade Configuration is empty
    GRADE_B_RATIO = 0.60

    @classmethod
    def _stock_uom(cls, item_code: str) -> str:
        """Real stock UOM for item_code — never assume a hardcoded UOM name exists on-site."""
        uom = frappe.db.get_value("Item", item_code, "stock_uom")
        if not uom:
            frappe.throw(_("Item {0} has no Stock UOM set.").format(item_code))
        return uom

    @classmethod
    def create_from_final_qi(cls, qi_doc) -> Optional[str]:
        """
        Auto-create Repack SE from a submitted Final Packing QI.

        Detects whether to use dynamic or legacy grade configuration.
        """
        if not SettingsManager.is_auto_repack_enabled():
            return None

        company = SettingsManager.get_company()
        # The Packing Work Order's actual output lands in fg_grade_a_warehouse
        # (events/work_order.py::_get_warehouses_for_stage("pack")) — NOT
        # cutting_packing_warehouse (a WIP staging warehouse the item is never
        # placed in). Sourcing from the wrong warehouse means Frappe can't find
        # a valuation rate there and the whole Stock Entry fails to insert.
        wh_src = SettingsManager.get_warehouse("fg_grade_a_warehouse")

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
            cls._link_repack_se_to_roll_chain(qi_doc, se.name)
            return se.name

        except Exception:
            frappe.log_error(
                title="DESAR: Repack SE creation failed",
                message=frappe.get_traceback(),
            )
            frappe.msgprint(
                _("Repack could not be auto-created. Please create it manually."),
                indicator="orange",
            )
            return None

    @classmethod
    def _link_repack_se_to_roll_chain(cls, qi_doc, se_name: str):
        """
        Record the Repack SE on its DESAR Roll Chain row immediately, so it's
        still findable from the Production Order if the user navigates away
        before submitting it (it stays in Draft otherwise). Best-effort —
        the Repack SE already exists by this point regardless of outcome here.
        """
        try:
            roll_ticket = qi_doc.get("custom_roll_ticket")
            if not roll_ticket:
                return
            row_name = frappe.db.get_value("DESAR Roll Chain", {"roll_ticket": roll_ticket}, "name")
            if row_name:
                frappe.db.set_value("DESAR Roll Chain", row_name, "repack_se", se_name)
        except Exception:
            frappe.log_error(
                title="DESAR: Repack SE linking to Roll Chain failed",
                message=frappe.get_traceback(),
            )

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

        output_rows = []
        unaccounted_qty = 0

        for reading in grade_readings:
            qty = reading["qty"]
            if not qty:
                continue

            grade = next((g for g in grade_config if g.grade_code == reading["grade_code"]), None)
            if not grade or grade.is_scrap:
                # Scrap is disposed, not sold — consumed from source above, no valued output row.
                continue
            if not flt(grade.valuation_pct):
                frappe.throw(_(
                    "Grade {0} has no Valuation % set in DESAR Grade Configuration. "
                    "Set it above 0 before repacking — a blank or zero value would value this grade at zero."
                ).format(grade.grade_code))

            item_code = cls._derive_item_with_suffix(base_item, grade.item_suffix) if grade.item_suffix else None
            if not item_code or not frappe.db.exists("Item", item_code):
                # Item missing — this grade's qty must NOT be silently consumed
                # from source stock with no output row (that's an invisible
                # stock/valuation write-off). Pull it back out of `total`.
                unaccounted_qty += qty
                frappe.msgprint(
                    _("Item for Grade {0} not found — {1} qty excluded from Repack, "
                      "NOT consumed from stock. Fix the item and repack manually.").format(
                        grade.grade_code, qty
                    ),
                    alert=True, indicator="orange",
                )
                continue

            output_rows.append({
                "item_code":               item_code,
                "t_warehouse":             grade.target_warehouse,
                "qty":                     qty,
                "uom":                     cls._stock_uom(item_code),
                "is_finished_item":        1,
                "set_basic_rate_manually": 1,
                "basic_rate":              round(val_rate * flt(grade.valuation_pct) / 100, 2),
            })

        consumed_total = total - unaccounted_qty
        if not consumed_total:
            return [], 0

        items = [{
            "item_code":               base_item,
            "s_warehouse":             wh_src,
            "qty":                     consumed_total,
            "uom":                     cls._stock_uom(base_item),
            "set_basic_rate_manually": 1,
            "basic_rate":              val_rate,
        }] + output_rows

        return items, consumed_total

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
        Legacy grade build — hardcoded A/B, with Grade C consumed as disposed scrap.
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

        item_a, item_b = cls._resolve_grade_items_legacy(qi_doc)
        if not item_a:
            frappe.msgprint(
                _("Cannot determine Grade A item for Repack. Please create manually."),
                alert=True, indicator="orange",
            )
            return [], 0

        if grade_b and item_b and not frappe.db.exists("Item", item_b):
            frappe.msgprint(
                _("Grade B item <b>{0}</b> does not exist — {1} qty excluded from Repack, "
                  "NOT consumed from stock. Fix the item and repack manually.").format(item_b, grade_b),
                alert=True, indicator="orange",
            )
            # Missing item — don't silently consume its qty from source stock
            # with no output row (invisible stock/valuation write-off).
            total -= grade_b
            grade_b = 0
            item_b = None

        if not total:
            return [], 0

        val_rate = StockEntryRepository.get_valuation_rate(item_a, wh_src)

        items = [{
            "item_code": item_a, "s_warehouse": wh_src, "qty": total, "uom": cls._stock_uom(item_a),
            "set_basic_rate_manually": 1, "basic_rate": val_rate,
        }]

        if grade_a:
            items.append({
                "item_code": item_a, "t_warehouse": wh_a, "qty": grade_a, "uom": cls._stock_uom(item_a),
                "is_finished_item": 1, "set_basic_rate_manually": 1, "basic_rate": val_rate,
            })
        if grade_b and item_b:
            items.append({
                "item_code": item_b, "t_warehouse": wh_b, "qty": grade_b, "uom": cls._stock_uom(item_b),
                "is_finished_item": 1, "set_basic_rate_manually": 1,
                "basic_rate": round(val_rate * cls.GRADE_B_RATIO, 2),
            })
        # Grade C is disposed scrap — already counted in `total` consumed from source,
        # never a valued output row.

        return items, total

    @classmethod
    def _resolve_grade_items_legacy(cls, qi_doc) -> Tuple[Optional[str], Optional[str]]:
        item_a = cls._get_base_item(qi_doc)
        item_b = derive_grade_b_item(item_a) if item_a else None
        return item_a or None, item_b

    @classmethod
    def _build_items(
        cls,
        item_a, item_b, wh_src, wh_a, wh_b,
        total, grade_a, grade_b, val_rate
    ) -> list:
        """
        Alias for backward compatibility with existing tests.
        Called by test_roll_ticket_service.py TestRepackServiceUnit tests.
        Builds legacy A/B items directly without reading from DB.
        `total` already includes any disposed scrap qty consumed from source.
        """
        items = [{
            "item_code": item_a, "s_warehouse": wh_src, "qty": total, "uom": "Pcs",
            "set_basic_rate_manually": 1, "basic_rate": val_rate,
        }]

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
        return items
