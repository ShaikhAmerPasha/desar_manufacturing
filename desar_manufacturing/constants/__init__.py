"""
DESAR Manufacturing Constants
Import from here for clean code.

Usage:
    from desar_manufacturing.constants import GREY_ROLL, RollStatus, QIFields
"""
from desar_manufacturing.constants.items import (
    WARPING_BEAM,
    GREY_ROLL,
    FINISHED_ROLL,
    CHEMICAL_MATERIALS,
    SHEMAGH_SCRAP,
    GRADE_A_SUFFIX,
    GRADE_B_SUFFIX,
)
from desar_manufacturing.constants.roll_ticket import RollStatus
from desar_manufacturing.constants.quality_inspection import QIFields, QIStage, QITemplates
from desar_manufacturing.constants.roles import (
    ALL_DESAR_ROLES,
    SUPERVISOR_ROLES,
    JOB_CARD_ROLES,
    QC_ROLES,
    STORE_ROLES,
)

__all__ = [
    "WARPING_BEAM",
    "GREY_ROLL",
    "FINISHED_ROLL",
    "CHEMICAL_MATERIALS",
    "SHEMAGH_SCRAP",
    "GRADE_A_SUFFIX",
    "GRADE_B_SUFFIX",
    "RollStatus",
    "QIFields",
    "QIStage",
    "QITemplates",
    "ALL_DESAR_ROLES",
    "SUPERVISOR_ROLES",
    "JOB_CARD_ROLES",
    "QC_ROLES",
    "STORE_ROLES",
]
