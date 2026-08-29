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

		_desar_simplify_form(frm, {
			hide_all: [
				"naming_series", "inspection_type", "reference_type", "reference_name",
				"item_serial_no", "bom_no", "verified_by", "amended_from", "manual_inspection",
				"child_row_reference", "company", "letter_head", "readings",
			],
			readonly_all: [
				"item_code", "batch_no", "inspected_by", "report_date",
				"quality_inspection_template", "sample_size",
			],
		});
		_desar_apply_grade_readings_readonly(frm);

		_desar_fetch_baseline(frm, () => _desar_prefill_if_fresh(frm));
		_desar_show_production_order_link(frm);
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


function _desar_show_production_order_link(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "desar_manufacturing.api.production_order.find_production_order_for_quality_inspection",
		args: { quality_inspection: frm.doc.name },
		callback({ message: po }) {
			if (!po) return;
			frm.add_custom_button(__("Back to Production Order"), () => {
				frappe.set_route("Form", "DESAR Production Order", po);
			}, __("DESAR"));
			frm.set_intro(
				__("This Quality Inspection belongs to Production Order {0}.",
					[`<a href="/app/desar-production-order/${po}">${po}</a>`]),
				"blue"
			);
		}
	});
}


function _desar_is_packing(frm) {
	return frm.doc.custom_desar_stage_name === "Packing" && !!frm.doc.custom_roll_ticket;
}


function _desar_apply_grade_readings_readonly(frm) {
	// Once any Grade Adjustment row exists on a Packing-stage QI, qty on
	// custom_desar_grade_readings is auto-recomputed by _desar_recompute() —
	// a floor worker should never hand-edit a number the system is about to
	// overwrite. Cosmetic only, not gated by role: this is true for every user.
	const grid = frm.fields_dict.custom_desar_grade_readings &&
		frm.fields_dict.custom_desar_grade_readings.grid;
	if (!grid) return;
	const should_be_readonly = _desar_is_packing(frm) &&
		(frm.doc.custom_desar_grade_adjustments || []).length > 0;
	grid.update_docfield_property("qty", "read_only", should_be_readonly ? 1 : 0);
	frm.refresh_field("custom_desar_grade_readings");
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
	_desar_apply_grade_readings_readonly(frm);
}
