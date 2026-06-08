"""
DESAR Manufacturing — Settings Manager

Single source of truth for all DESAR Settings.
Validates required fields before returning values.
Uses frappe.db.get_singles_dict for DB access — avoids loading the
DocType controller which fails in Frappe test runner context.
Cache cleared when DESAR Settings is saved via on_update hook wrapper.
"""
import frappe
from frappe import _


class SettingsManager:
    """
    Manages access to DESAR Settings singleton.

    Usage:
        from desar_manufacturing.config.settings_manager import SettingsManager
        wh = SettingsManager.get_warehouse("cutting_packing_warehouse")
        company = SettingsManager.get("default_company")
    """

    _DOCTYPE = "DESAR Settings"
    _CACHE_KEY = "desar_settings"

    WAREHOUSE_KEYS = [
        "yarn_warehouse",
        "chemical_warehouse",
        "accessories_warehouse",
        "warping_wip_warehouse",
        "loom_floor_warehouse",
        "grey_roll_warehouse",
        "finishing_wip_warehouse",
        "finished_roll_warehouse",
        "cutting_packing_warehouse",
        "fg_grade_a_warehouse",
        "fg_grade_b_warehouse",
        "scrap_warehouse",
    ]

    @classmethod
    def _get_all(cls) -> dict:
        """
        Load all DESAR Settings fields at once.

        Uses frappe.db.get_singles_dict() — reads directly from tabSingles
        without loading the DocType controller.

        frappe.get_single() fails in test runner context because it calls
        load_doctype_module() which calls get_module_app() which cannot
        resolve "Desar Manufacturing" in the test runner module registry.
        get_singles_dict() bypasses this entirely — pure DB read.
        """
        cached = frappe.cache().get_value(cls._CACHE_KEY)
        if cached:
            return cached

        if not frappe.db.exists("DocType", cls._DOCTYPE):
            return {}

        try:
            data = frappe.db.get_singles_dict(cls._DOCTYPE)
        except Exception:
            # Never raise — return empty dict as safe fallback
            frappe.log_error(
                title="DESAR: SettingsManager._get_all failed",
                message=frappe.get_traceback(),
            )
            return {}

        if data:
            frappe.cache().set_value(cls._CACHE_KEY, data, expires_in_sec=3600)
        return data or {}

    @classmethod
    def get(cls, key: str, default=None):
        """Get a single setting value with optional fallback."""
        value = cls._get_all().get(key)
        return value if value is not None else default

    @classmethod
    def get_warehouse(cls, key: str) -> str:
        """
        Get a warehouse setting.
        Raises a descriptive, user-friendly error if not configured.
        """
        value = cls.get(key)
        if not value:
            frappe.throw(
                _("DESAR Settings → <b>{0}</b> is not configured.<br>"
                  "Please go to <b>DESAR Settings</b> and fill all warehouse fields.").format(key),
                title=_("Configuration Missing"),
            )
        return value

    @classmethod
    def get_all_warehouses(cls) -> dict:
        """Get all 12 warehouse settings. Raises listing ALL missing fields."""
        result = {}
        missing = []
        for key in cls.WAREHOUSE_KEYS:
            value = cls.get(key)
            if value:
                result[key] = value
            else:
                missing.append(key)

        if missing:
            frappe.throw(
                _("DESAR Settings: the following warehouses are not configured:<br>"
                  "<b>{0}</b><br><br>"
                  "Please configure them before proceeding.").format(
                    "<br>".join(missing)
                ),
                title=_("Incomplete Configuration"),
            )
        return result

    @classmethod
    def is_auto_roll_ticket_enabled(cls) -> bool:
        """Check if Roll Ticket auto-creation is enabled. Default True."""
        value = cls.get("auto_create_roll_ticket")
        return value if value is not None else True

    @classmethod
    def is_auto_repack_enabled(cls) -> bool:
        """Check if Repack auto-creation is enabled. Default True."""
        value = cls.get("auto_create_repack_entry")
        return value if value is not None else True

    @classmethod
    def get_company(cls) -> str:
        """Get default company. Falls back to Global Defaults."""
        company = cls.get("default_company")
        if not company:
            company = frappe.db.get_single_value(
                "Global Defaults", "default_company"
            )
        return company or ""


def on_settings_update(doc, method):
    """
    Wrapper function called by hooks.py on_update for DESAR Settings.
    Clears settings cache so next request reads fresh values.
    Must be a module-level function (not classmethod) for Frappe doc_events.
    """
    frappe.cache().delete_value(SettingsManager._CACHE_KEY)
    frappe.logger().debug("DESAR SettingsManager: cache cleared on settings update")