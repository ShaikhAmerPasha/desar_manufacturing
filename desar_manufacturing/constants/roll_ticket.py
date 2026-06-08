"""
DESAR Manufacturing — Roll Ticket Status Constants
"""


class RollStatus:
    IN_GREY_STORE = "In Grey Store"
    IN_FINISHING = "In Finishing"
    IN_PACKING = "In Packing"
    COMPLETED = "Completed"

    ALL = [IN_GREY_STORE, IN_FINISHING, IN_PACKING, COMPLETED]
    WIP = [IN_GREY_STORE, IN_FINISHING, IN_PACKING]
