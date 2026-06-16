"""
DESAR Manufacturing — Quality Inspection Constants

NOTE: As of v3.0, the dynamic grade system replaces fixed fields.
QIFields, QIStage, QITemplates are kept for legacy fallback only.
Active systems use DESAR Grade Configuration + Stage Configuration.
"""


class QIFields:
    """
    Legacy fixed field names on Quality Inspection.
    Used only when DESAR Grade Configuration is NOT set up.
    """
    GREY_A = "custom_grey_qty_a"
    GREY_B = "custom_grey_qty_b"
    GREY_C = "custom_grey_qty_c"
    FIN_A  = "custom_finished_qty_a"
    FIN_B  = "custom_finished_qty_b"
    FIN_C  = "custom_finished_qty_c"
    FINAL_A = "custom_cutted_qty_a"
    FINAL_B = "custom_cutted_qty_b"
    FINAL_C = "custom_cutted_qty_c"


class QIStage:
    """Legacy QI stage identifiers."""
    GREY      = "grey"
    FINISHING = "finishing"
    FINAL     = "final"
    UNKNOWN   = "unknown"


class QITemplates:
    """Legacy QI template names — used as fallback when Stage Configuration empty."""
    GREY      = "Grey Inspection - Shemagh"
    FINISHING = "Finishing Inspection - Shemagh"
    FINAL     = "Final Packing Inspection - Shemagh"
