// DESAR Production Order v6 — Client Script

const styles = `
.desar-dashboard-card {
	background: #ffffff;
	border: 1px solid #e2e8f0;
	border-radius: 12px;
	box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
	margin-bottom: 20px;
	overflow: hidden;
}
.desar-dashboard-header {
	background: #f8fafc;
	border-bottom: 1px solid #e2e8f0;
	padding: 14px 20px;
	font-weight: 700;
	font-size: 15px;
	color: #1e293b;
}
.desar-dashboard-body {
	padding: 20px;
}
.desar-stage-card {
	border: 1px solid #e2e8f0;
	border-radius: 8px;
	margin-bottom: 8px;
	background: #fafafb;
	overflow: hidden;
}
.desar-stage-header {
	padding: 10px 16px;
	background: #f8fafc;
	display: flex;
	justify-content: space-between;
	align-items: center;
	cursor: pointer;
	font-weight: 700;
	font-size: 13px;
	border-bottom: 1px solid #e2e8f0;
	user-select: none;
}
.desar-stage-header:hover {
	background: #f1f5f9;
}
.desar-stage-body {
	padding: 12px 16px;
	font-size: 13px;
	background: #ffffff;
}
.desar-badge {
	display: inline-flex;
	align-items: center;
	padding: 3px 8px;
	border-radius: 6px;
	font-size: 11px;
	font-weight: 600;
	margin-right: 6px;
	margin-bottom: 4px;
}
.desar-badge-green { background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.desar-badge-blue { background-color: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
.desar-badge-grey { background-color: #f8fafc; color: #475569; border: 1px solid #e2e8f0; }
.desar-badge-red { background-color: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

.desar-link {
	color: #2563eb !important;
	text-decoration: none !important;
	font-weight: 600;
}
.desar-link:hover {
	text-decoration: underline !important;
	color: #1d4ed8 !important;
}
@keyframes desar-pulse {
	0%   { box-shadow: 0 0 0 0 rgba(249, 115, 22, 0.85); transform: scale(1); }
	70%  { box-shadow: 0 0 0 12px rgba(249, 115, 22, 0); transform: scale(1.05); }
	100% { box-shadow: 0 0 0 0 rgba(249, 115, 22, 0); transform: scale(1); }
}
.desar-pulse {
	background-color: #f97316 !important;
	border-color: #f97316 !important;
	animation: desar-pulse 1.2s infinite;
}
@keyframes desar-pulse-ring {
	0%   { box-shadow: 0 0 0 0 rgba(249, 115, 22, 0.85); }
	70%  { box-shadow: 0 0 0 6px rgba(249, 115, 22, 0); }
	100% { box-shadow: 0 0 0 0 rgba(249, 115, 22, 0); }
}
.desar-pulse-ring {
	display: inline-block;
	border-radius: 6px;
	animation: desar-pulse-ring 1.2s infinite;
}
`;

