"""
DESAR Manufacturing — Quality Inspection Constants

Custom field names on Quality Inspection doctype.
QI stage identifiers.
QI template names.
"""


class QIFields:
    """Custom field names on Quality Inspection."""

    # Grey stage
    GREY_A = "custom_grey_qty_a"
    GREY_B = "custom_grey_qty_b"
    GREY_C = "custom_grey_qty_c"

    # Finishing stage
    FIN_A = "custom_finished_qty_a"
    FIN_B = "custom_finished_qty_b"
    FIN_C = "custom_finished_qty_c"

    # Final (packing) stage
    FINAL_A = "custom_cutted_qty_a"
    FINAL_B = "custom_cutted_qty_b"
    FINAL_C = "custom_cutted_qty_c"


class QIStage:
    """QI stage identifiers — used internally."""
    GREY = "grey"
    FINISHING = "finishing"
    FINAL = "final"
    UNKNOWN = "unknown"


class QITemplates:
    """QI template names in ERPNext."""
    GREY = "Grey Inspection - Shemagh"
    FINISHING = "Finishing Inspection - Shemagh"
    FINAL = "Final Packing Inspection - Shemagh"
