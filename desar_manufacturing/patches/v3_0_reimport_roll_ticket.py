import frappe
import os

def execute():
    if frappe.db.get_value("DocType", "Roll Ticket", "module"):
        return
    path = os.path.join(
        frappe.get_app_path("desar_manufacturing"),
        "desar_manufacturing", "doctype", "roll_ticket", "roll_ticket.json"
    )
    if os.path.exists(path):
        from frappe.modules.import_file import import_file_by_path
        import_file_by_path(path, force=True)
        frappe.db.commit()