frappe.ui.form.on("DESAR Production Order", {
	refresh(frm) {
		_desar_simplify_form(frm, {
			hide_all: ["naming_series", "sales_order", "production_plan"],
			// Supervisor keeps these for troubleshooting; Operator/QC/Store Manager don't.
			hide_strict_only: ["warping_wo", "warping_transfer_se", "warping_manufacture_se", "beam_split_se"],
		});
		_desar_simplify_grid(frm, "roll_chains", {
			// Reached via the guided Job Card "Create QI" buttons, not by clicking
			// a raw Link field here — hidden for all 4 floor roles including Supervisor.
			hide_all: ["grey_roll_qi", "finished_roll_qi", "packing_qi"],
			hide_strict_only: ["grey_roll_wo", "finished_roll_wo", "packing_wo", "packing_manufacture_se", "repack_se"],
		});

		if (frm.doc.docstatus !== 1) return;

		// Inject styles once
		if (!$("style#desar-dashboard-styles").length) {
			$("<style id='desar-dashboard-styles'>").text(styles).appendTo("head");
		}

		frm.trigger("render_warping_actions");
		frm.trigger("render_beam_split_actions");
		frm.trigger("render_next_step_guidance");
		frm.trigger("load_and_render_dashboard");

		// Job Cards/SEs/QIs are completed on their OWN form, usually in a
		// separate tab (links open target="_blank") — this tab never
		// navigates away, so nothing here naturally re-fetches. A submitted
		// QI can also update this doc's own roll_chains fields server-side,
		// not just the dashboard's Job Card/SE/QI cache — so do a full
		// reload_doc() (which re-fires refresh, re-running everything below)
		// whenever the user tabs back in, instead of just the dashboard part.
		$(window).off("focus.desar_po").on("focus.desar_po", () => {
			if (cur_frm === frm && frm.doc.docstatus === 1) {
				frm.reload_doc();
			}
		});
	},

	render_warping_actions(frm) {
		const s = frm.doc.warping_status;
		if (s === "Not Started") {
			_pulse_custom_button(
				frm.add_custom_button(__("Start Warping"), () => _call(frm, "start_warping", {}), __("Warping")),
				__("Click to submit the Warping Work Order and begin manufacturing")
			);
		} else if (s === "In Progress" && frm.doc.warping_transfer_se && !frm.doc.warping_manufacture_se) {
			_pulse_custom_button(
				frm.add_custom_button(__("Complete Warping"), () => _call(frm, "complete_warping", {}), __("Warping")),
				__("Click once the Warping Transfer SE below has been submitted")
			);
			frm.add_custom_button(__("View Transfer SE"), () =>
				frappe.set_route("Form", "Stock Entry", frm.doc.warping_transfer_se), __("Warping"));
		}
	},

	render_beam_split_actions(frm) {
		if (frm.doc.warping_status !== "Completed") return;
		if (frm.doc.beam_split_status === "Completed") return;
		_pulse_custom_button(
			frm.add_custom_button(__("Split Beam"), () => _split_beam_dialog(frm), __("Beam Split")),
			__("Click to divide the warping beam into individual rolls")
		);
	},

	render_next_step_guidance(frm) {
		// This runs more than once per page load by design (once immediately
		// on refresh, again once the async dashboard data below has loaded,
		// so the message reflects fresh data) — but frm.set_intro() ->
		// show_message() always APPENDS a new banner, it never clears the
		// previous one. Without this clear, every re-render stacks another
		// copy of the same message on top of the last.
		frm.dashboard.clear_headline();
		const { message, color } = _next_step_message(frm);
		frm.set_intro(message, color);
	},

	load_and_render_dashboard(frm) {
		// Collect all Work Orders
		const wo_names = [];
		if (frm.doc.warping_wo) wo_names.push(frm.doc.warping_wo);
		(frm.doc.roll_chains || []).forEach(r => {
			if (r.grey_roll_wo) wo_names.push(r.grey_roll_wo);
			if (r.finished_roll_wo) wo_names.push(r.finished_roll_wo);
			if (r.packing_wo) wo_names.push(r.packing_wo);
		});

		// Collect all QIs
		const qi_names = [];
		(frm.doc.roll_chains || []).forEach(r => {
			if (r.grey_roll_qi) qi_names.push(r.grey_roll_qi);
			if (r.finished_roll_qi) qi_names.push(r.finished_roll_qi);
			if (r.packing_qi) qi_names.push(r.packing_qi);
		});

		// Show loading placeholders
		_show_placeholders(frm);

		const promises = [];

		let job_cards_by_wo = {};
		if (wo_names.length) {
			promises.push(
				frappe.db.get_list("Job Card", {
					filters: {work_order: ["in", wo_names], docstatus: ["!=", 2]},
					fields: ["name", "work_order", "operation", "status"],
					limit: 1000
				}).then(res => {
					_warn_if_truncated(res, "Job Cards");
					(res || []).forEach(jc => {
						if (!job_cards_by_wo[jc.work_order]) job_cards_by_wo[jc.work_order] = [];
						job_cards_by_wo[jc.work_order].push(jc);
					});
				})
			);

			promises.push(
				frappe.db.get_list("Stock Entry", {
					filters: {work_order: ["in", wo_names], docstatus: ["!=", 2]},
					fields: ["name", "work_order", "purpose", "stock_entry_type", "docstatus"],
					limit: 1000
				}).then(res => {
					_warn_if_truncated(res, "Stock Entries");
					let stock_entries_by_wo = {};
					(res || []).forEach(se => {
						if (!stock_entries_by_wo[se.work_order]) stock_entries_by_wo[se.work_order] = [];
						stock_entries_by_wo[se.work_order].push(se);
					});
					frm.dashboard_stock_entries = stock_entries_by_wo;
				})
			);
		} else {
			frm.dashboard_stock_entries = {};
		}

		let qi_by_name = {};
		if (qi_names.length) {
			promises.push(
				frappe.db.get_list("Quality Inspection", {
					filters: {name: ["in", qi_names]},
					fields: ["name", "status", "docstatus"],
					limit: 1000
				}).then(res => {
					_warn_if_truncated(res, "Quality Inspections");
					(res || []).forEach(qi => {
						qi_by_name[qi.name] = qi;
					});
				})
			);
		}

		frm.dashboard_job_cards = job_cards_by_wo;
		frm.dashboard_qis = qi_by_name;

		Promise.all(promises).then(() => {
			frm.trigger("render_warping_dashboard");
			frm.trigger("render_roll_chains");
			frm.trigger("render_next_step_guidance");
		}).catch(err => {
			console.error("Error loading dashboard data:", err);
			frm.trigger("render_warping_dashboard");
			frm.trigger("render_roll_chains");
			frm.trigger("render_next_step_guidance");
		});
	},

	render_warping_dashboard(frm) {
		const $wrapper = frm.fields_dict["warping_wo"].$wrapper;
		$wrapper.empty().show();

		const wo = frm.doc.warping_wo;
		const batch = frm.doc.warping_batch;
		const status = frm.doc.warping_status;

		const job_cards = (frm.dashboard_job_cards && frm.dashboard_job_cards[wo]) || [];
		const stock_entries = (frm.dashboard_stock_entries && frm.dashboard_stock_entries[wo]) || [];

		const is_completed = status === "Completed";
		const display_style = is_completed ? "none" : "block";
		const toggle_icon = is_completed ? "▶" : "▼";

		const job_cards_html = _job_cards_html(job_cards, wo);
		const se_list = _warping_se_list(stock_entries, frm.doc.warping_transfer_se, frm.doc.warping_manufacture_se);
		const stock_entries_html = _stock_entries_html(se_list, wo);

		const details_html = `
			<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:16px;">
				<div>
					<strong>Work Order:</strong><br>
					${wo ? `<a href="${frappe.utils.get_form_link("Work Order", wo)}" target="_blank" class="desar-link" style="font-size:14px; font-weight:600;">${wo}</a>` : `<span style="color:#6c757d;">Not Created</span>`}
					${job_cards_html}
				</div>
				<div>${stock_entries_html}</div>
			</div>
		`;

		const $card = $(`
			<div class="desar-dashboard-card">
				<div class="desar-dashboard-header" style="display:flex; justify-content:space-between; align-items:center; cursor:pointer;">
					<span>
						<span class="toggle-indicator" style="margin-right: 8px; font-size: 11px;">${toggle_icon}</span>
						Stage 1 — Warping
						<span style="margin-left: 10px;">${_badge(status, status)}</span>
					</span>
					${batch ? `<span style="font-weight:400; font-size:12px; color:#6c757d;">Beam Batch: <a href="${frappe.utils.get_form_link("Batch", batch)}" target="_blank" class="desar-link">${batch}</a></span>` : ""}
				</div>
				<div class="desar-dashboard-body" style="display:${display_style}; border-top:1px solid #f1f5f9;">
					${_details_toggle(__("Details"), details_html)}
				</div>
			</div>
		`);

		$card.find(".desar-dashboard-header").on("click", function(e) {
			if ($(e.target).closest("a").length) return;
			const $body = $card.find(".desar-dashboard-body");
			const $indicator = $card.find(".toggle-indicator");
			if ($body.is(":visible")) {
				$body.slideUp(150);
				$indicator.text("▶");
			} else {
				$body.slideDown(150);
				$indicator.text("▼");
			}
		});

		_bind_details_toggle($card);
		$wrapper.append($card);
	},

	render_roll_chains(frm) {
		const $field = frm.get_field("roll_chains");
		if (!$field || !$field.$wrapper) return;
		$field.$wrapper.find(".frappe-control").hide();
		$field.$wrapper.find(".desar-roll-chains").remove();

		if (!frm.doc.roll_chains || !frm.doc.roll_chains.length) {
			const msg = frm.doc.beam_split_status === "Completed"
				? __("No rolls found.")
				: __("Complete Beam Split to see roll chains.");
			$field.$wrapper.append(`<div class="desar-roll-chains" style="padding:12px;color:#6c757d;">${msg}</div>`);
			return;
		}
		const $wrap = $('<div class="desar-roll-chains"></div>');
		frm.doc.roll_chains.forEach(roll => $wrap.append(_render_roll_row(frm, roll)));

		_bind_details_toggle($wrap);

		// Event delegation for stage accordion toggles
		$wrap.on("click", ".desar-stage-header", function(e) {
			if ($(e.target).closest("a").length || $(e.target).closest("button").length) return;
			const $body = $(this).next(".desar-stage-body");
			const $indicator = $(this).find(".stage-toggle-indicator");
			if ($body.is(":visible")) {
				$body.slideUp(120);
				$indicator.text("▶");
			} else {
				$body.slideDown(120);
				$indicator.text("▼");
			}
		});

		$field.$wrapper.append($wrap);
	},
});


