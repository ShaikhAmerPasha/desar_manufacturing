"""Roll Inspection rules: opening counts, grade movements, closing counts."""
import frappe
from frappe import _

from desar_manufacturing.config.settings_manager import SettingsManager
from desar_manufacturing.utils.grade_movement import (
    GradeMovementError,
    apply_adjustments,
    apply_movements,
    derive_adjustments,
    total,
)

COUNT = "Count"
MOVEMENT = "Movement"
REAL_COUNT = "Real Count"


def configured_grades() -> list:
    grades = SettingsManager.get_grade_configuration()
    if not grades:
        frappe.throw(_("Configure grades in DESAR Settings, Grade Configuration."))
    best_first = sorted(grades, key=lambda grade: (-(grade.valuation_pct or 0), grade.grade_code))
    return [(grade.grade_code, grade.grade_label or grade.grade_code) for grade in best_first]


def counts_of(rows) -> dict:
    return {row.grade_code: int(row.qty or 0) for row in rows}


def fill_grade_rows(doc, table_field: str, counts: dict) -> None:
    doc.set(table_field, [])
    for code, label in configured_grades():
        doc.append(table_field, {"grade_code": code, "grade_label": label, "qty": counts.get(code, 0)})


def previous_closing(roll_ticket: str, sequence: int):
    """Closing counts of the latest submitted inspection before this sequence, or None."""
    rows = frappe.get_all(
        "Roll Inspection",
        filters={"roll_ticket": roll_ticket, "docstatus": 1},
        fields=["name", "stage"],
    )
    earlier = []
    for row in rows:
        row_sequence = frappe.db.get_value("Inspection Stage", row.stage, "sequence")
        if row_sequence < sequence:
            earlier.append((row_sequence, row.name))
    if not earlier:
        return None
    name = max(earlier)[1]
    return counts_of(frappe.get_doc("Roll Inspection", name).closing)


def prepare(doc) -> None:
    """Fill opening and ensure closing rows exist. Runs on every validate."""
    stage = frappe.get_cached_doc("Inspection Stage", doc.stage)
    if stage.entry_mode == COUNT:
        _prepare_count_mode(doc)
        return
    opening = previous_closing(doc.roll_ticket, stage.sequence)
    if opening is None:
        frappe.throw(_("Submit the previous inspection for this roll first."))
    fill_grade_rows(doc, "opening", opening)
    if not doc.closing:
        fill_grade_rows(doc, "closing", opening)


def _prepare_count_mode(doc) -> None:
    if doc.movements or doc.adjustments:
        frappe.throw(_("{0} takes counts only. Remove movement and difference rows.").format(doc.stage))
    doc.set("opening", [])
    if not doc.closing:
        fill_grade_rows(doc, "closing", {})


def calculate(doc) -> None:
    """Compute closing counts or loss rows from the entry mode."""
    stage = frappe.get_cached_doc("Inspection Stage", doc.stage)
    try:
        if stage.entry_mode == MOVEMENT:
            _calculate_movement_mode(doc)
        elif stage.entry_mode == REAL_COUNT:
            _calculate_real_count_mode(doc)
    except GradeMovementError as error:
        frappe.throw(_(str(error)))
    doc.total_pieces = total(counts_of(doc.closing))


def _movement_rows(doc) -> list:
    return [
        {"from_grade": row.from_grade, "to_grade": row.to_grade, "qty": int(row.qty or 0)}
        for row in doc.movements
    ]


def _calculate_movement_mode(doc) -> None:
    expected = apply_movements(counts_of(doc.opening), _movement_rows(doc))
    adjustments = [{"grade_code": row.grade_code, "qty": int(row.qty or 0)} for row in doc.adjustments]
    closing = apply_adjustments(expected, adjustments)
    fill_grade_rows(doc, "closing", closing)


def _calculate_real_count_mode(doc) -> None:
    expected = apply_movements(counts_of(doc.opening), _movement_rows(doc))
    differences = derive_adjustments(expected, counts_of(doc.closing))
    reasons = {row.grade_code: row.reason for row in doc.adjustments}
    doc.set("adjustments", [])
    for difference in differences:
        doc.append("adjustments", {**difference, "reason": reasons.get(difference["grade_code"])})


def require_reasons(doc) -> None:
    for row in doc.movements:
        _check_reason(row.reason, "Movement", row.idx)
    for row in doc.adjustments:
        _check_reason(row.reason, "Loss" if row.qty < 0 else "Count Gain", row.idx)


def _check_reason(reason, kind: str, row_number: int) -> None:
    if not reason:
        frappe.throw(_("Row {0}: reason is required.").format(row_number))
    reason_kind = frappe.db.get_value("Inspection Reason", reason, "kind")
    if reason_kind != kind:
        frappe.throw(_("Row {0}: reason {1} is not valid for {2}.").format(row_number, reason, kind))


def ensure_unique(doc) -> None:
    existing = frappe.db.exists(
        "Roll Inspection",
        {"roll_ticket": doc.roll_ticket, "stage": doc.stage, "docstatus": 1, "name": ["!=", doc.name]},
    )
    if existing:
        frappe.throw(_("{0} already has a submitted {1} inspection: {2}.").format(
            doc.roll_ticket, doc.stage, existing))


def publish_to_roll_ticket(doc) -> None:
    stage = frappe.get_cached_doc("Inspection Stage", doc.stage)
    roll_ticket = frappe.get_doc("Roll Ticket", doc.roll_ticket)
    for row in doc.closing:
        roll_ticket.append("stage_grades", {
            "stage_seq": stage.sequence, "stage_name": doc.stage,
            "grade_code": row.grade_code, "grade_label": row.grade_label,
            "qty": row.qty, "roll_inspection": doc.name,
        })
    roll_ticket.save(ignore_permissions=True)


def withdraw_from_roll_ticket(doc) -> None:
    sequence = frappe.db.get_value("Inspection Stage", doc.stage, "sequence")
    later = [
        name for name in frappe.get_all(
            "Roll Inspection", {"roll_ticket": doc.roll_ticket, "docstatus": 1}, pluck="name")
        if frappe.db.get_value("Inspection Stage", frappe.db.get_value("Roll Inspection", name, "stage"),
                               "sequence") > sequence
    ]
    if later:
        frappe.throw(_("Cancel later inspection {0} first.").format(later[0]))
    roll_ticket = frappe.get_doc("Roll Ticket", doc.roll_ticket)
    roll_ticket.set("stage_grades", [r for r in roll_ticket.stage_grades if r.roll_inspection != doc.name])
    roll_ticket.save(ignore_permissions=True)


@frappe.whitelist()
def get_grade_rows(roll_ticket: str, stage: str) -> dict:
    """Opening and starting closing rows for the form, before the first save."""
    frappe.has_permission("Roll Inspection", "create", throw=True)
    stage_doc = frappe.get_cached_doc("Inspection Stage", stage)
    opening = None if stage_doc.entry_mode == COUNT else previous_closing(roll_ticket, stage_doc.sequence)
    if opening is None and stage_doc.entry_mode != COUNT:
        frappe.throw(_("Submit the previous inspection for this roll first."))
    labels = dict(configured_grades())
    rows = lambda counts: [{"grade_code": code, "grade_label": labels[code], "qty": counts.get(code, 0)}
                           for code in labels]
    return {"opening": rows(opening) if opening is not None else [], "closing": rows(opening or {})}
