// DESAR Production Plan — Client Script v7
// v7: a Sales Order with multiple design lines can land in one combined
// Production Plan. list_plan_designs() finds every design on this plan;
// one DESAR Production Order gets created per design, not just one for
// the whole plan.

frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(__("Create DESAR Production Order"), function() {
			create_desar_production_orders(frm);
		}, __("DESAR"));
	},
});

async function create_desar_production_orders(frm) {
	const designs_res = await frappe.call({
		method: "desar_manufacturing.api.production_order.list_plan_designs",
		args: { production_plan: frm.doc.name },
	});
	const designs = designs_res.message || [];

	if (!designs.length) {
		frappe.msgprint({
			title: __("Cannot Create"),
			message: __("Cannot determine Design Master. Set custom_design_master on at least one Work Order."),
			indicator: "red",
		});
		return;
	}

	const previews = await Promise.all(designs.map((design_master) =>
		frappe.call({
			method: "desar_manufacturing.api.production_order.preview_plan",
			args: { production_plan: frm.doc.name, design_master },
		}).then((r) => ({ design_master, preview: r.message || {} }))
	));

	const pending = previews.filter((p) => !p.preview.error && !p.preview.already_exists);
	const skipped = previews.filter((p) => p.preview.error || p.preview.already_exists);

	if (!pending.length) {
		frappe.msgprint({
			title: __("Already Exists"),
			message: __("Every design on this Production Plan already has a DESAR Production Order."),
			indicator: "orange",
		});
		return;
	}

	const rows = pending
		.map((p) => `<li><b>${p.preview.article_name} (${p.preview.design_no})</b> — ${p.preview.total_qty} pcs</li>`)
		.join("");
	const skipped_note = skipped.length
		? `<br><i>${__("Skipping {0} design(s) that already have one.", [skipped.length])}</i>`
		: "";

	frappe.confirm(
		__("Create {0} DESAR Production Order(s)?<ul>{1}</ul>{2}", [pending.length, rows, skipped_note]),
		async function() {
			frappe.dom.freeze(__("Creating DESAR Production Orders..."));
			const created = [];
			const failed = [];
			for (const p of pending) {
				try {
					const r = await frappe.call({
						method: "desar_manufacturing.api.production_order.create_desar_po",
						args: { production_plan: frm.doc.name, design_master: p.design_master },
					});
					created.push(r.message);
				} catch (e) {
					failed.push(p.preview.article_name || p.design_master);
				}
			}
			frappe.dom.unfreeze();

			frappe.show_alert({
				message: __("Created {0} DESAR Production Order(s){1}", [
					created.length,
					failed.length ? __(" — {0} failed", [failed.length]) : "",
				]),
				indicator: failed.length ? "orange" : "green",
			}, 8);

			if (created.length === 1) {
				frappe.set_route("Form", "DESAR Production Order", created[0].production_order);
			} else if (created.length > 1) {
				frappe.set_route("List", "DESAR Production Order", { production_plan: frm.doc.name });
			}
		}
	);
}