function _warn_if_truncated(res, label) {
	if ((res || []).length === 1000) {
		frappe.show_alert({
			message: __("{0} dashboard list hit the 1000-row cap — some may not be shown.", [label]),
			indicator: "orange",
		}, 8);
	}
}


function _show_placeholders(frm) {
	["warping_wo", "warping_batch", "warping_status", "warping_transfer_se", "warping_manufacture_se"].forEach(f => {
		if (frm.fields_dict[f]) frm.fields_dict[f].$wrapper.hide();
	});

	const $warping_wo_wrap = frm.fields_dict["warping_wo"].$wrapper;
	$warping_wo_wrap.show().empty().append(`
		<div class="desar-dashboard-card warping-placeholder">
			<div class="desar-dashboard-header">Stage 1 — Warping</div>
			<div class="desar-dashboard-body" style="text-align:center; color:#6c757d; padding:30px;">
				<i class="fa fa-spinner fa-spin fa-2x"></i><br><br>Loading Warping Dashboard...
			</div>
		</div>
	`);

	const $field = frm.get_field("roll_chains");
	if ($field && $field.$wrapper) {
		$field.$wrapper.find(".frappe-control").hide();
		$field.$wrapper.find(".desar-roll-chains").remove();
		$field.$wrapper.append(`
			<div class="desar-roll-chains" style="text-align:center; color:#6c757d; padding:30px;">
				<i class="fa fa-spinner fa-spin fa-2x"></i><br><br>Loading Roll Chains...
			</div>
		`);
	}
}


