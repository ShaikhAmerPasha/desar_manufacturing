import frappe
from frappe.model.document import Document
from frappe.utils import flt


class RollTicket(Document):
    def validate(self):
        """
        v3.0: Static grade fields removed.
        Totals are now computed from stage_grades child table.
        No server-side calculation needed here.
        """
        pass
