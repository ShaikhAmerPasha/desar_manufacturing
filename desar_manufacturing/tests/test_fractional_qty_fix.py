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


class TestSubAssemblyWarehouseAutofill(unittest.TestCase):
	"""Get Sub Assembly Items only fills fg_warehouse when the whole
	Production Plan has one uniform Sub Assembly Warehouse set — doesn't fit
	a multi-stage flow where each item belongs in a different warehouse."""

	def test_known_item_gets_its_warehouse(self):
		row = MagicMock(production_item="Warping Beam", fg_warehouse=None)
		with patch("frappe.db.get_single_value", return_value="Warping WIP - ST"):
			production_plan._autofill_sub_assembly_warehouse(row)
		self.assertEqual(row.fg_warehouse, "Warping WIP - ST")

	def test_each_item_maps_to_its_own_warehouse(self):
		cases = [
			("Warping Beam", "warping_wip_warehouse"),
			("Beam Roll", "warping_wip_warehouse"),
			("Grey Roll", "loom_floor_warehouse"),
			("Finished Roll", "finishing_wip_warehouse"),
		]
		for item, expected_field in cases:
			row = MagicMock(production_item=item, fg_warehouse=None)
			with patch("frappe.db.get_single_value") as mock_get:
				mock_get.return_value = "SOME-WH"
				production_plan._autofill_sub_assembly_warehouse(row)
				mock_get.assert_called_once_with("DESAR Settings", expected_field)

	def test_stale_or_wrong_warehouse_gets_overridden(self):
		"""Item Default/core fallback can leave a non-blank but wrong
		warehouse here — there's exactly one correct answer for these
		4 shared WIP items, so it must be overridden, not left alone."""
		row = MagicMock(production_item="Grey Roll", fg_warehouse="Stores - ST")
		with patch("frappe.db.get_single_value", return_value="Loom Floor - ST"):
			production_plan._autofill_sub_assembly_warehouse(row)
		self.assertEqual(row.fg_warehouse, "Loom Floor - ST")

	def test_unknown_item_left_blank(self):
		row = MagicMock(production_item="Shemagh-VIC-60-A", fg_warehouse=None)
		production_plan._autofill_sub_assembly_warehouse(row)
		self.assertIsNone(row.fg_warehouse)

	def test_unconfigured_warehouse_leaves_row_blank(self):
		row = MagicMock(production_item="Grey Roll", fg_warehouse=None)
		with patch("frappe.db.get_single_value", return_value=None):
			production_plan._autofill_sub_assembly_warehouse(row)
		self.assertIsNone(row.fg_warehouse)


def _skip_design_context_autofill(test_case):
	"""These tests exercise qty-rounding only. before_validate now also
	calls design-context/warehouse/skip_transfer autofill (needed so it
	survives Production Plan's ignore_validate=True bulk creation — see
	events/work_order.py) — stub those out here so a bare MagicMock doc
	doesn't trigger real (harmlessly-caught, but noisy) DB queries."""
	for name in ("_autofill_design_context", "_autofill_warehouses", "_apply_skip_transfer"):
		patcher = patch.object(work_order, name)
		patcher.start()
		test_case.addCleanup(patcher.stop)


class TestWorkOrderBeforeInsertRoundsQty(unittest.TestCase):
	def setUp(self):
		_skip_design_context_autofill(self)

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

	def setUp(self):
		_skip_design_context_autofill(self)

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

	def setUp(self):
		_skip_design_context_autofill(self)

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
