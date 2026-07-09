"""
Patch: Reimport Roll Ticket if it was orphaned during migrate.
This patch runs every migrate to ensure Roll Ticket DocType exists.
"""
import frappe
import os


def execute():
    if frappe.db.get_value("DocType", "Roll Ticket", "module"):
        return  # Already exists with module — skip

    path = os.path.join(
        frappe.get_app_path("desar_manufacturing"),
        "desar_manufacturing", "doctype", "roll_ticket", "roll_ticket.json"
    )

    if not os.path.exists(path):
        frappe.log_error("Roll Ticket JSON not found at: " + path)
        return

    from frappe.modules.import_file import import_file_by_path
    import_file_by_path(path, force=True)
    frappe.db.commit()
    frappe.logger().info("DESAR: Roll Ticket DocType reimported successfully")
