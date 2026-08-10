import frappe
from frappe.model.document import Document
from frappe.utils import flt


class DesignMaster(Document):
    def before_insert(self):
        self._auto_fill_stages()
        self._auto_fill_defaults()

    def validate(self):
        self._compute_yarn_rates()
        self._compute_totals()
        self._resolve_finished_item()

    def _auto_fill_stages(self):
        """Copy default stage template from DESAR Settings into a new Design Master."""
        if self.stage_configuration:
            return
        settings = frappe.get_single("DESAR Settings")
        template = settings.get("default_stage_template") or []
        for row in template:
            self.append("stage_configuration", {
                "stage_seq": row.stage_seq,
                "stage_name": row.stage_name,
                "output_item": row.output_item,
                "output_qty": row.output_qty,
                "qi_required": row.qi_required,
                "qi_template": row.qi_template,
                "roll_ticket_trigger": row.roll_ticket_trigger,
                "skip_transfer": row.skip_transfer,
                "is_final_stage": row.is_final_stage,
            })

    def _auto_fill_defaults(self):
        """Fill chemical and packing defaults from DESAR Settings."""
        settings = frappe.get_single("DESAR Settings")
        defaults = {
            "branded_box_item": "default_box_item",
            "label_item": "default_label_item",
            "sticker_item": "default_sticker_item",
            "chemical_materials_qty_kg": "default_chemical_qty_kg",
        }
        for dm_field, settings_field in defaults.items():
            if not self.get(dm_field) and settings.get(settings_field):
                self.set(dm_field, settings.get(settings_field))

    def _compute_yarn_rates(self):
        """Auto-calculate Rate (Kg/Piece) = Qty (Kg) ÷ Planned Qty for all yarn rows."""
        planned = flt(self.planned_qty)
        if not planned:
            return
        for table in ("warp_yarns", "weft_yarns", "flower_yarns"):
            for row in self.get(table) or []:
                if flt(row.qty_kg):
                    row.rate_kg_per_piece = flt(row.qty_kg) / planned

    def _compute_totals(self):
        """Sum up total ends and total yarn Kg across all yarn tables."""
        total_ends = 0
        total_kg = 0.0
        for row in self.get("warp_yarns") or []:
            total_ends += (row.ends or 0)
            total_kg += flt(row.qty_kg)
        for table in ("weft_yarns", "flower_yarns"):
            for row in self.get(table) or []:
                total_kg += flt(row.qty_kg)
        self.total_warp_ends = total_ends
        self.total_yarn_kg = total_kg

    def _resolve_finished_item(self):
        """Auto-resolve the Grade A finished item code from Article + Size."""
        if not self.finished_item and self.article_name and self.default_size:
            abbr = (self.article_name or "")[:3].upper()
            candidate = f"Shemagh-{abbr}-{self.default_size}-A"
            if frappe.db.exists("Item", candidate):
                self.finished_item = candidate
                
        # Push the finished item down to the final production stage
        if self.finished_item and self.stage_configuration:
            for row in self.stage_configuration:
                if row.is_final_stage and not row.output_item:
                    row.output_item = self.finished_item
