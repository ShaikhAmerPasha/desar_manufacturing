// Colors the Current Stage list column. Kept separate from `status` on
// purpose — see specs/production-order-stage-visibility.md.

const DESAR_STAGE_COLORS = {
	"Warping":       "gray",
	"Beam Split":    "blue",
	"Grey Roll":     "orange",
	"Finished Roll": "yellow",
	"Packing":       "purple",
	"Completed":     "green",
};

frappe.listview_settings["DESAR Production Order"] = {
	add_fields: ["current_stage"],
	formatters: {
		current_stage(value) {
			if (!value) return "";
			// Mixed multi-roll stages come back as "Grey Roll: 2, Packing: 1"
			const color = DESAR_STAGE_COLORS[value] || (value.includes(":") ? "cyan" : "gray");
			return `<span class="indicator-pill ${color} filterable" data-value="${frappe.utils.escape_html(value)}">
				<span>${frappe.utils.escape_html(value)}</span>
			</span>`;
		},
	},
};
