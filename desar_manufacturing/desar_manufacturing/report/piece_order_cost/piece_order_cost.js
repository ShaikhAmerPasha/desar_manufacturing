frappe.query_reports["Piece Order Cost"] = {
	filters: [
		{ fieldname: "work_order", label: __("Work Order"), fieldtype: "Link", options: "Work Order", reqd: 1 },
	],
};
