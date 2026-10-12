"""Pure grade arithmetic for Roll Inspection. No database access."""


class GradeMovementError(ValueError):
    pass


def apply_movements(opening: dict, movements: list) -> dict:
    """Return closing counts after moving pieces between grades.

    opening: {grade_code: qty}. movements: [{"from_grade", "to_grade", "qty"}].
    """
    closing = dict(opening)
    for move in movements:
        _apply_one_movement(closing, move)
    return closing


def _apply_one_movement(counts: dict, move: dict) -> None:
    source, target, qty = move["from_grade"], move["to_grade"], move["qty"]
    if qty <= 0:
        raise GradeMovementError("Movement quantity must be greater than zero.")
    if source == target:
        raise GradeMovementError("From grade and to grade cannot be the same.")
    if counts.get(source, 0) < qty:
        raise GradeMovementError(
            f"Cannot move {qty} from grade {source}: only {counts.get(source, 0)} available."
        )
    counts[source] -= qty
    counts[target] = counts.get(target, 0) + qty


def apply_adjustments(counts: dict, adjustments: list) -> dict:
    """Apply signed per-grade changes (process loss is negative, count gain positive)."""
    result = dict(counts)
    for adjustment in adjustments:
        grade, change = adjustment["grade_code"], adjustment["qty"]
        result[grade] = result.get(grade, 0) + change
        if result[grade] < 0:
            raise GradeMovementError(f"Adjustment makes grade {grade} negative.")
    return result


def derive_adjustments(expected: dict, real: dict) -> list:
    """Per-grade difference between real counts and expected counts, non-zero only."""
    grades = sorted(set(expected) | set(real))
    return [
        {"grade_code": grade, "qty": real.get(grade, 0) - expected.get(grade, 0)}
        for grade in grades
        if real.get(grade, 0) != expected.get(grade, 0)
    ]


def total(counts: dict) -> int:
    return sum(counts.values())
