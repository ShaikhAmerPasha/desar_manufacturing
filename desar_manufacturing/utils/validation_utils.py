"""
DESAR Manufacturing — Validation Utilities

Pure functions only.
No database calls. No side effects. Fully unit-testable.
"""
import math
from frappe.utils import flt
from typing import Tuple, Optional


def _check_total_against_wo_qty(total: float, wo_qty: float) -> Tuple[bool, Optional[str]]:
    """Shared strict total-vs-wo_qty comparison used by both the fixed-grade
    and dynamic (N-grade) final-count checks — every piece must be accounted for."""
    total = flt(total)
    wo_qty = flt(wo_qty)

    if not total:
        # No final grades entered — this is not a final QI
        return True, None

    if not wo_qty:
        # Cannot validate without WO qty — pass silently
        return True, None

    if total > wo_qty:
        return False, (
            "Final grade total ({total}) cannot exceed manufactured qty ({wo_qty}). "
            "Check your grade counts."
        ).format(total=int(total), wo_qty=int(wo_qty))

    if total < wo_qty:
        diff = int(wo_qty - total)
        return False, (
            "Final grade total ({total}) is less than manufactured qty ({wo_qty}). "
            "{diff} piece(s) unaccounted. "
            "Add the missing piece(s) to Grade C/Scrap."
        ).format(total=int(total), wo_qty=int(wo_qty), diff=diff)

    return True, None


def validate_final_grade_counts(
    grade_a: float,
    grade_b: float,
    grade_c: float,
    wo_qty: float,
) -> Tuple[bool, Optional[str]]:
    """
    Validate that final grade counts exactly equal Work Order quantity.

    This is STRICT — the total must match exactly because every piece
    must be accounted for: Grade A, Grade B, or Scrap.

    Args:
        grade_a: Final Grade A count
        grade_b: Final Grade B count
        grade_c: Final Grade C/Scrap count
        wo_qty:  Work Order manufactured quantity

    Returns:
        (is_valid, error_message)
        is_valid=True means validation passed.
        error_message is None when valid.

    Example:
        valid, msg = validate_final_grade_counts(42, 6, 2, 50)
        # valid=True, msg=None

        valid, msg = validate_final_grade_counts(42, 6, 0, 50)
        # valid=False, msg="...2 pieces unaccounted..."
    """
    total = flt(grade_a) + flt(grade_b) + flt(grade_c)
    return _check_total_against_wo_qty(total, wo_qty)


def validate_grade_readings_total(total: float, wo_qty: float) -> Tuple[bool, Optional[str]]:
    """
    Same strict check as validate_final_grade_counts, for the dynamic
    (configurable N-grade) QI Grade Readings path where the caller has
    already summed all grade rows to a single total.
    """
    return _check_total_against_wo_qty(total, wo_qty)


def validate_estimate_reasonable(
    stage_label: str,
    grade_a: float,
    grade_b: float,
    grade_c: float,
    max_expected: int = 80,
    min_expected: int = 10,
) -> Optional[str]:
    """
    Soft check: warn if a stage's grade estimate totals seem unusual.
    Does NOT block submission — returns warning string or None.

    Args:
        stage_label: human-readable stage name for the warning message (e.g. "Grey", "Finishing")
        grade_a, grade_b, grade_c: stage grade estimates
        max_expected: Warn if total exceeds this (default 80)
        min_expected: Warn if total is below this (default 10)

    Returns:
        Warning message string, or None if counts look normal.
    """
    total = flt(grade_a) + flt(grade_b) + flt(grade_c)
    if not total:
        return None
    if total > max_expected:
        return (
            "{stage} grade total is {total} pieces — unusually high. "
            "Please verify before submitting."
        ).format(stage=stage_label, total=int(total))
    if total < min_expected:
        return (
            "{stage} grade total is {total} pieces — unusually low. "
            "Please verify before submitting."
        ).format(stage=stage_label, total=int(total))
    return None


def validate_grey_estimate_reasonable(
    grey_a: float,
    grey_b: float,
    grey_c: float,
    max_expected: int = 80,
    min_expected: int = 10,
) -> Optional[str]:
    """Soft check for Grey stage estimate totals. See validate_estimate_reasonable."""
    return validate_estimate_reasonable("Grey", grey_a, grey_b, grey_c, max_expected, min_expected)


def validate_finishing_estimate_reasonable(
    fin_a: float,
    fin_b: float,
    fin_c: float,
    max_expected: int = 80,
    min_expected: int = 10,
) -> Optional[str]:
    """Soft check for Finishing stage estimate totals. See validate_estimate_reasonable."""
    return validate_estimate_reasonable("Finishing", fin_a, fin_b, fin_c, max_expected, min_expected)


def round_up_if_needed(qty: float, must_be_whole_number: bool) -> float:
    """
    Round qty up to the next whole number when its UOM requires it.

    ERPNext's BOM-ratio MRP explosion can produce a fractional sub-assembly
    requirement (e.g. 161 pieces / 50 per roll = 3.22 rolls) with no rounding
    of its own, then hard-rejects saving a Work Order for a whole-number UOM
    with that fractional qty. Round up rather than down/nearest — under-
    provisioning a physical unit (a beam, a roll) isn't a valid option.
    """
    qty = flt(qty)
    if must_be_whole_number and qty != int(qty):
        return float(math.ceil(qty))
    return qty


def resolve_by_keyword(stage_keyword: str, mapping: dict) -> Optional[str]:
    """First mapping value whose key is a substring of stage_keyword, else None."""
    for keyword, value in mapping.items():
        if keyword in stage_keyword:
            return value
    return None


def derive_grade_b_item(grade_a_item: str) -> Optional[str]:
    """
    Derive Grade B item code from Grade A item code.
    Convention: Shemagh-VIC-60-A → Shemagh-VIC-60-B

    Args:
        grade_a_item: Grade A item code

    Returns:
        Grade B item code, or None if cannot be derived.
    """
    if not grade_a_item:
        return None
    if "-A" not in grade_a_item:
        return None
    # Replace LAST occurrence of -A with -B
    # e.g. "Shemagh-VIC-60-A" → "Shemagh-VIC-60-B"
    idx = grade_a_item.rfind("-A")
    return grade_a_item[:idx] + "-B" + grade_a_item[idx + 2:]
