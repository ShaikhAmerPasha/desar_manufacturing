import frappe
from desar_manufacturing.services.production_plan_service import list_plan_designs, create_desar_po_from_plan

@frappe.whitelist()
def run(plan_name):
    designs = list_plan_designs(plan_name)
    results = []
    for d in designs:
        try:
            res = create_desar_po_from_plan(plan_name, design_master=d)
            results.append(res)
        except Exception as e:
            results.append(f"Error for {d}: {str(e)}")
    return results
