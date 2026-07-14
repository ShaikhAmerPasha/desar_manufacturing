import frappe
from frappe import _
from frappe.utils import flt

from desar_manufacturing.utils.grade_utils import get_final_stage_names

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
    rt_filters = {}
    for key in ("design_no", "article_name", "roll_status"):
        if filters.get(key):
            rt_filters[key] = filters[key]

    tickets = frappe.get_all(
        "Roll Ticket",
        filters=rt_filters,
        fields=["name", "roll_batch", "parent_beam_batch", "design_no", "article_name", "size", "roll_status"],
        order_by="creation desc",
    )
    if not tickets:
        return []

    stage_rows_by_ticket = _fetch_stage_rows([t.name for t in tickets])
    final_stages = set(get_final_stage_names())
    return [_build_row(rt, stage_rows_by_ticket.get(rt.name, []), final_stages) for rt in tickets]


def _fetch_stage_rows(ticket_names):
    rows = frappe.get_all(
        "DESAR Roll Ticket Stage Grade",
        filters={"parent": ["in", ticket_names]},
        fields=["parent", "stage_seq", "stage_name", "grade_code", "qty"],
    )
    grouped = {}
    for r in rows:
        grouped.setdefault(r.parent, []).append(r)
    return grouped


def _build_row(rt, stage_rows, final_stages):
    grey_stage, fin_stage, cut_stage = _resolve_stage_buckets(stage_rows, final_stages)
    grey = _grade_totals(stage_rows, grey_stage)
    fin = _grade_totals(stage_rows, fin_stage)
    cut = _grade_totals(stage_rows, cut_stage)
    cut_total = cut["A"] + cut["B"] + cut["C"]
    return {
        "roll_ticket": rt.name, "roll_batch": rt.roll_batch, "parent_beam": rt.parent_beam_batch,
        "design_no": rt.design_no, "article": rt.article_name, "size": rt.size, "status": rt.roll_status,
        "grey_a": grey["A"], "grey_b": grey["B"], "grey_c": grey["C"],
        "fin_a": fin["A"], "fin_b": fin["B"], "fin_c": fin["C"],
        "cut_a": cut["A"], "cut_b": cut["B"], "cut_c": cut["C"],
        "cut_total": cut_total,
        "yield_a": round(cut["A"] / cut_total * 100, 1) if cut_total else 0,
    }


def _resolve_stage_buckets(stage_rows, final_stages):
    """First stage seen = grey, a stage flagged is_final_stage = cut, anything in between = fin."""
    seq_by_name = {}
    for r in stage_rows:
        seq_by_name.setdefault(r.stage_name, r.stage_seq)
    ordered = sorted(seq_by_name, key=lambda name: seq_by_name[name])
    if not ordered:
        return None, None, None
    grey_stage = ordered[0]
    cut_stage = next((s for s in ordered if s in final_stages), ordered[-1])
    fin_stage = next((s for s in ordered if s not in (grey_stage, cut_stage)), None)
    return grey_stage, fin_stage, cut_stage


def _grade_totals(stage_rows, stage_name):
    totals = {"A": 0, "B": 0, "C": 0}
    for r in stage_rows:
        if r.stage_name == stage_name and r.grade_code in totals:
            totals[r.grade_code] += flt(r.qty)
    return totals