function _render_roll_row(frm, roll) {
	const color = _status_color(roll.roll_status || "Not Started");
	const icon  = _status_icon(roll.roll_status || "Not Started");

	const $row = $(`
		<div style="border:1px solid ${color};border-left:4px solid ${color};border-radius:8px;
			padding:14px;margin-bottom:12px;background:white;box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
			<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
				<div style="font-weight:700;font-size:14px;color:#1e293b;">
					${icon} Roll ${roll.roll_no}
					${roll.beam_roll_batch ? `<span style="font-weight:400;font-size:12px;color:#6c757d;margin-left:8px;">Beam: <a href="${frappe.utils.get_form_link("Batch", roll.beam_roll_batch)}" target="_blank" class="desar-link">${roll.beam_roll_batch}</a></span>` : ""}
					${roll.roll_ticket ? `<span style="font-size:12px;margin-left:8px;padding: 2px 6px; background:#f1f5f9; border-radius:4px;"><a href="${frappe.utils.get_form_link("Roll Ticket", roll.roll_ticket)}" target="_blank" class="desar-link">🎫 Ticket: ${roll.roll_ticket}</a></span>` : ""}
				</div>
				<div class="roll-actions"></div>
			</div>
			<div style="margin-bottom:10px;">${_roll_summary_html(roll)}</div>
			<div style="display:flex;flex-direction:column;gap:8px;">
				${_render_stage_section(frm, "Grey Roll",     roll.grey_roll_status,     roll.grey_roll_wo,     roll.grey_roll_batch,    roll.grey_roll_qi,     "grey")}
				${_render_stage_section(frm, "Finished Roll", roll.finished_roll_status, roll.finished_roll_wo, roll.finished_roll_batch, roll.finished_roll_qi, "finished")}
				${_render_stage_section(frm, "Packing",       roll.packing_status,       roll.packing_wo,       "",                       roll.packing_qi,      "packing")}
			</div>
		</div>`);

	_add_roll_buttons($row.find(".roll-actions"), frm, roll);
	return $row;
}


function _render_stage_section(frm, stage_label, status, wo, batch_no, qi_no, stage_key) {
	const is_completed = status === "Completed";
	const display_style = is_completed ? "none" : "block";
	const toggle_icon = is_completed ? "▶" : "▼";
	const color = _status_color(status || "Locked");

	const job_cards = (frm.dashboard_job_cards && frm.dashboard_job_cards[wo]) || [];
	const stock_entries = (frm.dashboard_stock_entries && frm.dashboard_stock_entries[wo]) || [];

	const qi_html = _qi_badge_html(frm, qi_no);
	const job_cards_html = _job_cards_html(job_cards, wo);
	const se_list = _roll_stage_se_list(stock_entries, stage_key, frm.doc.packing_manufacture_se);
	const se_html = _stock_entries_html(se_list, wo);
	const header_bg = is_completed ? "#f8fafc" : `${color}06`;

	const details_html = `
		<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px;">
			<div>
				<strong>Work Order:</strong><br>
				${wo ? `<a href="${frappe.utils.get_form_link("Work Order", wo)}" target="_blank" class="desar-link" style="font-weight:600;">${wo}</a>` : `<span style="color:#6c757d;">Not Created</span>`}
				${job_cards_html}
			</div>
			<div>${se_html}</div>
		</div>
	`;

	return `
		<div class="desar-stage-card" style="border-left: 3px solid ${color};">
			<div class="desar-stage-header" style="background:${header_bg};">
				<span>
					<span class="stage-toggle-indicator" style="margin-right:6px; font-size:9px;">${toggle_icon}</span>
					${__(stage_label)}
					<span style="margin-left: 8px;">${_badge(status, status)}</span>
					${qi_html}
				</span>
				<span style="font-weight:400; font-size:11px; color:#6c757d;">
					${batch_no ? `Batch: <a href="${frappe.utils.get_form_link("Batch", batch_no)}" target="_blank" class="desar-link">${batch_no}</a>` : ""}
				</span>
			</div>
			<div class="desar-stage-body" style="display:${display_style}; border-top:1px solid #f1f5f9;">
				${details_html}
			</div>
		</div>
	`;
}


