const STAGE_COLORS = [
	["Completed", "green"],
	["Packing", "purple"],
	["Finished Roll", "blue"],
	["Grey Roll", "orange"],
	["Beam Split", "yellow"],
	["Warping", "red"],
];

function stage_color(stage) {
	if (!stage) return "darkgrey";
	const match = STAGE_COLORS.find(([prefix]) => stage.startsWith(prefix));
	return match ? match[1] : "darkgrey";
}

frappe.listview_settings["DESAR Production Order"] = {
	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		if (!doc.current_stage) return [__(doc.status), "darkgrey", "status,=," + doc.status];
		return [__(doc.current_stage), stage_color(doc.current_stage), "current_stage,like,%" + doc.current_stage.split(" (")[0] + "%"];
	},
};
