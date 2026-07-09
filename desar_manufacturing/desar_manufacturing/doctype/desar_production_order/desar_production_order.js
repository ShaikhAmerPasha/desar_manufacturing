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
`;

frappe.ui.form.on("DESAR Production Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		// Inject styles once
		if (!$("style#desar-dashboard-styles").length) {
			$("<style id='desar-dashboard-styles'>").text(styles).appendTo("head");
		}

		frm.trigger("render_warping_actions");
		frm.trigger("render_beam_split_actions");
		frm.trigger("load_and_render_dashboard");
	},

	render_warping_actions(frm) {
		const s = frm.doc.warping_status;
		if (s === "Not Started") {
			frm.add_custom_button(__("Start Warping"), () => _call(frm, "start_warping", {}), __("Warping"));
		} else if (s === "In Progress" && frm.doc.warping_transfer_se && !frm.doc.warping_manufacture_se) {
			frm.add_custom_button(__("Complete Warping"), () => _call(frm, "complete_warping", {}), __("Warping"));
			frm.add_custom_button(__("View Transfer SE"), () =>
				frappe.set_route("Form", "Stock Entry", frm.doc.warping_transfer_se), __("Warping"));
		}
	},

	render_beam_split_actions(frm) {
		if (frm.doc.warping_status !== "Completed") return;
		if (frm.doc.beam_split_status === "Completed") return;
		frm.add_custom_button(__("Split Beam"), () => _split_beam_dialog(frm), __("Beam Split"));
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
		}).catch(err => {
			console.error("Error loading dashboard data:", err);
			frm.trigger("render_warping_dashboard");
			frm.trigger("render_roll_chains");
		});
	},

	render_warping_dashboard(frm) {
		const $wrapper = frm.fields_dict["warping_wo"].$wrapper;
		$wrapper.empty().show();

		const wo = frm.doc.warping_wo;
		const batch = frm.doc.warping_batch;
		const status = frm.doc.warping_status;
		const transfer_se = frm.doc.warping_transfer_se;
		const manufacture_se = frm.doc.warping_manufacture_se;

		const job_cards = (frm.dashboard_job_cards && frm.dashboard_job_cards[wo]) || [];
		const stock_entries = (frm.dashboard_stock_entries && frm.dashboard_stock_entries[wo]) || [];

		const is_completed = status === "Completed";
		const display_style = is_completed ? "none" : "block";
		const toggle_icon = is_completed ? "▶" : "▼";

		let job_cards_html = "";
		if (job_cards.length) {
			job_cards_html = `<div style="margin-top: 8px;">
				<strong>Job Cards:</strong><br>
				<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:4px;">
					${job_cards.map(jc => {
						const badge = _badge(`${jc.operation}: ${jc.status}`, jc.status);
						return `<a href="${frappe.utils.get_form_link("Job Card", jc.name)}" target="_blank">${badge}</a>`;
					}).join("")}
				</div>
			</div>`;
		} else if (wo) {
			job_cards_html = `<div style="margin-top: 8px; color:#6c757d;">No Job Cards found for this Work Order.</div>`;
		}

		let stock_entries_html = "";
		const se_links = [];
		if (transfer_se) {
			se_links.push({ name: transfer_se, type: "Transfer Stock Entry", label: "Transfer SE", docstatus: 1 });
		}
		if (manufacture_se) {
			se_links.push({ name: manufacture_se, type: "Manufacture Stock Entry", label: "Manufacture SE", docstatus: 1 });
		}
		stock_entries.forEach(se => {
			if (se.name !== transfer_se && se.name !== manufacture_se) {
				const is_mfg = se.purpose === "Manufacture" || se.stock_entry_type === "Manufacture";
				se_links.push({
					name: se.name,
					type: is_mfg ? "Manufacture Stock Entry" : "Transfer Stock Entry",
					label: is_mfg ? "Manufacture SE" : "Transfer SE",
					docstatus: se.docstatus
				});
			}
		});

		if (se_links.length) {
			stock_entries_html = `<div style="margin-top: 8px;">
				<strong>Stock Entries:</strong><br>
				<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:4px;">
					${se_links.map(se => {
						const docstatus_label = se.docstatus === 1 ? "Submitted" : (se.docstatus === 0 ? "Draft" : "Cancelled");
						const badge = _badge(`${se.label}: ${se.name} (${docstatus_label})`, docstatus_label);
						return `<a href="${frappe.utils.get_form_link("Stock Entry", se.name)}" target="_blank">${badge}</a>`;
					}).join("")}
				</div>
			</div>`;
		}

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
					<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:16px;">
						<div>
							<strong>Work Order:</strong><br>
							${wo ? `<a href="${frappe.utils.get_form_link("Work Order", wo)}" target="_blank" class="desar-link" style="font-size:14px; font-weight:600;">${wo}</a>` : `<span style="color:#6c757d;">Not Created</span>`}
							${job_cards_html}
						</div>
						<div>
							${stock_entries_html}
						</div>
					</div>
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

		// Event delegation for submitting SE
		$wrap.on("click", ".btn-submit-se", function(e) {
			e.preventDefault();
			e.stopPropagation();
			const se_name = $(this).data("se");
			frappe.confirm(
				__("Are you sure you want to submit Stock Entry {0}?", [se_name]),
				function() {
					frappe.call({
						method: "frappe.client.submit",
						args: {
							doc: {
								doctype: "Stock Entry",
								name: se_name
							}
						},
						freeze: true,
						freeze_message: __("Submitting Stock Entry..."),
						callback(r) {
							if (!r.exc) {
								frappe.show_alert({message: __("Stock Entry submitted successfully"), indicator: "green"});
								frm.reload_doc();
							}
						}
					});
				}
			);
		});

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

	let qi_html = "";
	if (qi_no) {
		const qi_doc = (frm.dashboard_qis && frm.dashboard_qis[qi_no]) || {};
		let qi_status = qi_doc.status || "Draft";
		if (qi_doc.docstatus === 1) {
			qi_status = qi_doc.status === "Accepted" ? "Accepted" : "Rejected";
		} else if (qi_doc.docstatus === 0) {
			qi_status = "Draft";
		}
		const badge = _badge(`QI: ${qi_no} (${qi_status})`, qi_status);
		qi_html = `<a href="${frappe.utils.get_form_link("Quality Inspection", qi_no)}" target="_blank" style="margin-left:8px;">${badge}</a>`;
	}

	let job_cards_html = "";
	if (job_cards.length) {
		job_cards_html = `
			<div style="margin-top: 6px;">
				<strong>Job Cards:</strong>
				<div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:2px;">
					${job_cards.map(jc => {
						const badge = _badge(`${jc.operation}: ${jc.status}`, jc.status);
						return `<a href="${frappe.utils.get_form_link("Job Card", jc.name)}" target="_blank">${badge}</a>`;
					}).join("")}
				</div>
			</div>
		`;
	} else if (wo) {
		job_cards_html = `<div style="margin-top: 6px; color:#8c95a5; font-size:11px;">No Job Cards</div>`;
	}

	let se_html = "";
	const se_list = [];

	stock_entries.forEach(se => {
		const is_mfg = se.purpose === "Manufacture" || se.stock_entry_type === "Manufacture" || (stage_key === "packing" && se.name === frm.doc.packing_manufacture_se);
		se_list.push({
			name: se.name,
			is_mfg: is_mfg,
			label: is_mfg ? "Manufacture SE" : "Transfer SE",
			docstatus: se.docstatus
		});
	});

	if (stage_key === "packing" && frm.doc.packing_manufacture_se) {
		if (!se_list.some(s => s.name === frm.doc.packing_manufacture_se)) {
			se_list.push({
				name: frm.doc.packing_manufacture_se,
				is_mfg: true,
				label: "Manufacture SE",
				docstatus: 0
			});
		}
	}

	if (se_list.length) {
		se_html = `
			<div style="margin-top: 6px;">
				<strong>Stock Entries:</strong>
				<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:2px;">
					${se_list.map(se => {
						const docstatus_label = se.docstatus === 1 ? "Submitted" : (se.docstatus === 0 ? "Draft" : "Cancelled");
						let badge_label = `${se.label}: ${se.name} (${docstatus_label})`;
						let badge = _badge(badge_label, docstatus_label);
						
						let submit_btn = "";
						if (stage_key === "packing" && se.is_mfg && se.docstatus === 0) {
							submit_btn = `<button class="btn btn-xs btn-primary btn-submit-se" data-se="${se.name}" style="padding: 1px 5px; font-size: 10px; margin-left: 4px; line-height: 1.2;">Submit SE</button>`;
						}
						
						return `
							<div style="display:inline-flex; align-items:center; margin-bottom: 2px;">
								<a href="${frappe.utils.get_form_link("Stock Entry", se.name)}" target="_blank">${badge}</a>
								${submit_btn}
							</div>
						`;
					}).join("")}
				</div>
			</div>
		`;
	} else if (wo) {
		se_html = `<div style="margin-top: 6px; color:#8c95a5; font-size:11px;">No Stock Entries</div>`;
	}

	const header_bg = is_completed ? "#f8fafc" : `${color}06`;

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
				<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px;">
					<div>
						<strong>Work Order:</strong><br>
						${wo ? `<a href="${frappe.utils.get_form_link("Work Order", wo)}" target="_blank" class="desar-link" style="font-weight:600;">${wo}</a>` : `<span style="color:#6c757d;">Not Created</span>`}
						${job_cards_html}
					</div>
					<div>
						${se_html}
					</div>
				</div>
			</div>
		</div>
	`;
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
		_btn($c, "Start Grey Roll", "primary", () => _roll_call(frm, "start_grey_roll", rn));
	if (roll.grey_roll_status === "In Progress" && !roll.grey_roll_qi)
		_btn($c, "Complete Grey Roll", "primary", () => _roll_call(frm, "complete_grey_roll", rn));
	if (roll.grey_roll_status === "In Progress" && roll.grey_roll_qi)
		_btn($c, "Refresh", "default", () => _refresh_roll(frm, rn));

	// Finished Roll
	if (roll.finished_roll_status === "Not Started" && roll.grey_roll_status === "Completed")
		_btn($c, "Start Finished Roll", "primary", () => _roll_call(frm, "start_finished_roll", rn));
	if (roll.finished_roll_status === "In Progress" && !roll.finished_roll_qi)
		_btn($c, "Complete Finished Roll", "primary", () => _roll_call(frm, "complete_finished_roll", rn));
	if (roll.finished_roll_status === "In Progress" && roll.finished_roll_qi)
		_btn($c, "Refresh", "default", () => _refresh_roll(frm, rn));

	// Packing
	if (roll.packing_status === "Not Started" && roll.finished_roll_status === "Completed")
		_btn($c, "Start Packing", "primary", () => _roll_call(frm, "start_packing", rn));
	if (roll.packing_status === "In Progress" && !roll.packing_manufacture_se)
		_btn($c, "Complete Packing", "primary", () => _roll_call(frm, "complete_packing", rn));
	if (roll.packing_status === "In Progress" && roll.packing_manufacture_se && !roll.packing_qi)
		_btn($c, "Create Inspection", "primary", () => _roll_call(frm, "finalize_packing", rn));
	if (roll.packing_status === "In Progress" && roll.packing_qi)
		_btn($c, "Refresh", "default", () => _refresh_roll(frm, rn));
	if (roll.packing_status === "In Progress" && roll.packing_qi && _qi_submitted(frm, roll.packing_qi))
		_btn($c, "Complete Roll", "primary", () => _roll_call(frm, "complete_roll", rn));
}


