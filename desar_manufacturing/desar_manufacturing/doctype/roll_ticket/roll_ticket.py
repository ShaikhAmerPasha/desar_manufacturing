import frappe
from frappe.model.document import Document
from frappe.utils import flt


class RollTicket(Document):
    def validate(self):
        self._calc_totals()

    def _calc_totals(self):
        self.grey_total = flt(self.grey_qty_a) + flt(self.grey_qty_b) + flt(self.grey_qty_c)
        self.finished_total = flt(self.finished_qty_a) + flt(self.finished_qty_b) + flt(self.finished_qty_c)
        self.cutted_total = flt(self.cutted_qty_a) + flt(self.cutted_qty_b) + flt(self.cutted_qty_c)
