"""
DESAR Quality Inspection Service v6
"""
import frappe
from frappe.utils import nowdate
from desar_manufacturing.config.settings_manager import SettingsManager


def make_roll_qi(po, roll, stage_name: str, batch_no: str, work_order: str) -> object:
	"""Create a Quality Inspection for a roll stage."""
	dm = frappe.get_cached_doc("Design Master", po.design_master)

	# Find stage config by name
	stage_config = None
	for sc in dm.stage_configuration:
		if sc.stage_name.lower() == stage_name.lower():
			stage_config = sc
			break

	if not stage_config and work_order:
		wo_item = frappe.db.get_value("Work Order", work_order, "production_item") or ""
		for sc in dm.stage_configuration:
			if sc.output_item == wo_item:
				stage_config = sc
				break

	template  = stage_config.get("qi_template", "") if stage_config else ""
	item_code = stage_config.output_item if stage_config else ""
	if not item_code and work_order:
		item_code = frappe.db.get_value("Work Order", work_order, "production_item") or ""

	# Reference: use submitted Manufacture SE (Work Order not allowed in v15)
	ref_type = ""
	ref_name = ""
	if work_order:
		se = frappe.db.get_value(
			"Stock Entry",
			{"work_order": work_order, "stock_entry_type": "Manufacture", "docstatus": 1},
			"name",
			order_by="creation desc",
		)
		if not se:
			se = frappe.db.get_value(
				"Stock Entry",
				{"work_order": work_order, "purpose": "Manufacture", "docstatus": 1},
				"name",
				order_by="creation desc",
			)
		if se:
			ref_type = "Stock Entry"
			ref_name = se

	# sample_size must be integer >= 1
	sample_size = 1
	if stage_config:
		raw = stage_config.get("sample_size")
		if raw:
			try:
				sample_size = max(1, int(float(raw)))
			except (ValueError, TypeError):
				sample_size = 1

	# Find custom roll ticket link
	roll_ticket = roll.get("roll_ticket") if roll else None
	if not roll_ticket and batch_no:
		roll_ticket = frappe.db.get_value("Roll Ticket", {"roll_batch": batch_no}, "name")

	qi = frappe.get_doc({
		"doctype":                     "Quality Inspection",
		"inspection_type":             "In Process",
		"reference_type":              ref_type,
		"reference_name":              ref_name,
		"item_code":                   item_code,
		"batch_no":                    batch_no or "",
		"sample_size":                 sample_size,
		"inspected_by":                frappe.session.user,
		"report_date":                 nowdate(),
		"quality_inspection_template": template,
		"status":                      "Accepted",
		"custom_roll_ticket":          roll_ticket or "",
		"custom_desar_stage_name":     stage_name,
	})

	# Append grade readings from settings
	grades = SettingsManager.get_grade_configuration()
	for g in grades:
		qi.append("custom_desar_grade_readings", {
			"grade_code":  g.get("grade_code") or "",
			"grade_label": g.get("grade_label") or "",
			"qty":         0
		})

	if template:
		try:
			tmpl = frappe.get_doc("Quality Inspection Template", template)
			for r in (tmpl.get("item_quality_inspection_parameter") or []):
				qi.append("readings", {
					"specification": r.specification,
					"min_value":     r.get("min_value"),
					"max_value":     r.get("max_value"),
					"numeric":       r.get("numeric"),
				})
		except Exception:
			pass

	qi.insert(ignore_permissions=True)
	return qi