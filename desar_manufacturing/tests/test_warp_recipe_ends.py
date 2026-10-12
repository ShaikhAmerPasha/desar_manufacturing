import frappe
from frappe.tests.utils import FrappeTestCase


def make_recipe(rows: list, **values):
    return frappe.get_doc({"doctype": "Warp Recipe", "recipe_name": "TEST-ENDS", "yarn_items": rows, **values})


class TestWarpRecipeEnds(FrappeTestCase):
    def test_total_ends_counts_blocks_and_repeats(self):
        recipe = make_recipe([
            {"yarn_item": "x", "kind": "Selvedge", "ends": 36, "block_repeats": 1},
            {"yarn_item": "x", "kind": "Body", "ends": 72, "block_repeats": 3},
            {"yarn_item": "x", "kind": "Flower", "ends": 10, "block_repeats": 2},
        ])
        recipe.validate()
        self.assertEqual([row.row_total_ends for row in recipe.yarn_items], [36, 216, 20])
        self.assertEqual(recipe.total_ends, 272)

    def test_blank_repeats_count_once(self):
        recipe = make_recipe([{"yarn_item": "x", "ends": 96, "block_repeats": 0}])
        recipe.validate()
        self.assertEqual(recipe.total_ends, 96)

    def test_existing_rate_based_quantity_still_works(self):
        recipe = make_recipe([{"yarn_item": "x", "rate_kg_per_piece": 0.2, "ends": 10}], planned_qty=100)
        recipe.validate()
        self.assertEqual((recipe.yarn_items[0].qty_kg, recipe.total_yarn_kg), (20, 20))

    def test_total_matches_paper_work_order(self):
        blocks = [36, 96, 228, 2474, 96, 96, 112, 80]
        recipe = make_recipe([{"yarn_item": "x", "ends": ends} for ends in blocks])
        recipe.validate()
        self.assertEqual(recipe.total_ends, sum(blocks))
