"""Split a pooled production cost across grades by valuation weight. No database access."""


def split_cost(total_cost: float, quantities: dict, weights: dict) -> dict:
    """Return {grade: rate per piece}. A grade with weight 0 gets rate 0.

    Rate of grade g = weight[g] * base_rate, where
    base_rate = total_cost / sum(quantity[g] * weight[g]).
    """
    weighted_pieces = sum(quantities.get(grade, 0) * weights.get(grade, 0) for grade in quantities)
    if weighted_pieces <= 0:
        return {grade: 0.0 for grade in quantities}
    base_rate = total_cost / weighted_pieces
    return {grade: round(weights.get(grade, 0) * base_rate, 6) for grade in quantities}