function _split_beam_dialog(frm) {
	const suggested = frm.doc.pieces_per_roll
		? Math.ceil(frm.doc.total_qty / frm.doc.pieces_per_roll) : 2;
	const d = new frappe.ui.Dialog({
		title: __("Split Beam into Rolls"),
		fields: [{
			fieldname: "roll_count", fieldtype: "Int",
			label: __("Number of Rolls"), reqd: 1, default: suggested,
			description: __("Each roll = one loom run. Suggested: {0}", [suggested]),
		}],
		primary_action_label: __("Split"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "desar_manufacturing.api.production_order.split_beam",
				args: { production_order: frm.doc.name, roll_count: values.roll_count },
				freeze: true, freeze_message: __("Splitting beam..."),
				callback(r) {
					if (r.exc) return;
					const res = r.message || {};
					frappe.msgprint(
						__("Beam split into {0} rolls. Batches: {1}",
							[res.roll_count, (res.beam_roll_batches || []).join(", ")]),
						__("Beam Split Complete"));
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
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

function _qi_submitted(frm, qi_name) {
	if (frm.dashboard_qis && frm.dashboard_qis[qi_name]) {
		return frm.dashboard_qis[qi_name].docstatus === 1;
	}
	return true;
}

function _btn($c, label, type, fn) {
	const cls = type === "primary" ? "btn-primary" : "btn-default";
	$(`<button class="btn btn-xs ${cls}" style="margin-left:5px;">${__(label)}</button>`)
		.on("click", fn).appendTo($c);
}

function _status_icon(s) {
	return { Completed:"✅", "In Progress":"🔄", "Not Started":"⚪", Locked:"🔒" }[s] || "⚪";
}
function _status_color(s) {
	return { Completed:"#28a745", "In Progress":"#007bff", "Not Started":"#6c757d", Locked:"#ced4da" }[s] || "#ced4da";
}
