"""
Warp Recipe — rate-based Qty (Kg) calculation.

Builds a real in-memory Warp Recipe doc (frappe.new_doc, never inserted)
and calls its actual validate() — not a reimplementation.
"""
import unittest

import frappe


def _recipe(planned_qty, rows):
    doc = frappe.new_doc("Warp Recipe")
    doc.recipe_name = "TEST-WR"
    doc.planned_qty = planned_qty
    for row in rows:
        doc.append("yarn_items", row)
    return doc


class TestRateBasedQty(unittest.TestCase):
    def test_rate_row_derives_qty_kg_from_planned_qty(self):
        recipe = _recipe(575, [{"yarn_item": "Yarn-A", "rate_kg_per_piece": 0.1739130435, "qty_kg": 0}])
        recipe.validate()
        self.assertAlmostEqual(recipe.yarn_items[0].qty_kg, 100.0, places=3)

    def test_row_without_rate_keeps_typed_qty_kg(self):
        recipe = _recipe(575, [{"yarn_item": "Yarn-A", "rate_kg_per_piece": 0, "qty_kg": 42}])
        recipe.validate()
        self.assertEqual(recipe.yarn_items[0].qty_kg, 42)

    def test_total_yarn_kg_sums_all_rows(self):
        recipe = _recipe(575, [
            {"yarn_item": "Yarn-A", "rate_kg_per_piece": 0.1739130435, "qty_kg": 0},
            {"yarn_item": "Yarn-B", "rate_kg_per_piece": 0, "qty_kg": 66.67},
        ])
        recipe.validate()
        self.assertAlmostEqual(recipe.total_yarn_kg, 166.67, places=2)

    def test_mixed_rate_and_manual_rows(self):
        recipe = _recipe(230, [
            {"yarn_item": "Yarn-A", "rate_kg_per_piece": 0.434782609, "qty_kg": 0},
            {"yarn_item": "Yarn-B", "rate_kg_per_piece": 0, "qty_kg": 12.5},
        ])
        recipe.validate()
        self.assertAlmostEqual(recipe.yarn_items[0].qty_kg, 100.0, places=2)
        self.assertEqual(recipe.yarn_items[1].qty_kg, 12.5)
