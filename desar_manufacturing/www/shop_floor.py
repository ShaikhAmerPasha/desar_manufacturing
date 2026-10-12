import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.throw(frappe._("Sign in to continue."), frappe.PermissionError)
    context.boot = {"frappe_version": frappe.__version__, "csrf_token": frappe.sessions.get_csrf_token()}
    return context
