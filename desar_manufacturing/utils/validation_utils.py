"""
DESAR Manufacturing — Validation Utilities

Pure functions only.
No database calls. No side effects. Fully unit-testable.
"""
from frappe.utils import flt
from typing import Tuple, Optional


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
            "Check your Grade A / B / C counts."
        ).format(total=int(total), wo_qty=int(wo_qty))

    if total < wo_qty:
        diff = int(wo_qty - total)
        return False, (
            "Final grade total ({total}) is less than manufactured qty ({wo_qty}). "
            "{diff} piece(s) unaccounted. "
            "Add the missing piece(s) to Grade C/Scrap."
        ).format(total=int(total), wo_qty=int(wo_qty), diff=diff)

    return True, None


def validate_grey_estimate_reasonable(
    grey_a: float,
    grey_b: float,
    grey_c: float,
    max_expected: int = 80,
    min_expected: int = 10,
) -> Optional[str]:
    """
    Soft check: warn if grey estimate totals seem unusual.
    Does NOT block submission — returns warning string or None.

    Args:
        grey_a, grey_b, grey_c: Grey stage grade estimates
        max_expected: Warn if total exceeds this (default 80)
        min_expected: Warn if total is below this (default 10)

    Returns:
        Warning message string, or None if counts look normal.
    """
    total = flt(grey_a) + flt(grey_b) + flt(grey_c)
    if not total:
        return None
    if total > max_expected:
        return (
            "Grey grade total is {total} pieces — unusually high. "
            "Please verify before submitting."
        ).format(total=int(total))
    if total < min_expected:
        return (
            "Grey grade total is {total} pieces — unusually low. "
            "Please verify before submitting."
        ).format(total=int(total))
    return None


def validate_finishing_estimate_reasonable(
    fin_a: float,
    fin_b: float,
    fin_c: float,
    max_expected: int = 80,
    min_expected: int = 10,
) -> Optional[str]:
    """Same as grey estimate validation but for finishing stage."""
    total = flt(fin_a) + flt(fin_b) + flt(fin_c)
    if not total:
        return None
    if total > max_expected:
        return (
            "Finishing grade total is {total} pieces — unusually high. "
            "Please verify before submitting."
        ).format(total=int(total))
    if total < min_expected:
        return (
            "Finishing grade total is {total} pieces — unusually low. "
            "Please verify before submitting."
        ).format(total=int(total))
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
