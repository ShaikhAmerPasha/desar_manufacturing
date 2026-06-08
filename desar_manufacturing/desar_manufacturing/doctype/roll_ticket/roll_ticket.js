// Roll Ticket client script — DESAR buttons are in desar.js
frappe.ui.form.on("Roll Ticket", {
    validate(frm) {
        // Auto-calculate totals
        frm.set_value("grey_total",
            (frm.doc.grey_qty_a || 0) + (frm.doc.grey_qty_b || 0) + (frm.doc.grey_qty_c || 0));
        frm.set_value("finished_total",
            (frm.doc.finished_qty_a || 0) + (frm.doc.finished_qty_b || 0) + (frm.doc.finished_qty_c || 0));
        frm.set_value("cutted_total",
            (frm.doc.cutted_qty_a || 0) + (frm.doc.cutted_qty_b || 0) + (frm.doc.cutted_qty_c || 0));
    }
});
