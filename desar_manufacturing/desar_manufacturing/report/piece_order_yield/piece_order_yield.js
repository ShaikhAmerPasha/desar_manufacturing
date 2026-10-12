frappe.query_reports["Piece Order Yield"] = {
	filters: [
 {
  "fieldname": "work_order",
  "label": __("Work Order"),
  "fieldtype": "Link",
  "options": "Work Order"
 },
 {
  "fieldname": "group_by",
  "label": __("Group By"),
  "fieldtype": "Select",
  "options": "Work Order\nRoll",
  "default": "Work Order"
 }
],
};
