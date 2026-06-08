import frappe
from frappe import _

def execute(filters=None):
    return get_columns(), get_data(filters or {})

def get_columns():
    return [
        {"fieldname":"roll_ticket","label":_("Roll Ticket"),"fieldtype":"Link","options":"Roll Ticket","width":130},
        {"fieldname":"roll_batch","label":_("Roll Batch"),"fieldtype":"Link","options":"Batch","width":170},
        {"fieldname":"parent_beam","label":_("Beam Batch"),"fieldtype":"Link","options":"Batch","width":170},
        {"fieldname":"design_no","label":_("Design"),"fieldtype":"Data","width":80},
        {"fieldname":"article","label":_("Article"),"fieldtype":"Data","width":90},
        {"fieldname":"size","label":_("Size"),"fieldtype":"Data","width":60},
        {"fieldname":"status","label":_("Status"),"fieldtype":"Data","width":120},
        {"fieldname":"grey_a","label":_("Grey A"),"fieldtype":"Int","width":70},
        {"fieldname":"grey_b","label":_("Grey B"),"fieldtype":"Int","width":70},
        {"fieldname":"grey_c","label":_("Grey C"),"fieldtype":"Int","width":70},
        {"fieldname":"fin_a","label":_("Fin A"),"fieldtype":"Int","width":70},
        {"fieldname":"fin_b","label":_("Fin B"),"fieldtype":"Int","width":70},
        {"fieldname":"fin_c","label":_("Fin C"),"fieldtype":"Int","width":70},
        {"fieldname":"cut_a","label":_("Final A"),"fieldtype":"Int","width":70},
        {"fieldname":"cut_b","label":_("Final B"),"fieldtype":"Int","width":70},
        {"fieldname":"cut_c","label":_("Final C"),"fieldtype":"Int","width":70},
        {"fieldname":"cut_total","label":_("Total"),"fieldtype":"Int","width":70},
        {"fieldname":"yield_a","label":_("A Yield %"),"fieldtype":"Percent","width":85},
    ]

def get_data(filters):
    conds = []
    vals = {}
    if filters.get("design_no"):
        conds.append("rt.design_no = %(design_no)s")
        vals["design_no"] = filters["design_no"]
    if filters.get("article_name"):
        conds.append("rt.article_name = %(article_name)s")
        vals["article_name"] = filters["article_name"]
    if filters.get("roll_status"):
        conds.append("rt.roll_status = %(roll_status)s")
        vals["roll_status"] = filters["roll_status"]
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = frappe.db.sql("""
        SELECT rt.name AS roll_ticket, rt.roll_batch, rt.parent_beam_batch AS parent_beam,
               rt.design_no, rt.article_name AS article, rt.size, rt.roll_status AS status,
               rt.grey_qty_a AS grey_a, rt.grey_qty_b AS grey_b, rt.grey_qty_c AS grey_c,
               rt.finished_qty_a AS fin_a, rt.finished_qty_b AS fin_b, rt.finished_qty_c AS fin_c,
               rt.cutted_qty_a AS cut_a, rt.cutted_qty_b AS cut_b, rt.cutted_qty_c AS cut_c,
               rt.cutted_total AS cut_total
        FROM `tabRoll Ticket` rt {where}
        ORDER BY rt.creation DESC
    """.format(where=where), vals, as_dict=True)
    for r in rows:
        t = r.get("cut_total") or 0
        r["yield_a"] = round((r.get("cut_a") or 0) / t * 100, 1) if t else 0
    return rows
