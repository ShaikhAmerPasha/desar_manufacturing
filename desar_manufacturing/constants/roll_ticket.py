"""
DESAR Manufacturing — Roll Ticket Status Constants

v3.0: roll_status is now a Data field (free text) to support
dynamic stage names from Stage Configuration.
Status format: "In {stage_name}" for intermediate stages.
Special values: "In Grey Store" (initial), "Completed", "Rejected".
"""


class RollStatus:
    IN_GREY_STORE = "In Grey Store"
    IN_FINISHING  = "In Finishing"
    IN_PACKING    = "In Packing"
    COMPLETED     = "Completed"
    REJECTED      = "Rejected"

    # Dynamic status builder
    @staticmethod
    def in_stage(stage_name: str) -> str:
        """Build 'In {stage_name}' status for any stage."""
        return f"In {stage_name}"

    ALL = [IN_GREY_STORE, IN_FINISHING, IN_PACKING, COMPLETED]
    WIP = [IN_GREY_STORE, IN_FINISHING, IN_PACKING]