function _qi_badge_html(frm, qi_no) {
	if (!qi_no) return "";
	const qi_doc = (frm.dashboard_qis && frm.dashboard_qis[qi_no]) || {};
	let qi_status = qi_doc.status || "Draft";
	if (qi_doc.docstatus === 1) {
		qi_status = qi_doc.status === "Accepted" ? "Accepted" : "Rejected";
	} else if (qi_doc.docstatus === 0) {
		qi_status = "Draft";
	}
	const badge = _badge(`QI: ${qi_no} (${qi_status})`, qi_status);
	const pending_cls = qi_doc.docstatus === 0 ? "desar-pulse-ring" : "";
	return `<span style="margin-left:8px; display:inline-flex; align-items:center;" class="${pending_cls}">
		<a href="${frappe.utils.get_form_link("Quality Inspection", qi_no)}" target="_blank">${badge}</a>
	</span>`;
}


function _roll_stage_se_list(stock_entries, stage_key, packing_manufacture_se) {
	const se_list = stock_entries.map(se => {
		const is_mfg = se.purpose === "Manufacture" || se.stock_entry_type === "Manufacture" ||
			(stage_key === "packing" && se.name === packing_manufacture_se);
		return { name: se.name, label: is_mfg ? "Manufacture SE" : "Transfer SE", docstatus: se.docstatus };
	});
	if (stage_key === "packing" && packing_manufacture_se && !se_list.some(s => s.name === packing_manufacture_se)) {
		se_list.push({ name: packing_manufacture_se, label: "Manufacture SE", docstatus: 0 });
	}
	return se_list;
}


function _warping_se_list(stock_entries, transfer_se, manufacture_se) {
	const by_name = {};
	stock_entries.forEach(se => { by_name[se.name] = se; });
	const se_list = [];
	const push_named = (name, label) => {
		if (!name) return;
		const existing = by_name[name];
		se_list.push({ name, label, docstatus: existing ? existing.docstatus : 1 });
	};
	push_named(transfer_se, "Transfer SE");
	push_named(manufacture_se, "Manufacture SE");
	stock_entries.forEach(se => {
		if (se.name !== transfer_se && se.name !== manufacture_se) {
			const is_mfg = se.purpose === "Manufacture" || se.stock_entry_type === "Manufacture";
			se_list.push({ name: se.name, label: is_mfg ? "Manufacture SE" : "Transfer SE", docstatus: se.docstatus });
		}
	});
	return se_list;
}


function _job_cards_html(job_cards, wo) {
	if (!job_cards.length) {
		return wo ? `<div style="margin-top: 6px; color:#8c95a5; font-size:11px;">No Job Cards</div>` : "";
	}
	return `
		<div style="margin-top: 6px;">
			<strong>Job Cards:</strong>
			<div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:2px;">
				${job_cards.map(jc => {
					const badge = _badge(`${jc.operation}: ${jc.status}`, jc.status);
					const pending = jc.status !== "Completed";
					return `<a href="${frappe.utils.get_form_link("Job Card", jc.name)}" target="_blank" class="${pending ? "desar-pulse-ring" : ""}">${badge}</a>`;
				}).join("")}
			</div>
		</div>
	`;
}


function _stock_entries_html(se_list, wo) {
	if (!se_list.length) {
		return wo ? `<div style="margin-top: 6px; color:#8c95a5; font-size:11px;">No Stock Entries</div>` : "";
	}
	return `
		<div style="margin-top: 6px;">
			<strong>Stock Entries:</strong>
			<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:2px;">
				${se_list.map(se => _se_badge_html(se)).join("")}
			</div>
		</div>
	`;
}


function _se_badge_html(se) {
	const docstatus_label = se.docstatus === 1 ? "Submitted" : (se.docstatus === 0 ? "Draft" : "Cancelled");
	const badge = _badge(`${se.label}: ${se.name} (${docstatus_label})`, docstatus_label);
	const pending = se.docstatus === 0;
	return `
		<div style="display:inline-flex; align-items:center; margin-bottom: 2px;" class="${pending ? "desar-pulse-ring" : ""}">
			<a href="${frappe.utils.get_form_link("Stock Entry", se.name)}" target="_blank">${badge}</a>
		</div>
	`;
}


function _roll_summary_html(roll) {
	const stages = [
		["Grey", roll.grey_roll_status],
		["Finishing", roll.finished_roll_status],
		["Packing", roll.packing_status],
	];
	return stages.map(([label, status]) => _badge(`${label}: ${status || "Not Started"}`, status)).join("");
}


function _details_toggle(label, details_html) {
	return `
		<div class="desar-details-toggle" style="cursor:pointer; font-size:11px; color:#2563eb; display:inline-block;">
			<span class="desar-details-indicator">▸</span> ${label}
		</div>
		<div class="desar-details-body" style="display:none; margin-top:8px;">
			${details_html}
		</div>
	`;
}


