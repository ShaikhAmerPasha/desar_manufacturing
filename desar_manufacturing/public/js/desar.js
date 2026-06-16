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
     * Dynamic QI buttons are added by the second handler below.
     * Legacy fallback is handled inside _desar_load_stage_config callback.
     */
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;
        // QI buttons are handled by dynamic handler at bottom of file
        // which falls back to legacy if no Stage Configuration found
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

        const stages = frm.doc.stage_configuration || [];

        if (stages.length > 0) {
            // Dynamic mode — check which stages are missing BOMs
            const missing = stages.filter(s => !s.bom_no).map(s => s.stage_name);
            const total = stages.length;
            const done = total - missing.length;

            if (missing.length > 0) {
                frm.add_custom_button(__("Create All BOMs"), () => {
                    _desar_create_all_boms(frm, total);
                }, __("DESAR"));
                frm.set_intro(
                    __("Missing BOMs for stages: {0}. Click 'Create All BOMs'.", [missing.join(", ")]),
                    "orange"
                );
            } else {
                frm.set_intro(
                    __("All {0} BOMs created in Draft. Review and submit each BOM.", [total]),
                    "green"
                );
            }
        } else {
            // Legacy mode — check bom_level_1/2/3/4
            const has_all_boms = (
                frm.doc.bom_level_1 &&
                frm.doc.bom_level_2 &&
                frm.doc.bom_level_3 &&
                frm.doc.bom_level_4
            );

            if (!has_all_boms) {
                frm.add_custom_button(__("Create All BOMs"), () => {
                    _desar_create_all_boms(frm, 4);
                }, __("DESAR"));

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
                frm.set_intro(__("All 4 BOMs created in Draft. Review and submit each BOM."), "green");
            }
        }
    },

});


function _desar_create_all_boms(frm, stage_count) {
    frappe.confirm(
        __("Create all {0} BOMs for Design Master {1}?", [stage_count, frm.doc.name]),
        () => {
            _desar_call(
                DESAR.API.CREATE_BOMS,
                { design_master: frm.doc.name },
                () => {
                    frappe.show_alert({
                        message: __("BOMs created in Draft — please review and submit each BOM"),
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

    // Stage grades are now dynamic — totals computed server-side
    // Old static grey_qty_a/b/c, finished_qty_a/b/c, cutted_qty_a/b/c removed v3.0

});





// ═══════════════════════════════════════════════════════════════════════════════
// DYNAMIC QI BUTTONS — reads Stage Configuration from Design Master
// Replaces hardcoded GREY_ROLL/FINISHED_ROLL/Shemagh checks
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Load stage configuration for the Work Order's Design Master.
 * Returns array of stages with qi_required=1.
 * Falls back to legacy buttons if no stage config found.
 */
function _desar_load_stage_config(frm, callback) {
    const design_master = frm.doc.custom_design_master;
    if (!design_master) {
        callback(null);
        return;
    }

    frappe.call({
        method: "desar_manufacturing.api.manufacturing.get_stage_configuration",
        args: { design_master },
        callback({ message }) {
            callback(message || []);
        },
        error() { callback(null); }
    });
}

/**
 * Add dynamic QI button for the stage matching this Work Order's production item.
 *
 * Key rule: Each Work Order produces ONE item → matches ONE stage in Stage Config.
 * Only show the QI button for THAT stage.
 *
 * e.g. Grey Roll WO → matches Weaving stage (output_item=Grey Roll) → shows
 *      "Create Grey Inspection" (label = "Create {output_item} Inspection")
 *
 * No button shown if:
 * - Stage has qi_required=0 (e.g. Warping stage)
 * - No Manufacture SE exists yet (WO not finished)
 * - Production item does not match any stage
 */
function _desar_add_dynamic_qi_buttons(frm, stages) {
    const production_item = frm.doc.production_item;
    if (!production_item) return;

    // Find the stage that matches this WO's production item
    const matching_stage = stages.find(s => s.output_item === production_item);
    if (!matching_stage) {
        // No matching stage — fallback to legacy
        _desar_maybe_add_qi_button(frm);
        return;
    }

    // Stage found but QI not required (e.g. Warping Beam)
    if (!matching_stage.qi_required) return;

    // Only show button if Manufacture SE exists
    frappe.db.count("Stock Entry", {
        work_order: frm.doc.name,
        stock_entry_type: "Manufacture",
        docstatus: 1,
    }).then(count => {
        if (!count) return;

        // Label: "Create {output_item} Inspection"
        // e.g. "Create Grey Roll Inspection" or "Create Shemagh-VIC-60-A Inspection"
        const label = __("Create {0} Inspection", [matching_stage.output_item]);

        frm.add_custom_button(label, () => {
            frappe.confirm(
                __("Create Quality Inspection for {0}?", [matching_stage.stage_name]),
                () => {
                    _desar_call(
                        "desar_manufacturing.api.manufacturing.create_quality_inspection_dynamic",
                        { work_order: frm.doc.name, stage_name: matching_stage.stage_name },
                        (qi_name) => {
                            frappe.show_alert({
                                message: __("QI {0} created", [qi_name]),
                                indicator: "green",
                            });
                            frappe.set_route("Form", "Quality Inspection", qi_name);
                        }
                    );
                }
            );
        }, __("DESAR QC"));
    });
}

// Override the refresh handler to try dynamic first, fallback to legacy
const _original_wo_refresh = frappe.ui.form.on;

frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;

        // Try dynamic stage config first
        _desar_load_stage_config(frm, (stages) => {
            if (stages && stages.length > 0) {
                _desar_add_dynamic_qi_buttons(frm, stages);
            } else {
                // Fallback to legacy buttons
                _desar_maybe_add_qi_button(frm);
            }
        });
    },
});