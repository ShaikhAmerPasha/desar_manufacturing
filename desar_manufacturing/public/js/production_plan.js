// DESAR Production Plan — Client Script v6

frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(__("Create DESAR Production Order"), function() {
			// Preview first
			frappe.call({
				method: "desar_manufacturing.api.production_order.preview_plan",
				args: { production_plan: frm.doc.name },
				callback(r) {
					if (r.exc) return;
					const p = r.message || {};

					if (p.error) {
						frappe.msgprint({
							title: __("Cannot Create"),
							message: p.error,
							indicator: "red",
						});
						return;
					}

					if (p.already_exists) {
						frappe.msgprint({
							title: __("Already Exists"),
							message: __("DESAR Production Order already exists for this Production Plan."),
							indicator: "orange",
						});
						return;
					}

					frappe.confirm(
						__("Design: <b>{0} ({1})</b><br>Rolls: <b>{2}</b><br>Pieces per Roll: <b>{3}</b><br>Total Qty: <b>{4}</b><br><br>Proceed?",
							[p.article_name, p.design_no, p.roll_count, p.pieces_per_roll, p.total_qty]),
						function() {
							frappe.call({
								method: "desar_manufacturing.api.production_order.create_desar_po",
								args: { production_plan: frm.doc.name },
								freeze: true,
								freeze_message: __("Creating DESAR Production Order..."),
								callback(r) {
									if (r.exc) return;
									const res = r.message || {};
									frappe.show_alert({
										message: __("DESAR Production Order {0} created — {1} rolls, {2} pcs",
											[res.production_order, res.roll_count, res.total_qty]),
										indicator: "green",
									}, 8);
									// Navigate to the new PO
									if (res.production_order) {
										frappe.set_route("Form", "DESAR Production Order", res.production_order);
									}
								},
							});
						}
					);
				},
			});
		}, __("DESAR"));
	},
});