function _bind_details_toggle($scope) {
	$scope.on("click", ".desar-details-toggle", function() {
		const $body = $(this).next(".desar-details-body");
		const $ind = $(this).find(".desar-details-indicator");
		if ($body.is(":visible")) {
			$body.slideUp(120);
			$ind.text("▸");
		} else {
			$body.slideDown(120);
			$ind.text("▾");
		}
	});
}




function _badge(label, status) {
	let cls = "desar-badge-grey";
	let s = (status || "").toLowerCase();
	if (["completed", "accepted", "done", "submitted"].includes(s)) {
		cls = "desar-badge-green";
	} else if (["in progress", "active", "work in progress"].includes(s)) {
		cls = "desar-badge-blue";
	} else if (["rejected", "cancelled", "failed"].includes(s)) {
		cls = "desar-badge-red";
	}
	return `<span class="desar-badge ${cls}">${label}</span>`;
}


function _add_roll_buttons($c, frm, roll) {
	const rn = roll.roll_no;

	// Grey Roll
	if (roll.grey_roll_status === "Not Started" && roll.beam_roll_batch)
		_btn($c, "Start Grey Roll", "primary", () => _roll_call(frm, "start_grey_roll", rn),
			"Begin the Grey Roll stage for this roll");
	if (roll.grey_roll_status === "In Progress" && !roll.grey_roll_qi) {
		const blocked = _job_cards_pending(frm, roll.grey_roll_wo);
		_btn($c, "Complete Grey Roll", blocked ? "default" : "primary", () => _roll_call(frm, "complete_grey_roll", rn),
			blocked ? "Complete the open Job Card(s) above first" : "Finish Grey Roll and create its Quality Inspection");
	}
	if (roll.grey_roll_status === "In Progress" && roll.grey_roll_qi)
		_btn($c, "Refresh", "default", () => _refresh_roll(frm, rn));

	// Finished Roll
	if (roll.finished_roll_status === "Not Started" && roll.grey_roll_status === "Completed")
		_btn($c, "Start Finished Roll", "primary", () => _roll_call(frm, "start_finished_roll", rn),
			"Begin the Finished Roll stage for this roll");
	if (roll.finished_roll_status === "In Progress" && !roll.finished_roll_qi) {
		const blocked = _job_cards_pending(frm, roll.finished_roll_wo);
		_btn($c, "Complete Finished Roll", blocked ? "default" : "primary", () => _roll_call(frm, "complete_finished_roll", rn),
			blocked ? "Complete the open Job Card(s) above first" : "Finish Finished Roll and create its Quality Inspection");
	}
	if (roll.finished_roll_status === "In Progress" && roll.finished_roll_qi)
		_btn($c, "Refresh", "default", () => _refresh_roll(frm, rn));

	// Packing
	if (roll.packing_status === "Not Started" && roll.finished_roll_status === "Completed")
		_btn($c, "Start Packing", "primary", () => _roll_call(frm, "start_packing", rn),
			"Begin the Packing stage for this roll");
	if (roll.packing_status === "In Progress" && !roll.packing_manufacture_se) {
		const blocked = _job_cards_pending(frm, roll.packing_wo);
		_btn($c, "Complete Packing", blocked ? "default" : "primary", () => _roll_call(frm, "complete_packing", rn),
			blocked ? "Complete the open Job Card(s) above first" : "Finish Packing and create the Manufacture Stock Entry");
	}
	if (roll.packing_status === "In Progress" && roll.packing_manufacture_se && !roll.packing_qi)
		_btn($c, "Create Inspection", "primary", () => _roll_call(frm, "finalize_packing", rn),
			"Create the Packing Quality Inspection");
	if (roll.packing_status === "In Progress" && roll.packing_qi)
		_btn($c, "Refresh", "default", () => _refresh_roll(frm, rn));
	if (roll.packing_status === "In Progress" && roll.packing_qi && _qi_submitted(frm, roll.packing_qi))
		_btn($c, "Complete Roll", "primary", () => _roll_call(frm, "complete_roll", rn),
			"Submitted QI accepted — click to mark this roll fully complete");
	if (roll.repack_se)
		_btn($c, "View Repack SE", "default", () => frappe.set_route("Form", "Stock Entry", roll.repack_se));
}


