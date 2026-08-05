// DESAR Quality Inspection — Packing grade sync from Finishing baseline

frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		// DESAR Roll Chain (child table on DESAR Production Order) links back to
		// this QI via grey_roll_qi/finished_roll_qi/packing_qi — Frappe's generic
		// "linked with submitted documents" check finds that Link and forces a
		// cascade cancel of the whole Production Order just to cancel one QI.
		// Same fix ERPNext itself uses for Sales Invoice/Payment Entry/Journal
		// Entry against their own submittable links — this only affects the
		// confirmation dialog, not permissions or the actual cancel/amend logic
		// (events/quality_inspection.py::on_cancel already reverts Roll Ticket/
		// Roll Chain state correctly for a standalone QI cancel).
		frm.ignore_doctypes_on_cancel_all = ["DESAR Production Order"];
		_desar_fetch_baseline(frm, () => _desar_prefill_if_fresh(frm));
	},

	quality_inspection_template(frm) {
		// Re-pull the Finishing baseline and re-apply grade movement — overwrites
		// whatever the inspector typed into Grade A/B/C, per user's explicit choice.
		_desar_fetch_baseline(frm, () => _desar_recompute(frm));
	},

	custom_desar_grade_adjustments_remove(frm) {
		_desar_recompute(frm);
	},
});

frappe.ui.form.on("DESAR Grade Adjustment", {
	from_grade(frm) { _desar_recompute(frm); },
	to_grade(frm) { _desar_recompute(frm); },
	qty(frm) { _desar_recompute(frm); },
});


function _desar_is_packing(frm) {
	return frm.doc.custom_desar_stage_name === "Packing" && !!frm.doc.custom_roll_ticket;
}


function _desar_fetch_baseline(frm, then_fn) {
	if (!_desar_is_packing(frm)) return;
	frappe.call({
		method: "desar_manufacturing.api.manufacturing.get_finishing_grade_baseline",
		args: { roll_ticket: frm.doc.custom_roll_ticket },
		callback(r) {
			frm._desar_finishing_baseline = r.message || {};
			then_fn();
		},
	});
}


function _desar_prefill_if_fresh(frm) {
	// Only pre-fill on a fresh QI — don't clobber counts the inspector already typed.
	const readings = frm.doc.custom_desar_grade_readings || [];
	if (!readings.length || !readings.every(r => !r.qty)) return;
	readings.forEach(r => {
		const base = frm._desar_finishing_baseline[r.grade_code];
		if (base !== undefined) frappe.model.set_value(r.doctype, r.name, "qty", base);
	});
	frm.refresh_field("custom_desar_grade_readings");
}


function _desar_recompute(frm) {
	// Mirrors events/quality_inspection.py::_validate_adjustment_quantities exactly —
	// keep both in sync if the reconciliation math ever changes.
	if (!frm._desar_finishing_baseline) return;
	const expected = Object.assign({}, frm._desar_finishing_baseline);
	(frm.doc.custom_desar_grade_adjustments || []).forEach(adj => {
		if (!adj.from_grade || !adj.to_grade || !adj.qty) return;
		expected[adj.from_grade] = (expected[adj.from_grade] || 0) - flt(adj.qty);
		expected[adj.to_grade] = (expected[adj.to_grade] || 0) + flt(adj.qty);
	});
	(frm.doc.custom_desar_grade_readings || []).forEach(r => {
		if (expected[r.grade_code] === undefined) return;
		frappe.model.set_value(r.doctype, r.name, "qty", expected[r.grade_code]);
	});
	frm.refresh_field("custom_desar_grade_readings");
}
