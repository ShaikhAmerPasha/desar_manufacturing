import frappe
from frappe import _

from desar_manufacturing.utils.grade_utils import get_final_stage_names

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
    final_stages = get_final_stage_names()
    if not final_stages:
        return []
    rows = frappe.db.sql("""
        SELECT rt.article_name AS article, rt.design_no AS design_no, rt.size AS size,
               COUNT(DISTINCT rt.name) AS rolls, SUM(sg.qty) AS total_pcs,
               SUM(CASE WHEN sg.grade_code = 'A' THEN sg.qty ELSE 0 END) AS grade_a,
               SUM(CASE WHEN sg.grade_code = 'B' THEN sg.qty ELSE 0 END) AS grade_b,
               SUM(CASE WHEN sg.grade_code = 'C' THEN sg.qty ELSE 0 END) AS grade_c
        FROM `tabRoll Ticket` rt
        JOIN `tabDESAR Roll Ticket Stage Grade` sg
            ON sg.parent = rt.name AND sg.stage_name IN %(final_stages)s
        WHERE rt.roll_status = 'Completed'
        GROUP BY rt.article_name, rt.design_no, rt.size
        ORDER BY rt.article_name, rt.design_no, rt.size
    """, {"final_stages": final_stages}, as_dict=True)
    for r in rows:
        t = r.get("total_pcs") or 0
        r["pct_a"] = round((r.get("grade_a") or 0) / t * 100, 1) if t else 0
        r["pct_b"] = round((r.get("grade_b") or 0) / t * 100, 1) if t else 0
        r["pct_c"] = round((r.get("grade_c") or 0) / t * 100, 1) if t else 0
    return rows
