"""Beams and rolls of a piece based Work Order."""
import frappe
from frappe import _
from frappe.utils import cint, flt


def create_beams(work_order: str, rows: list) -> list:
    """rows: [{length_m, workstation, planned_pieces, planned_rolls}]. Pieces must add up to the order qty."""
    order_qty = frappe.db.get_value("Work Order", work_order, "qty")
    if frappe.db.exists("Production Beam", {"work_order": work_order}):
        frappe.throw(_("{0} already has beams.").format(work_order))
    _check_pieces(rows, order_qty)
    return [_insert_beam(work_order, row) for row in rows]


def split_beam(beam: str, rows: list) -> list:
    """Split one beam into child beams, each on its own workstation."""
    parent = frappe.get_doc("Production Beam", beam)
    if parent.is_group:
        frappe.throw(_("{0} is already split.").format(beam))
    if frappe.db.exists("Roll Ticket", {"production_beam": beam}):
        frappe.throw(_("{0} already has rolls.").format(beam))
    _check_pieces(rows, parent.planned_pieces)
    children = [_insert_beam(parent.work_order, {**row, "parent_production_beam": beam}) for row in rows]
    parent.db_set("is_group", 1)
    return children


def leaf_beams(work_order: str) -> list:
    return frappe.get_all("Production Beam", filters={"work_order": work_order, "is_group": 0},
                          fields=["name", "workstation", "planned_pieces"], order_by="creation")


def create_rolls(beam: str, count: int) -> list:
    """Create `count` Roll Tickets for a leaf beam, splitting its pieces and length evenly."""
    beam_doc = frappe.get_doc("Production Beam", beam)
    if beam_doc.is_group:
        frappe.throw(_("Create rolls on a leaf beam, not on a split beam."))
    if cint(count) < 1:
        frappe.throw(_("Roll count must be at least 1."))
    if frappe.db.exists("Roll Ticket", {"production_beam": beam}):
        frappe.throw(_("{0} already has rolls.").format(beam))
    context = _design_context(beam_doc.work_order)
    rolls = [_insert_roll(beam_doc, number, count, context) for number in range(1, count + 1)]
    beam_doc.db_set({"planned_rolls": count, "status": "In Progress"})
    return rolls


def _check_pieces(rows: list, expected: int) -> None:
    if not rows:
        frappe.throw(_("Add at least one beam."))
    total = sum(cint(row.get("planned_pieces")) for row in rows)
    if total != cint(expected):
        frappe.throw(_("Beam pieces add up to {0}, expected {1}.").format(total, expected))


def _insert_beam(work_order: str, row: dict) -> str:
    return frappe.get_doc({
        "doctype": "Production Beam", "work_order": work_order,
        "parent_production_beam": row.get("parent_production_beam"),
        "length_m": flt(row.get("length_m")), "workstation": row.get("workstation"),
        "planned_pieces": cint(row.get("planned_pieces")), "planned_rolls": cint(row.get("planned_rolls")),
    }).insert(ignore_permissions=True).name


def _design_context(work_order: str) -> dict:
    order = frappe.db.get_value("Work Order", work_order, ["custom_design_no", "custom_article_name"], as_dict=True)
    return {"design_no": order.custom_design_no, "article_name": order.custom_article_name}


def _insert_roll(beam, number: int, count: int, context: dict) -> str:
    return frappe.get_doc({
        "doctype": "Roll Ticket", "work_order": beam.work_order, "production_beam": beam.name,
        "roll_no": number, "meters": flt(beam.length_m) / count, "machine_no": beam.workstation,
        **context,
    }).insert(ignore_permissions=True).name
