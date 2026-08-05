"""
DESAR Manufacturing — Document Utilities

Small cross-service helpers that need a DB call, so they don't belong
in validation_utils.py (pure functions only).
"""
import frappe


def is_submitted(doctype: str, name: str) -> bool:
	return frappe.db.get_value(doctype, name, "docstatus") == 1
