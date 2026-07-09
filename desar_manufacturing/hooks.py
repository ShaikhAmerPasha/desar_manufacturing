app_name        = "desar_manufacturing"
app_title       = "Desar Manufacturing"
app_publisher   = "DESAR Factory"
app_description = "Shemagh Manufacturing Module for DESAR Factory - ERPNext v15"
app_email       = "it@desarfactory.com"
app_license     = "MIT"
app_version     = "3.6.0"

required_apps = ["frappe", "erpnext"]

after_install = "desar_manufacturing.install.setup.after_install"
after_migrate = ["desar_manufacturing.install.setup.after_migrate"]

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["name", "in", [
            "Batch-custom_article",
            "Batch-custom_design_no",
            "Batch-custom_size",
            "Batch-custom_parent_beam_batch",
            "Batch-custom_machine_no",
            "Batch-custom_operator",
            "Work Order-custom_design_no",
            "Work Order-custom_article_name",
            "Work Order-custom_design_master",
            "Quality Inspection-custom_roll_ticket",
            "Quality Inspection-custom_desar_grade_readings",
            "Quality Inspection-custom_desar_stage_name",
            "Quality Inspection-custom_desar_grade_adj_section",
            "Quality Inspection-custom_desar_grade_adjustments",
            "Stock Entry-custom_source_qi",
            "BOM-custom_design_no",
            "BOM-custom_article_name",
            "BOM-custom_design_master",
            "Job Card-custom_assigned_to",
        ]]],
    },
]

doc_events = {
    "Stock Entry": {
        "on_submit": "desar_manufacturing.events.stock_entry.on_submit",
    },
    "Quality Inspection": {
        "before_submit": "desar_manufacturing.events.quality_inspection.before_submit",
        "on_submit":     "desar_manufacturing.events.quality_inspection.on_submit",
    },
    "Work Order": {
        "validate":      "desar_manufacturing.events.work_order.validate",
        "before_submit": "desar_manufacturing.events.work_order.before_submit",
    },
    "DESAR Settings": {
        "on_update": "desar_manufacturing.config.settings_manager.on_settings_update",
    },
}

doctype_js = {
	"Production Plan": "public/js/production_plan.js"
}

scheduler_events = {
    "daily": [
        "desar_manufacturing.tasks.daily.update_wip_report",
    ],
}

app_include_css = [
    "/assets/desar_manufacturing/css/desar.css",
    "/assets/desar_manufacturing/css/desar_workspace.css",
]
app_include_js = "/assets/desar_manufacturing/js/desar.js"

