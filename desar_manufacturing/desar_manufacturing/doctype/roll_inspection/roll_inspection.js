frappe.ui.form.on("Roll Inspection", {
	roll_ticket: (frm) => load_grade_rows(frm),
	stage: (frm) => load_grade_rows(frm),
});

function load_grade_rows(frm) {
	if (frm.is_new() === false || !frm.doc.roll_ticket || !frm.doc.stage) return;
	frappe.call({
		method: "desar_manufacturing.services.inspection_service.get_grade_rows",
		args: { roll_ticket: frm.doc.roll_ticket, stage: frm.doc.stage },
		callback: ({ message }) => {
			frm.clear_table("opening");
			frm.clear_table("closing");
			message.opening.forEach((row) => frm.add_child("opening", row));
			message.closing.forEach((row) => frm.add_child("closing", row));
			frm.refresh_fields();
		},
	});
}
