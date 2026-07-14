"""
Fractional sub-assembly qty fix — real hook functions, not reimplementations.

Reproduces the user's reported bug: Production Plan MRP explosion computes
a fractional sub-assembly qty (e.g. 161/50=3.22) for a whole-number-UOM
item, which used to make ERPNext reject the Work Order on save.
"""
import unittest
from unittest.mock import patch, MagicMock

from desar_manufacturing.events import production_plan, work_order


class TestProductionPlanRoundsSubAssemblyQty(unittest.TestCase):
	def test_fractional_row_rounded_up(self):
		row = MagicMock(stock_uom="Nos", qty=3.22)
		doc = MagicMock()
		doc.get.return_value = [row]

		with patch("frappe.get_cached_value", return_value=1):
			production_plan.validate(doc)

		self.assertEqual(row.qty, 4.0)

	def test_non_whole_number_uom_untouched(self):
		row = MagicMock(stock_uom="Kg", qty=3.22)
		doc = MagicMock()
		doc.get.return_value = [row]

		with patch("frappe.get_cached_value", return_value=0):
			production_plan.validate(doc)

		self.assertEqual(row.qty, 3.22)

	def test_no_rows_does_not_error(self):
		doc = MagicMock()
		doc.get.return_value = []
		production_plan.validate(doc)  # must not raise


class TestWorkOrderBeforeInsertRoundsQty(unittest.TestCase):
	def test_fractional_qty_rounded_up_before_validate_qty_can_reject_it(self):
		doc = MagicMock(stock_uom="Nos", qty=3.22)

		with patch("frappe.get_cached_value", return_value=1):
			work_order.before_insert(doc)

		self.assertEqual(doc.qty, 4.0)

	def test_whole_qty_unchanged(self):
		doc = MagicMock(stock_uom="Nos", qty=4.0)

		with patch("frappe.get_cached_value", return_value=1):
			work_order.before_insert(doc)

		self.assertEqual(doc.qty, 4.0)

	def test_missing_stock_uom_does_not_error(self):
		doc = MagicMock(stock_uom=None, qty=3.22)
		work_order.before_insert(doc)  # must not raise, must not touch qty
		self.assertEqual(doc.qty, 3.22)


class TestWorkOrderBeforeInsertRoundsRequiredItemsQty(unittest.TestCase):
	"""
	Reproduces the beam-split bug: cloning a Work Order to a smaller qty
	then calling set_required_items() (warping_service._clone_combined_wo)
	can leave a fractional required_qty on a required_items row even when
	the WO's own qty is a whole number.
	"""

	def test_fractional_required_qty_rounded_up(self):
		row = MagicMock(stock_uom="Nos", required_qty=1.6)
		doc = MagicMock(stock_uom="Nos", qty=1)
		doc.get.return_value = [row]

		with patch("frappe.get_cached_value", return_value=1):
			work_order.before_insert(doc)

		self.assertEqual(row.required_qty, 2.0)

	def test_non_whole_number_uom_row_untouched(self):
		row = MagicMock(stock_uom="Kg", required_qty=1.6)
		doc = MagicMock(stock_uom="Nos", qty=1)
		doc.get.return_value = [row]

		with patch("frappe.get_cached_value", return_value=0):
			work_order.before_insert(doc)

		self.assertEqual(row.required_qty, 1.6)

	def test_no_required_items_does_not_error(self):
		doc = MagicMock(stock_uom="Nos", qty=1)
		doc.get.return_value = []

		with patch("frappe.get_cached_value", return_value=1):
			work_order.before_insert(doc)  # must not raise


class TestWorkOrderBeforeValidateAlsoRounds(unittest.TestCase):
	"""
	Reproduces the resize-on-save bug: warping_service._resize_packing_wo
	resizes an already-inserted draft Work Order via .save(), which never
	fires before_insert again — before_validate must catch this case too,
	since it fires on every save/submit, not just insert.
	"""

	def test_before_validate_rounds_required_items_on_existing_doc_save(self):
		row = MagicMock(stock_uom="Nos", required_qty=1.62)
		doc = MagicMock(stock_uom="Nos", qty=81)
		doc.get.return_value = [row]

		with patch("frappe.get_cached_value", return_value=1):
			work_order.before_validate(doc)

		self.assertEqual(row.required_qty, 2.0)

	def test_before_insert_delegates_to_before_validate(self):
		row = MagicMock(stock_uom="Nos", required_qty=1.62)
		doc = MagicMock(stock_uom="Nos", qty=81)
		doc.get.return_value = [row]

		with patch("frappe.get_cached_value", return_value=1):
			work_order.before_insert(doc)

		self.assertEqual(row.required_qty, 2.0)
