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
            "Production Plan-custom_production_buffer_pct",
        ]]],
    },
    {
        "dt": "Property Setter",
        "filters": [["doc_type", "in", [
            "DESAR Beam Split Row",
            "DESAR Default Stage",
            "DESAR Grade Adjustment",
            "DESAR Grade Configuration",
            "DESAR Production Order",
            "DESAR Production Order Stage",
            "DESAR QI Grade Reading",
            "DESAR Roll Chain",
            "DESAR Roll Ticket Stage Grade",
            "DESAR Settings",
            "DESAR Stage Configuration",
            "DESAR Stage Operation",
            "Design Master",
            "Design Master Beam",
            "Design Master Flower Yarn",
            "Design Master Warp Yarn",
            "Design Master Weft Yarn",
            "Roll Ticket",
            "Warp Recipe",
            "Warp Recipe Item",
            "Weft Recipe",
            "Weft Recipe Item",
            "Batch",
            "Work Order",
            "Quality Inspection",
            "Stock Entry",
            "BOM",
            "Job Card",
            "Production Plan",
        ]]],
    },
]

doc_events = {
    "Stock Entry": {
        "before_validate": "desar_manufacturing.events.stock_entry.before_validate",
        "on_submit":       "desar_manufacturing.events.stock_entry.on_submit",
        "on_cancel":       "desar_manufacturing.events.stock_entry.on_cancel",
    },
    "Quality Inspection": {
        "validate":      "desar_manufacturing.events.quality_inspection.validate",
        "before_submit": "desar_manufacturing.events.quality_inspection.before_submit",
        "on_submit":     "desar_manufacturing.events.quality_inspection.on_submit",
        "on_cancel":     "desar_manufacturing.events.quality_inspection.on_cancel",
    },
    "Work Order": {
        "before_insert":   "desar_manufacturing.events.work_order.before_insert",
        "before_validate": "desar_manufacturing.events.work_order.before_validate",
        "validate":        "desar_manufacturing.events.work_order.validate",
        "before_submit":   "desar_manufacturing.events.work_order.before_submit",
        "on_cancel":       "desar_manufacturing.events.work_order.on_cancel",
    },
    "Production Plan": {
        "validate": "desar_manufacturing.events.production_plan.validate",
    },
    "DESAR Settings": {
        "on_update": "desar_manufacturing.config.settings_manager.on_settings_update",
    },
}

doctype_js = {
	"Production Plan": "public/js/production_plan.js",
	"Quality Inspection": "public/js/quality_inspection.js"
}

override_doctype_class = {
	"Production Plan": "desar_manufacturing.overrides.production_plan.CustomProductionPlan",
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

