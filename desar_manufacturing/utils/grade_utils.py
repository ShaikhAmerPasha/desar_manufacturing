import frappe
from frappe.utils import flt


def get_final_stage_names() -> list:
    """
    Stage names, across every Design Master, flagged as the final production
    stage. Intentionally unscoped — used by reports (e.g. roll_life_tracker)
    that classify stages across many orders/Design Masters at once. For a
    single record's final-stage check, use is_final_stage(), which is scoped.
    """
    return list(set(frappe.get_all(
        "DESAR Stage Configuration",
        filters={"is_final_stage": 1},
        pluck="stage_name",
    )))


def is_final_stage(stage_name: str, design_master: str) -> bool:
    """
    Whether `stage_name` is the final stage for THIS Design Master.

    Must be scoped by design_master: stage names repeat across Design
    Masters with different configs (e.g. some legacy Design Masters flag
    "Grey Roll" as final, others flag "Packing"). An unscoped stage_name-only
    lookup would match the first Design Master in the system that happens to
    flag that name, regardless of what the current record's own Design
    Master says — that was a real bug (grade-total validation firing on the
    wrong stage because another Design Master's config leaked in).
    """
    if not stage_name or not design_master:
        return False
    return bool(frappe.db.get_value(
        "DESAR Stage Configuration",
        {"parent": design_master, "stage_name": stage_name, "is_final_stage": 1},
        "name",
    ))


def get_work_order_from_qi(qi_doc) -> str:
    """Resolve the Work Order behind a QI's reference Stock Entry, if any."""
    if qi_doc.get("reference_type") == "Stock Entry" and qi_doc.get("reference_name"):
        return frappe.db.get_value("Stock Entry", qi_doc.get("reference_name"), "work_order") or ""
    return ""


def get_design_master_from_qi(qi_doc) -> str:
    """Resolve the Design Master a QI's stage belongs to, via its reference
    Stock Entry -> Work Order -> custom_design_master."""
    wo_name = get_work_order_from_qi(qi_doc)
    if not wo_name:
        return ""
    return frappe.db.get_value("Work Order", wo_name, "custom_design_master") or ""


def get_stage_grades(roll_ticket: str, stage_name: str) -> dict:
    """{grade_code: qty} for one roll ticket's stage_grades rows at the given stage."""
    rows = frappe.get_all(
        "DESAR Roll Ticket Stage Grade",
        filters={"parent": roll_ticket, "stage_name": stage_name},
        fields=["grade_code", "qty"],
    )
    return {r.grade_code: flt(r.qty) for r in rows}


def get_stage_grades_from_rt(roll_ticket: str, stage_name_pattern: str) -> dict:
    """
    {grade_code: qty} for a roll ticket's stage matching `stage_name_pattern`
    (LIKE match, e.g. "Finish") — resolves the actual stage name first since
    dynamic Stage Configuration names vary (e.g. "Finishing", "Chemical Finish").
    """
    actual_stage = frappe.db.get_value(
        "DESAR Roll Ticket Stage Grade",
        {"parent": roll_ticket, "stage_name": ["like", f"%{stage_name_pattern}%"]},
        "stage_name",
    )
    if not actual_stage:
        return {}
    return get_stage_grades(roll_ticket, actual_stage)
