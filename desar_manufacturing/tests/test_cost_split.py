import unittest

from desar_manufacturing.utils.cost_split import split_cost


class TestCostSplit(unittest.TestCase):
    def test_b_grade_at_sixty_percent_and_scrap_free(self):
        rates = split_cost(1000, {"A": 80, "B": 10, "C": 10}, {"A": 1.0, "B": 0.6, "C": 0.0})
        self.assertAlmostEqual(rates["A"], 1000 / 86, places=4)
        self.assertAlmostEqual(rates["B"], 0.6 * 1000 / 86, places=4)
        self.assertEqual(rates["C"], 0.0)

    def test_total_value_equals_total_cost(self):
        quantities = {"A": 80, "B": 10, "C": 10}
        rates = split_cost(1000, quantities, {"A": 1.0, "B": 0.6, "C": 0.0})
        value = sum(quantities[grade] * rates[grade] for grade in quantities)
        self.assertAlmostEqual(value, 1000, places=2)

    def test_all_scrap_gives_zero_rates(self):
        self.assertEqual(split_cost(500, {"C": 5}, {"C": 0.0}), {"C": 0.0})
