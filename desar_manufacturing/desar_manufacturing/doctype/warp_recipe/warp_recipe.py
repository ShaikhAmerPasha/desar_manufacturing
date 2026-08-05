import frappe
from frappe.model.document import Document
from frappe.utils import flt


class WarpRecipe(Document):
    def validate(self):
        self._apply_rate_based_qty()
        self.total_yarn_kg = sum(flt(row.qty_kg) for row in self.yarn_items)

    def _apply_rate_based_qty(self):
        """Rows with a Rate (Kg/Piece) set get their Qty (Kg) auto-derived
        from Planned Qty. Rows without a rate keep their typed Qty (Kg)."""
        for row in self.yarn_items:
            if flt(row.rate_kg_per_piece):
                row.qty_kg = flt(row.rate_kg_per_piece) * flt(self.planned_qty)
