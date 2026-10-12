frappe.query_reports["Sales Order Production"] = {
	filters: [
 {
  "fieldname": "sales_order",
  "label": __("Sales Order"),
  "fieldtype": "Link",
  "options": "Sales Order",
  "reqd": 1
 }
],
};