function _split_beam_dialog(frm) {
	const total_qty = frm.doc.total_qty || 0;

	const d = new frappe.ui.Dialog({
		title: __("Split Beam into Rolls"),
		size: "large",
		fields: [
			{
				fieldname: "split_rows", fieldtype: "Table", label: __("Split Rows"),
				reqd: 1,
				// This Dialog has no frm, so grid.js reads this inline `fields`
				// array directly (grid.js:571) instead of the child doctype's
				// meta — mirrors DESAR Beam Split Row's own field definitions.
				fields: [
					{ fieldname: "qty_to_split", fieldtype: "Int", label: __("No. of Rolls"), in_list_view: 1, reqd: 1, default: 1, read_only: 1 },
					{ fieldname: "pieces_per_split", fieldtype: "Int", label: __("Pieces per Roll"), in_list_view: 1, reqd: 1 },
				],
				data: [{ qty_to_split: 1, pieces_per_split: total_qty }],
			},
			{ fieldname: "split_summary", fieldtype: "HTML" },
		],
		primary_action_label: __("Split"),
		primary_action() {
			// disable_primary_action() only adds a CSS class — it does not
			// stop the click handler from running. This guard is the real
			// block; the CSS class is just the visual signal.
			if (!_split_rows_valid(d, total_qty)) return;
			const rows = _split_dialog_rows(d);
			d.hide();
			frappe.call({
				method: "desar_manufacturing.api.production_order.split_beam",
				args: { production_order: frm.doc.name, rows: JSON.stringify(rows) },
				freeze: true, freeze_message: __("Splitting beam..."),
				callback(r) {
					if (r.exc) return;
					_show_split_result(r.message || {});
					frm.reload_doc();
				},
			});
		},
	});

	const refresh_summary = () => {
		_render_split_summary(d, total_qty);
		if (_split_rows_valid(d, total_qty)) {
			d.enable_primary_action();
		} else {
			d.disable_primary_action();
		}
	};
	d.fields_dict.split_rows.grid.wrapper.on(
		"change click", "input, select, .grid-add-row, .grid-remove-rows, .grid-remove-all-rows",
		() => setTimeout(refresh_summary, 50));
	d.show();
	refresh_summary();
}


function _split_rows_valid(d, total_qty) {
	const rows = d.fields_dict.split_rows.grid.get_data() || [];
	if (!rows.length) return false;
	// Every row's "No. of Rolls" and "Pieces per Roll" must actually be
	// filled in (a blank/zero Pieces per Roll — e.g. right after Add Row,
	// before the user has typed a value — must block Split, not silently
	// count as zero pieces).
	const all_filled = rows.every(r => cint(r.qty_to_split) > 0 && cint(r.pieces_per_split) > 0);
	if (!all_filled) return false;
	const pieces = rows.reduce((sum, r) => sum + cint(r.qty_to_split) * cint(r.pieces_per_split), 0);
	return pieces === total_qty;
}


function _split_dialog_rows(d) {
	return (d.fields_dict.split_rows.grid.get_data() || []).map(r => ({
		qty_to_split: r.qty_to_split, pieces_per_split: r.pieces_per_split,
	}));
}


function _render_split_summary(d, total_qty) {
	const rows = d.fields_dict.split_rows.grid.get_data() || [];
	const rolls = rows.reduce((sum, r) => sum + cint(r.qty_to_split), 0);
	const pieces = rows.reduce((sum, r) => sum + cint(r.qty_to_split) * cint(r.pieces_per_split), 0);
	const ok = pieces === total_qty;

	d.fields_dict.split_summary.$wrapper.html(`
		<div style="padding:8px 0; font-weight:600; color:${ok ? "#166534" : "#991b1b"};">
			${__("Rolls")}: ${rolls} &nbsp;|&nbsp; ${__("Pieces")}: ${pieces} / ${total_qty}
			${ok ? " ✓" : ""}
		</div>
	`);
}


function _show_split_result(res) {
	const plan_html = (res.roll_plan || [])
		.map(rp => __("Roll {0}: {1} pcs", [rp.roll_no, rp.planned_qty]))
		.join("<br>");
	frappe.msgprint(
		__("Beam split into {0} rolls.<br>{1}", [res.roll_count, plan_html]),
		__("Beam Split Complete"));
}


function _call(frm, method, args) {
	frappe.call({
		method: "desar_manufacturing.api.production_order." + method,
		args: Object.assign({ production_order: frm.doc.name }, args),
		freeze: true, freeze_message: __("Processing..."),
		callback(r) {
			if (r.exc) return;
			const msg = (r.message || {}).message;
			if (msg) frappe.show_alert({ message: msg, indicator: "blue" }, 6);
			frm.reload_doc();
		},
	});
}

function _roll_call(frm, method, roll_no) {
	frappe.call({
		method: "desar_manufacturing.api.production_order." + method,
		args: { production_order: frm.doc.name, roll_no },
		freeze: true, freeze_message: __("Processing Roll {0}...", [roll_no]),
		callback(r) {
			if (r.exc) return;
			const msg = (r.message || {}).message;
			if (msg) frappe.show_alert({ message: msg, indicator: "blue" }, 6);
			frm.reload_doc();
		},
	});
}

