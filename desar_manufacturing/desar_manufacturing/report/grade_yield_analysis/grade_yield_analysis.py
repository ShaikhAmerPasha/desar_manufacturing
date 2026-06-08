import frappe
from frappe import _

def execute(filters=None):
    return get_columns(), get_data()

def get_columns():
    return [
        {"fieldname":"article","label":_("Article"),"fieldtype":"Data","width":100},
        {"fieldname":"design_no","label":_("Design No."),"fieldtype":"Data","width":90},
        {"fieldname":"size","label":_("Size"),"fieldtype":"Data","width":70},
        {"fieldname":"rolls","label":_("Rolls"),"fieldtype":"Int","width":80},
        {"fieldname":"total_pcs","label":_("Total Pcs"),"fieldtype":"Int","width":90},
        {"fieldname":"grade_a","label":_("Grade A"),"fieldtype":"Int","width":90},
        {"fieldname":"grade_b","label":_("Grade B"),"fieldtype":"Int","width":90},
        {"fieldname":"grade_c","label":_("Scrap"),"fieldtype":"Int","width":90},
        {"fieldname":"pct_a","label":_("A %"),"fieldtype":"Percent","width":80},
        {"fieldname":"pct_b","label":_("B %"),"fieldtype":"Percent","width":80},
        {"fieldname":"pct_c","label":_("Scrap %"),"fieldtype":"Percent","width":80},
    ]

def get_data():
    rows = frappe.db.sql("""
        SELECT article_name AS article, design_no, size,
               COUNT(*) AS rolls, SUM(cutted_total) AS total_pcs,
               SUM(cutted_qty_a) AS grade_a, SUM(cutted_qty_b) AS grade_b, SUM(cutted_qty_c) AS grade_c
        FROM `tabRoll Ticket` WHERE roll_status = 'Completed'
        GROUP BY article_name, design_no, size
        ORDER BY article_name, design_no, size
    """, as_dict=True)
    for r in rows:
        t = r.get("total_pcs") or 0
        r["pct_a"] = round((r.get("grade_a") or 0) / t * 100, 1) if t else 0
        r["pct_b"] = round((r.get("grade_b") or 0) / t * 100, 1) if t else 0
        r["pct_c"] = round((r.get("grade_c") or 0) / t * 100, 1) if t else 0
    return rows
