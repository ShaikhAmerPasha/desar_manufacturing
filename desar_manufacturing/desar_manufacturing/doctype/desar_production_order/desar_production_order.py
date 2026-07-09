"""
DESAR Production Order v6 Controller

Single-document multi-roll architecture.
All roll chains tracked within one document per Sales Order line.
"""
import frappe
from frappe.model.document import Document


class DESARProductionOrder(Document):

	def before_submit(self):
		self.status = "Submitted"

	def on_cancel(self):
		self.status = "Cancelled"

	def validate(self):
		if self.design_master and not self.article_name:
			dm = frappe.get_cached_doc("Design Master", self.design_master)
			self.article_name = dm.article_name
			self.design_no = dm.design_no
