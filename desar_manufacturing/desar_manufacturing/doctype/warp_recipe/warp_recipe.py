import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class WarpRecipe(Document):
    def validate(self):
        self._apply_rate_based_qty()
        self._count_ends()
        self._warn_duplicate_rows()
        self.total_yarn_kg = sum(flt(row.qty_kg) for row in self.yarn_items)

    def _apply_rate_based_qty(self):
        """Rows with a Rate (Kg/Piece) set get their Qty (Kg) auto-derived
        from Planned Qty. Rows without a rate keep their typed Qty (Kg)."""
        for row in self.yarn_items:
            if flt(row.rate_kg_per_piece):
                row.qty_kg = flt(row.rate_kg_per_piece) * flt(self.planned_qty)

    def _count_ends(self):
        for row in self.yarn_items:
            row.row_total_ends = cint(row.ends) * max(cint(row.block_repeats), 1)
        self.total_ends = sum(row.row_total_ends for row in self.yarn_items)

    def _warn_duplicate_rows(self):
        seen = set()
        for row in self.yarn_items:
            key = (row.yarn_item, row.color, row.kind, row.sequence, row.ends)
            if key in seen:
                frappe.msgprint(_("Row {0} repeats an earlier row for {1}.").format(row.idx, row.yarn_item),
                                alert=True, indicator="orange")
            seen.add(key)
