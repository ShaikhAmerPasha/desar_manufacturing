/**
 * DESAR Manufacturing — Client Scripts v2.3
 *
 * Architecture:
 *   - Each form has its own isolated section
 *   - All private functions prefixed with _desar_
 *   - All API calls through _desar_call() wrapper
 *   - No magic strings — DESAR constants object
 *   - Defensive: checks existence before calling frappe methods
 */

// ── Constants (mirrors Python constants) ─────────────────────────────────────

const DESAR = {
    API: {
        CREATE_QI:   "desar_manufacturing.api.manufacturing.create_quality_inspection",
        CREATE_BOMS: "desar_manufacturing.api.manufacturing.create_boms_from_design",
    },
    STAGE: {
        GREY:       "grey",
        FINISHING:  "finishing",
        FINAL:      "final",
    },
    ITEMS: {
        GREY_ROLL:     "Grey Roll",
        FINISHED_ROLL: "Finished Roll",
    },
    SHEMAGH_PREFIX: "Shemagh",
};


// ── Shared API call wrapper ───────────────────────────────────────────────────

function _desar_call(method, args, on_success, on_error) {
    frappe.call({
        method,
        args,
        freeze: true,
        freeze_message: __("Please wait..."),
        callback({ message }) {
            if (message !== undefined && message !== null) {
                on_success(message);
            }
        },
        error(r) {
            const msg = (r && r.message) || __("An unexpected error occurred. Please try again.");
            if (on_error) {
                on_error(msg);
            } else {
                frappe.msgprint({ title: __("Error"), message: msg, indicator: "red" });
            }
        },
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// WORK ORDER FORM
// ═══════════════════════════════════════════════════════════════════════════════

frappe.ui.form.on("Work Order", {

    /**
     * When BOM is selected on WO:
     * Auto-fill Design No, Article Name, Design Master from BOM custom fields.
     * Only fills if not already set by user.
     */
    bom_no(frm) {
        if (!frm.doc.bom_no) return;

        frappe.db.get_value(
            "BOM",
            frm.doc.bom_no,
            ["custom_design_no", "custom_article_name", "custom_design_master"]
        ).then(({ message: m }) => {
            if (!m) return;
            if (m.custom_design_no     && !frm.doc.custom_design_no)
                frm.set_value("custom_design_no",     m.custom_design_no);
            if (m.custom_article_name  && !frm.doc.custom_article_name)
                frm.set_value("custom_article_name",  m.custom_article_name);
            if (m.custom_design_master && !frm.doc.custom_design_master)
                frm.set_value("custom_design_master", m.custom_design_master);
        });
    },

    /**
     * On form refresh of a SUBMITTED Work Order:
     * Show DESAR QC button group if a Manufacture SE exists.
     * Button type depends on the production item.
     */
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;
        _desar_maybe_add_qi_button(frm);
    },

});


/**
 * Determine the correct QI stage for this Work Order's production item.
 * Returns null if this WO does not need a QI button (e.g. Warping Beam).
 */
function _desar_get_qi_config(production_item) {
    if (!production_item) return null;

    if (production_item === DESAR.ITEMS.GREY_ROLL) {
        return { stage: DESAR.STAGE.GREY, label: __("Create Grey Inspection") };
    }
    if (production_item === DESAR.ITEMS.FINISHED_ROLL) {
        return { stage: DESAR.STAGE.FINISHING, label: __("Create Finishing Inspection") };
    }
    if (production_item.startsWith(DESAR.SHEMAGH_PREFIX)) {
        return { stage: DESAR.STAGE.FINAL, label: __("Create Final Inspection") };
    }
    return null;  // Warping Beam — no QI button needed
}


/**
 * Check if a Manufacture SE exists, then add the QI button.
 * Button is hidden if WO has not been finished yet.
 */
function _desar_maybe_add_qi_button(frm) {
    const config = _desar_get_qi_config(frm.doc.production_item);
    if (!config) return;

    frappe.db.count("Stock Entry", {
        work_order:       frm.doc.name,
        stock_entry_type: "Manufacture",
        docstatus:        1,
    }).then(count => {
        if (!count) return;  // WO not finished — no button yet

        frm.add_custom_button(config.label, () => {
            _desar_create_qi(frm, config.stage, config.label);
        }, __("DESAR QC"));
    });
}


/**
 * Call server to create pre-filled QI, then navigate to it.
 */
function _desar_create_qi(frm, stage, label) {
    frappe.confirm(
        __("Create {0} for Work Order {1}?", [label, frm.doc.name]),
        () => {
            _desar_call(
                DESAR.API.CREATE_QI,
                { work_order: frm.doc.name, stage },
                (qi_name) => {
                    frappe.show_alert({
                        message: __("Quality Inspection {0} created", [qi_name]),
                        indicator: "green",
                    });
                    frappe.set_route("Form", "Quality Inspection", qi_name);
                }
            );
        }
    );
}


// ═══════════════════════════════════════════════════════════════════════════════
// DESIGN MASTER FORM
// ═══════════════════════════════════════════════════════════════════════════════

frappe.ui.form.on("Design Master", {

    refresh(frm) {
        if (frm.is_new()) return;
        if (!frm.doc.is_active) return;

        const has_all_boms = (
            frm.doc.bom_level_1 &&
            frm.doc.bom_level_2 &&
            frm.doc.bom_level_3 &&
            frm.doc.bom_level_4
        );

        if (!has_all_boms) {
            frm.add_custom_button(__("Create All BOMs"), () => {
                _desar_create_all_boms(frm);
            }, __("DESAR"));

            // Show indicator if BOMs are missing
            const missing = [
                !frm.doc.bom_level_1 && "BOM L1 (Warping Beam)",
                !frm.doc.bom_level_2 && "BOM L2 (Grey Roll)",
                !frm.doc.bom_level_3 && "BOM L3 (Finished Roll)",
                !frm.doc.bom_level_4 && "BOM L4 (Shemagh)",
            ].filter(Boolean);

            frm.set_intro(
                __("Missing BOMs: {0}. Click 'Create All BOMs' to auto-create.", [missing.join(", ")]),
                "orange"
            );
        } else {
            frm.set_intro(__("All 4 BOMs are created for this Design Master."), "green");
        }
    },

});


function _desar_create_all_boms(frm) {
    frappe.confirm(
        __("Create all 4 BOMs for Design Master {0}?", [frm.doc.name]),
        () => {
            _desar_call(
                DESAR.API.CREATE_BOMS,
                { design_master: frm.doc.name },
                () => {
                    frappe.show_alert({
                        message: __("BOMs created successfully"),
                        indicator: "green",
                    });
                    frm.reload_doc();
                }
            );
        }
    );
}


// ═══════════════════════════════════════════════════════════════════════════════
// ROLL TICKET FORM
// ═══════════════════════════════════════════════════════════════════════════════

frappe.ui.form.on("Roll Ticket", {

    refresh(frm) {
        _desar_render_grade_summary(frm);
    },

    // Auto-calculate totals in real time as inspector types
    grey_qty_a(frm)     { _desar_calc_total(frm, "grey"); },
    grey_qty_b(frm)     { _desar_calc_total(frm, "grey"); },
    grey_qty_c(frm)     { _desar_calc_total(frm, "grey"); },
    finished_qty_a(frm) { _desar_calc_total(frm, "finished"); },
    finished_qty_b(frm) { _desar_calc_total(frm, "finished"); },
    finished_qty_c(frm) { _desar_calc_total(frm, "finished"); },
    cutted_qty_a(frm)   { _desar_calc_total(frm, "cutted"); },
    cutted_qty_b(frm)   { _desar_calc_total(frm, "cutted"); },
    cutted_qty_c(frm)   { _desar_calc_total(frm, "cutted"); },

});


function _desar_calc_total(frm, prefix) {
    const a = frm.doc[`${prefix}_qty_a`] || 0;
    const b = frm.doc[`${prefix}_qty_b`] || 0;
    const c = frm.doc[`${prefix}_qty_c`] || 0;
    frm.set_value(`${prefix}_total`, a + b + c);
}


/**
 * Render yield % summary in the Final section.
 * Shows Grade A%, Grade B%, Scrap% in green/orange/red.
 */
function _desar_render_grade_summary(frm) {
    const total = frm.doc.cutted_total || 0;
    if (!total) return;

    const pct = (n) => ((n || 0) / total * 100).toFixed(1);
    const a = frm.doc.cutted_qty_a || 0;
    const b = frm.doc.cutted_qty_b || 0;
    const c = frm.doc.cutted_qty_c || 0;

    const html = `
        <div style="padding: 6px 0; font-size: 13px; font-weight: 500;">
            <span style="color: #27ae60;">&#9632; Grade A: ${a} pcs (${pct(a)}%)</span>
            &nbsp;&nbsp;
            <span style="color: #e67e22;">&#9632; Grade B: ${b} pcs (${pct(b)}%)</span>
            &nbsp;&nbsp;
            <span style="color: #e74c3c;">&#9632; Scrap: ${c} pcs (${pct(c)}%)</span>
        </div>
    `;

    // Inject after the section_cutted heading
    const section = frm.fields_dict["section_cutted"];
    if (section && section.wrapper) {
        const existing = section.wrapper.querySelector(".desar-grade-summary");
        if (existing) existing.remove();
        const div = document.createElement("div");
        div.className = "desar-grade-summary";
        div.innerHTML = html;
        section.wrapper.appendChild(div);
    }
}