function _refresh_roll(frm, roll_no) {
	frappe.call({
		method: "desar_manufacturing.api.production_order.refresh_roll",
		args: { production_order: frm.doc.name, roll_no },
		callback(r) { if (!r.exc) frm.reload_doc(); },
	});
}

// Mirrors roll_service._validate_job_cards — the server throws if any Job
// Card for this work order isn't Completed, so don't pulse "Complete X"
// (implying it's the next click) while that would just error.
function _job_cards_pending(frm, work_order) {
	if (!work_order) return false;
	const cards = (frm.dashboard_job_cards && frm.dashboard_job_cards[work_order]) || [];
	return cards.some(jc => jc.status !== "Completed");
}

function _qi_submitted(frm, qi_name) {
	if (frm.dashboard_qis && frm.dashboard_qis[qi_name]) {
		return frm.dashboard_qis[qi_name].docstatus === 1;
	}
	return true;
}

function _btn($c, label, type, fn, hint) {
	const cls = type === "primary" ? "btn-primary" : "btn-default";
	const $btn = $(`<button class="btn btn-xs ${cls}" style="margin-left:5px;">${__(label)}</button>`)
		.on("click", fn).appendTo($c);
	if (type === "primary") {
		$btn.addClass("desar-pulse");
		if (hint) $btn.attr("title", __(hint));
	}
}

// Highlights a dropdown-grouped frm.add_custom_button entry the same way
// _btn() highlights inline roll buttons — pulse + hover hint.
function _pulse_custom_button($el, hint) {
	if (!$el || !$el.length) return;
	$el.addClass("desar-pulse");
	if (hint) $el.attr("title", __(hint));
}

function _next_step_message(frm) {
	if (frm.doc.warping_status === "Not Started") {
		return { message: __("Next: click <b>Start Warping</b> (under the Warping menu above) to begin."), color: "blue" };
	}
	if (frm.doc.warping_status === "In Progress") {
		if (frm.doc.warping_transfer_se && !frm.doc.warping_manufacture_se) {
			return { message: __("Next: submit the Warping Transfer SE, then click <b>Complete Warping</b>."), color: "blue" };
		}
		return { message: __("Warping in progress — waiting on the Transfer SE."), color: "blue" };
	}
	if (frm.doc.beam_split_status !== "Completed") {
		return { message: __("Next: click <b>Split Beam</b> (under the Beam Split menu above) to divide this batch into rolls."), color: "blue" };
	}

	const rolls = frm.doc.roll_chains || [];
	const pending = rolls.find(r => r.roll_status !== "Completed");
	if (!pending) {
		return { message: __("All stages complete."), color: "green" };
	}
	return { message: __("Next: Roll {0} — {1}", [pending.roll_no, _roll_next_action_label(frm, pending)]), color: "blue" };
}

function _roll_next_action_label(frm, roll) {
	if (roll.grey_roll_status === "Not Started") return __("click Start Grey Roll.");
	if (roll.grey_roll_status === "In Progress" && !roll.grey_roll_qi) {
		return _job_cards_pending(frm, roll.grey_roll_wo)
			? __("complete its open Job Card(s), then click Complete Grey Roll.")
			: __("click Complete Grey Roll.");
	}
	if (roll.grey_roll_status === "In Progress" && roll.grey_roll_qi) return __("submit its Grey Roll Quality Inspection.");

	if (roll.finished_roll_status === "Not Started") return __("click Start Finished Roll.");
	if (roll.finished_roll_status === "In Progress" && !roll.finished_roll_qi) {
		return _job_cards_pending(frm, roll.finished_roll_wo)
			? __("complete its open Job Card(s), then click Complete Finished Roll.")
			: __("click Complete Finished Roll.");
	}
	if (roll.finished_roll_status === "In Progress" && roll.finished_roll_qi) return __("submit its Finished Roll Quality Inspection.");

	if (roll.packing_status === "Not Started") return __("click Start Packing.");
	if (roll.packing_status === "In Progress" && !roll.packing_manufacture_se) {
		return _job_cards_pending(frm, roll.packing_wo)
			? __("complete its open Job Card(s), then click Complete Packing.")
			: __("click Complete Packing.");
	}
	if (roll.packing_status === "In Progress" && roll.packing_manufacture_se && !roll.packing_qi) return __("click Create Inspection.");
	if (roll.packing_status === "In Progress" && roll.packing_qi) {
		return _qi_submitted(frm, roll.packing_qi)
			? __("click Complete Roll.")
			: __("submit its Packing Quality Inspection.");
	}

	return __("finish its remaining stage.");
}

function _status_icon(s) {
	return { Completed:"✅", "In Progress":"🔄", "Not Started":"⚪", Locked:"🔒" }[s] || "⚪";
}
function _status_color(s) {
	return { Completed:"#28a745", "In Progress":"#007bff", "Not Started":"#6c757d", Locked:"#ced4da" }[s] || "#ced4da";
}
