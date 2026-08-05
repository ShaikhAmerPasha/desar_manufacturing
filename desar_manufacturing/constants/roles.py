"""
DESAR Manufacturing Role Groups

Shared role lists for frappe.only_for() guards across API and page
controllers. Keeps role membership consistent instead of each file
defining its own copy.
"""

ALL_DESAR_ROLES = [
	"System Manager",
	"DESAR Supervisor",
	"DESAR Operator",
	"DESAR QC Inspector",
	"DESAR Store Manager",
]

SUPERVISOR_ROLES = ["System Manager", "Manufacturing Manager", "DESAR Supervisor"]

JOB_CARD_ROLES = ["System Manager", "DESAR Supervisor", "DESAR Operator"]

QC_ROLES = ["System Manager", "DESAR Supervisor", "DESAR QC Inspector"]

STORE_ROLES = ["System Manager", "DESAR Supervisor", "DESAR Store Manager"]
