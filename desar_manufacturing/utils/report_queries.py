"""Shared SQL for the piece based reports. Only submitted Roll Inspections count."""
import frappe


def final_grade_rows(work_order: str = None, sales_order: str = None) -> list:
    """One row per roll and grade: work_order, roll_ticket, grade_code, qty (final inspection closing)."""
    return frappe.db.sql(
        """select ri.work_order, ri.roll_ticket, g.grade_code, g.qty
        from `tabRoll Inspection` ri
        join `tabInspection Stage` st on st.name = ri.stage and st.is_final = 1
        join `tabDESAR QI Grade Reading` g
          on g.parent = ri.name and g.parenttype = 'Roll Inspection' and g.parentfield = 'closing'
        left join `tabWork Order` wo on wo.name = ri.work_order
        where ri.docstatus = 1
          and (%(work_order)s is null or ri.work_order = %(work_order)s)
          and (%(sales_order)s is null or wo.sales_order = %(sales_order)s)""",
        {"work_order": work_order, "sales_order": sales_order}, as_dict=True)


def movement_rows(work_order: str = None) -> list:
    return frappe.db.sql(
        """select ri.work_order, ri.roll_ticket, ri.stage, m.from_grade, m.to_grade, m.qty, m.reason
        from `tabRoll Inspection Movement` m
        join `tabRoll Inspection` ri on ri.name = m.parent
        where ri.docstatus = 1 and (%(work_order)s is null or ri.work_order = %(work_order)s)""",
        {"work_order": work_order}, as_dict=True)


def adjustment_rows(work_order: str = None) -> list:
    return frappe.db.sql(
        """select ri.work_order, ri.roll_ticket, ri.stage, a.grade_code, a.qty, a.reason
        from `tabRoll Inspection Adjustment` a
        join `tabRoll Inspection` ri on ri.name = a.parent
        where ri.docstatus = 1 and (%(work_order)s is null or ri.work_order = %(work_order)s)""",
        {"work_order": work_order}, as_dict=True)


def scrap_grades() -> set:
    rows = frappe.get_all("DESAR Grade Configuration", filters={"parent": "DESAR Settings", "is_scrap": 1},
                          pluck="grade_code")
    return set(rows)
