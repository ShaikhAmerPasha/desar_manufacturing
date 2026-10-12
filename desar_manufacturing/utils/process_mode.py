import frappe

PIECE_BASED = "Piece Based"


def is_piece_based_design(design_master) -> bool:
    if not design_master:
        return False
    return frappe.get_cached_value("Design Master", design_master, "process_version") == PIECE_BASED
