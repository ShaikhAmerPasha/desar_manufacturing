"""
Post-install setup for DESAR Manufacturing.
Creates default DESAR Settings if not exist.
"""
import frappe
from frappe import _


def after_install():
    """Run after app is installed on a site."""
    _create_desar_settings()
    frappe.db.commit()


def _create_desar_settings():
    """Create default DESAR Settings singleton if it doesn't exist."""
    if frappe.db.exists("DESAR Settings"):
        return

    try:
        settings = frappe.get_doc({
            "doctype": "DESAR Settings",
            "default_company": "Standardtouch",
            "auto_create_roll_ticket": 1,
            "auto_create_repack_entry": 1,
            "yarn_store_warehouse": "Yarn Store - ST",
            "chemical_store_warehouse": "Chemical Store - ST",
            "accessories_store_warehouse": "Accessories Store - ST",
            "warping_wip_warehouse": "Warping WIP - ST",
            "loom_floor_warehouse": "Loom Floor - ST",
            "grey_roll_store_warehouse": "Grey Roll Store - ST",
            "finishing_wip_warehouse": "Finishing WIP - ST",
            "finished_roll_store_warehouse": "Finished Roll Store - ST",
            "cutting_packing_warehouse": "Cutting and Packing Floor - ST",
            "fg_grade_a_warehouse": "Finished Goods Grade A - ST",
            "fg_grade_b_warehouse": "Finished Goods Grade B - ST",
            "scrap_warehouse": "Scrap Yard - ST",
        })
        settings.insert(ignore_permissions=True)
    except Exception:
        pass  # Settings may already exist or warehouses may not exist yet
