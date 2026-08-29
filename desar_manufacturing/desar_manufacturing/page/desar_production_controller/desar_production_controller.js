/**
 * DESAR Production Controller v3.6
 *
 * One page, 4 role-based views:
 *   supervisor  → all orders, stage start buttons, assignment
 *   operator    → only MY assigned job cards, big Start/Complete buttons
 *   qc          → pending inspections list
 *   store       → pending Repack SEs only
 *
 * Mobile-first. Auto-refresh every 15s.
 */

frappe.pages["desar-production-controller"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "Production Controller",
        single_column: true,
    });
    $(wrapper).find(".layout-main").html('<div class="desar-ctrl"></div>');
    const app = new DESARController(wrapper);
    app.init();
    wrapper._desar_ctrl = app;
};

frappe.pages["desar-production-controller"].on_page_show = function(wrapper) {
    const pp = frappe.utils.get_url_arg("pp");
    if (pp && wrapper._desar_ctrl) {
        wrapper._desar_ctrl.show_order(pp);
    }
};


class DESARController {
    constructor(wrapper) {
        this.$w = $(wrapper);
        this.$main = this.$w.find(".desar-ctrl");
        this.role = null;
        this._timer = null;
    }

    init() {
        this._detect_role(() => this._render_home());
    }

    _detect_role(cb) {
        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_current_role",
            callback: (r) => {
                this.role = r.message || "supervisor";
                cb();
            }
        });
    }

    _render_home() {
        clearInterval(this._timer);
        if (this.role === "operator") {
            this._show_operator_view();
        } else if (this.role === "qc") {
            this._show_qc_view();
        } else if (this.role === "store") {
            this._show_store_view();
        } else {
            this.show_list();
        }
    }

    // ══ SUPERVISOR: Order List ══════════════════════════════════════════════

    show_list() {
        clearInterval(this._timer);
        this.$main.html(`
            <div class="dc-header">
                <span class="dc-title">Production Orders</span>
                <button class="btn btn-xs btn-default dc-btn-refresh">↻</button>
            </div>
            <div class="dc-body"><div class="dc-loading">Loading...</div></div>
        `);
        this.$main.find(".dc-btn-refresh").on("click", () => this._load_list());
        this._load_list();
        this._timer = setInterval(() => this._load_list(), 30000);
    }

    _load_list() {
        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_orders",
            callback: (r) => {
                const $b = this.$main.find(".dc-body");
                const orders = r.message || [];
                if (!orders.length) {
                    $b.html('<div class="dc-empty">No active production orders</div>');
                    return;
                }
                $b.html(orders.map(o => this._tpl_order_card(o)).join(""));
                $b.find(".dc-order-card").on("click", (e) => {
                    this.show_order($(e.currentTarget).data("pp"));
                });
            }
        });
    }

    _tpl_order_card(o) {
        const pct = o.total_stages ? Math.round(o.completed_stages / o.total_stages * 100) : 0;
        const bar_color = pct === 100 ? "#27ae60" : pct > 0 ? "#2E86AB" : "#aaa";
        const pills = (o.work_orders || []).map(w => {
            const icon = w.status === "Completed" ? "✅" : w.status === "In Process" ? "⏳" : "○";
            return `<span class="dc-pill">${icon} ${w.stage_name || w.production_item}</span>`;
        }).join("");

        return `
        <div class="dc-order-card" data-pp="${o.production_plan}">
            <div class="dc-order-top">
                <div>
                    <span class="dc-order-name">${o.article_name || o.design_no || "Order"}</span>
                    <span class="dc-order-so">${o.sales_order || o.production_plan}</span>
                </div>
                <span class="dc-pct" style="color:${bar_color}">${pct}%</span>
            </div>
            <div class="dc-progress-bar">
                <div class="dc-progress-fill" style="width:${pct}%;background:${bar_color}"></div>
            </div>
            <div class="dc-pills">${pills}</div>
        </div>`;
    }

    // ══ SUPERVISOR: Order Detail ═══════════════════════════════════════════

    show_order(pp) {
        clearInterval(this._timer);
        this.$main.html('<div class="dc-loading">Loading order...</div>');
        this._load_order(pp);
        this._timer = setInterval(() => this._load_order(pp), 15000);
    }

    _load_order(pp) {
        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_order_detail",
            args: { production_plan: pp },
            callback: (r) => {
                if (!r.message || !r.message.stages) { this.show_list(); return; }
                this._render_order(r.message);
            }
        });
    }

    _render_order(order) {
        const stages_html = order.stages.map(s => this._tpl_stage(s, order)).join("");
        const se_html = this._tpl_stock_entries(order.stock_entries || []);

        this.$main.html(`
            <div class="dc-header">
                <button class="btn btn-xs btn-default dc-btn-back">← Back</button>
                <span class="dc-title">${order.article_name || order.design_no}</span>
                <span class="dc-order-so">${order.sales_order || ""}</span>
                <button class="btn btn-xs btn-default dc-btn-refresh">↻</button>
            </div>
            <div class="dc-body">
                <div class="dc-stages">${stages_html}</div>
                ${se_html}
            </div>
        `);

        this.$main.find(".dc-btn-back").on("click", () => this.show_list());
        this.$main.find(".dc-btn-refresh").on("click", () => this._load_order(order.production_plan));
        this._bind_order_actions(order);
        this._load_all_jc_sections(order);
    }

    _tpl_stage(stage, order) {
        const icon = stage.wo_status === "Completed" ? "✅"
                   : stage.wo_docstatus === 1 ? "⏳" : "○";
        const locked = stage.is_locked;
        const done = stage.wo_status === "Completed";

        let actions = "";
        if (stage.can_start) {
            actions += `<button class="btn btn-sm btn-primary dc-act dc-start"
                data-wo="${stage.wo_name}" data-pp="${order.production_plan}">
                ▶ Start ${stage.stage_name}</button>`;
        }
        if (stage.can_transfer) {
            actions += `<button class="btn btn-sm btn-default dc-act dc-transfer"
                data-wo="${stage.wo_name}">Transfer Materials</button>`;
        }
        if (stage.can_finish) {
            actions += `<button class="btn btn-sm btn-success dc-act dc-finish"
                data-wo="${stage.wo_name}">Complete & Finish</button>`;
        }
        if (stage.can_create_qi) {
            actions += `<button class="btn btn-sm btn-warning dc-act dc-qi"
                data-wo="${stage.wo_name}" data-stage="${stage.stage_name}">
                Inspect ${stage.stage_name}</button>`;
        }
        if (stage.qi_exists && stage.qi_name) {
            actions += `<a href="/app/quality-inspection/${stage.qi_name}"
                class="btn btn-xs btn-default">QI ✅</a>`;
        }

        const assign_html = (stage.wo_docstatus === 1 && !done)
            ? `<div class="dc-jc-section" data-wo="${stage.wo_name}"></div>` : "";

        return `
        <div class="dc-stage ${locked ? "dc-locked" : ""} ${done ? "dc-done" : ""}">
            <div class="dc-stage-head">
                <span class="dc-stage-icon">${icon}</span>
                <span class="dc-stage-name">${stage.stage_name}</span>
                <span class="dc-stage-item">${stage.output_item}</span>
                ${locked ? '<span class="dc-badge-locked">Locked</span>' : ""}
            </div>
            ${actions ? `<div class="dc-actions">${actions}</div>` : ""}
            ${assign_html}
        </div>`;
    }

    _tpl_stock_entries(ses) {
        if (!ses.length) return "";
        const rows = ses.map(se => `
            <div class="dc-se-row ${se.needs_action ? "dc-se-alert" : ""}">
                <span class="dc-se-label">${se.label}</span>
                <span class="dc-se-date">${se.date}</span>
                <span class="dc-se-status">${se.status}</span>
                ${se.needs_action
                    ? `<button class="btn btn-xs btn-warning dc-submit-se" data-se="${se.name}">
                        Review & Submit</button>`
                    : `<a href="/app/stock-entry/${se.name}" class="btn btn-xs btn-default">View</a>`}
            </div>`).join("");
        return `<div class="dc-se-box"><div class="dc-se-title">Stock Entries</div>${rows}</div>`;
    }

    _bind_order_actions(order) {
        const pp = order.production_plan;

        this.$main.find(".dc-start").on("click", (e) => {
            const wo = $(e.target).data("wo");
            frappe.confirm(__("Start this stage? Work Order will be submitted automatically."), () => {
                frappe.call({
                    method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.start_stage",
                    args: { production_plan: pp, work_order: wo },
                    freeze: true, freeze_message: __("Starting stage..."),
                    callback: () => this._load_order(pp)
                });
            });
        });

        this.$main.find(".dc-transfer").on("click", (e) => {
            const wo = $(e.target).data("wo");
            frappe.confirm(__("Auto-create and submit Material Transfer?"), () => {
                frappe.call({
                    method: "desar_manufacturing.api.manufacturing.create_transfer_se",
                    args: { work_order: wo },
                    freeze: true, freeze_message: __("Creating Transfer Entry..."),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __("Transfer submitted ✓"), indicator: "green" });
                            this._load_order(pp);
                        }
                    }
                });
            });
        });

        this.$main.find(".dc-finish").on("click", (e) => {
            const wo = $(e.target).data("wo");
            frappe.confirm(__("Finish Work Order and create Manufacture Entry?"), () => {
                frappe.call({
                    method: "desar_manufacturing.api.manufacturing.finish_work_order",
                    args: { work_order: wo },
                    freeze: true, freeze_message: __("Finishing Work Order..."),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __("Stage complete ✓"), indicator: "green" });
                            this._load_order(pp);
                        }
                    }
                });
            });
        });

        this.$main.find(".dc-qi").on("click", (e) => {
            const wo = $(e.target).data("wo");
            const stage = $(e.target).data("stage");
            frappe.call({
                method: "desar_manufacturing.api.manufacturing.create_quality_inspection_dynamic",
                args: { work_order: wo, stage_name: stage },
                freeze: true, freeze_message: __("Creating Inspection..."),
                callback: (r) => {
                    if (r.message) frappe.set_route("Form", "Quality Inspection", r.message);
                }
            });
        });

        this.$main.find(".dc-submit-se").on("click", (e) => {
            frappe.set_route("Form", "Stock Entry", $(e.target).data("se"));
        });
    }

    _load_all_jc_sections(order) {
        this.$main.find(".dc-jc-section").each((i, el) => {
            const wo = $(el).data("wo");
            frappe.call({
                method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_stage_job_cards",
                args: { work_order: wo },
                callback: (r) => {
                    const jcs = r.message || [];
                    if (!jcs.length) { $(el).html(""); return; }
                    const html = jcs.map(jc => {
                        const icon = jc.status === "Completed" ? "✅" : "⏳";
                        const assignee = jc.custom_assigned_to
                            ? `<span class="dc-assignee">${jc.custom_assigned_to}</span>` : "";
                        return `<span class="dc-jc-pill">
                            ${icon} <a href="/app/job-card/${jc.name}">${jc.operation || jc.name}</a>
                            ${assignee}</span>`;
                    }).join("");
                    $(el).html(`<div class="dc-jc-pills">${html}</div>`);
                }
            });
        });
    }

    // ══ OPERATOR: My Jobs ══════════════════════════════════════════════════

    _show_operator_view() {
        this.$main.html(`
            <div class="dc-header">
                <span class="dc-title">My Jobs</span>
                <button class="btn btn-xs btn-default dc-btn-refresh">↻</button>
            </div>
            <div class="dc-body"><div class="dc-loading">Loading your jobs...</div></div>
        `);
        this.$main.find(".dc-btn-refresh").on("click", () => this._load_operator_jobs());
        this._load_operator_jobs();
        this._timer = setInterval(() => this._load_operator_jobs(), 15000);
    }

    _load_operator_jobs() {
        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_my_job_cards",
            callback: (r) => {
                const $b = this.$main.find(".dc-body");
                const jobs = r.message || [];
                if (!jobs.length) {
                    $b.html(`
                        <div class="dc-empty-operator">
                            <div class="dc-empty-icon">✅</div>
                            <div class="dc-empty-text">No jobs assigned to you today</div>
                        </div>`);
                    return;
                }
                $b.html(jobs.map(j => this._tpl_operator_job(j)).join(""));
                this._bind_operator_actions();
            }
        });
    }

    _tpl_operator_job(job) {
        const is_started = job.status === "Work In Progress";
        const is_done = job.status === "Completed";

        let btn = "";
        if (!is_done && !is_started) {
            btn = `<button class="btn dc-op-btn dc-op-start" data-jc="${job.name}">
                ▶ Start</button>`;
        } else if (is_started) {
            btn = `<button class="btn dc-op-btn dc-op-complete" data-jc="${job.name}" data-stage="${job.stage_name || job.operation || ""}">
                ✅ Complete</button>`;
        } else {
            btn = `<span class="dc-op-done">Done ✅</span>`;
        }

        // After JC done — show Transfer and Finish if needed
        let extra = "";
        if (is_done && job.can_transfer) {
            extra += `<button class="btn dc-op-btn-sm dc-transfer" data-wo="${job.work_order}">
                Transfer Materials</button>`;
        }
        if (is_done && job.can_finish) {
            extra += `<button class="btn dc-op-btn-sm dc-op-finish" data-wo="${job.work_order}">
                Complete Work Order</button>`;
        }

        return `
        <div class="dc-op-card ${is_done ? "dc-op-done-card" : ""}">
            <div class="dc-op-stage">${job.stage_name || job.operation}</div>
            <div class="dc-op-order">${job.article_name || ""} · ${job.production_item || ""}</div>
            <div class="dc-op-workstation">${job.workstation || ""}</div>
            <div class="dc-op-actions">
                ${btn}
                ${extra}
            </div>
        </div>`;
    }

    _bind_operator_actions() {
        // Start JC
        this.$main.find(".dc-op-start").on("click", (e) => {
            const jc = $(e.target).data("jc");
            frappe.call({
                method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.start_job_card",
                args: { job_card: jc },
                freeze: true, freeze_message: __("Starting..."),
                callback: () => {
                    frappe.show_alert({ message: __("Started ✓"), indicator: "green" });
                    this._load_operator_jobs();
                }
            });
        });

        // Complete JC — asks for optional scrap qty (and, Warping only,
        // actual yarn used) at the same moment the operator marks the job
        // done, rather than a separate document/step later.
        this.$main.find(".dc-op-complete").on("click", (e) => {
            const jc = $(e.target).data("jc");
            const stage = ($(e.target).data("stage") || "").toLowerCase();
            const is_warping = stage.includes("warp");

            const fields = [
                { fieldname: "scrap_qty", fieldtype: "Float", label: __("Scrap Qty (leave blank if none)") },
            ];
            if (is_warping) {
                fields.push({
                    fieldname: "actual_yarn_kg", fieldtype: "Float",
                    label: __("Actual Yarn Used, Kg (leave blank if it matched the recipe)"),
                });
            }

            const d = new frappe.ui.Dialog({
                title: __("Complete Job"),
                fields,
                primary_action_label: __("Complete"),
                primary_action: (values) => {
                    d.hide();
                    frappe.call({
                        method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.complete_job_card",
                        args: {
                            job_card: jc,
                            scrap_qty: values.scrap_qty,
                            actual_yarn_kg: values.actual_yarn_kg,
                        },
                        freeze: true, freeze_message: __("Completing..."),
                        callback: () => {
                            frappe.show_alert({ message: __("Job complete ✓"), indicator: "green" });
                            this._load_operator_jobs();
                        }
                    });
                },
            });
            d.show();
        });

        // Transfer + Finish (reuse existing)
        this.$main.find(".dc-transfer").on("click", (e) => {
            const wo = $(e.target).data("wo");
            frappe.confirm(__("Auto-create Material Transfer?"), () => {
                frappe.call({
                    method: "desar_manufacturing.api.manufacturing.create_transfer_se",
                    args: { work_order: wo },
                    freeze: true, freeze_message: __("Transferring..."),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __("Transfer done ✓"), indicator: "green" });
                            this._load_operator_jobs();
                        }
                    }
                });
            });
        });

        this.$main.find(".dc-op-finish").on("click", (e) => {
            const wo = $(e.target).data("wo");
            frappe.confirm(__("Finish Work Order?"), () => {
                frappe.call({
                    method: "desar_manufacturing.api.manufacturing.finish_work_order",
                    args: { work_order: wo },
                    freeze: true, freeze_message: __("Finishing..."),
                    callback: (r) => {
                        if (r.message) {
                            frappe.show_alert({ message: __("Work Order complete ✓"), indicator: "green" });
                            this._load_operator_jobs();
                        }
                    }
                });
            });
        });
    }

    // ══ QC INSPECTOR: Pending Inspections ═════════════════════════════════

    _show_qc_view() {
        this.$main.html(`
            <div class="dc-header">
                <span class="dc-title">Pending Inspections</span>
                <button class="btn btn-xs btn-default dc-btn-refresh">↻</button>
            </div>
            <div class="dc-body"><div class="dc-loading">Loading...</div></div>
        `);
        this.$main.find(".dc-btn-refresh").on("click", () => this._load_qc_jobs());
        this._load_qc_jobs();
        this._timer = setInterval(() => this._load_qc_jobs(), 15000);
    }

    _load_qc_jobs() {
        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_pending_inspections",
            callback: (r) => {
                const $b = this.$main.find(".dc-body");
                const items = r.message || [];
                if (!items.length) {
                    $b.html(`<div class="dc-empty-operator">
                        <div class="dc-empty-icon">✅</div>
                        <div class="dc-empty-text">No pending inspections</div>
                    </div>`);
                    return;
                }
                $b.html(items.map(i => `
                    <div class="dc-qc-card">
                        <div class="dc-op-stage">${i.stage_name}</div>
                        <div class="dc-op-order">${i.article_name || ""} · ${i.output_item}</div>
                        <div class="dc-op-workstation">Batch: ${i.batch_no || "—"}</div>
                        <div class="dc-op-actions">
                            <button class="btn dc-op-btn dc-qi"
                                data-wo="${i.work_order}" data-stage="${i.stage_name}">
                                Create Inspection</button>
                        </div>
                    </div>`).join(""));
                this.$main.find(".dc-qi").on("click", (e) => {
                    const wo = $(e.target).data("wo");
                    const stage = $(e.target).data("stage");
                    frappe.call({
                        method: "desar_manufacturing.api.manufacturing.create_quality_inspection_dynamic",
                        args: { work_order: wo, stage_name: stage },
                        freeze: true, freeze_message: __("Creating Inspection..."),
                        callback: (r) => {
                            if (r.message) frappe.set_route("Form", "Quality Inspection", r.message);
                        }
                    });
                });
            }
        });
    }

    // ══ STORE MANAGER: Pending Repack SEs ════════════════════════════════

    _show_store_view() {
        this.$main.html(`
            <div class="dc-header">
                <span class="dc-title">Pending Actions</span>
                <button class="btn btn-xs btn-default dc-btn-refresh">↻</button>
            </div>
            <div class="dc-body"><div class="dc-loading">Loading...</div></div>
        `);
        this.$main.find(".dc-btn-refresh").on("click", () => this._load_store_jobs());
        this._load_store_jobs();
        this._timer = setInterval(() => this._load_store_jobs(), 30000);
    }

    _load_store_jobs() {
        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_controller.desar_production_controller.get_pending_repack",
            callback: (r) => {
                const $b = this.$main.find(".dc-body");
                const items = r.message || [];
                if (!items.length) {
                    $b.html(`<div class="dc-empty-operator">
                        <div class="dc-empty-icon">✅</div>
                        <div class="dc-empty-text">No pending actions</div>
                    </div>`);
                    return;
                }
                $b.html(items.map(i => `
                    <div class="dc-store-card">
                        <div class="dc-store-badge">⚠️ Repack Pending</div>
                        <div class="dc-op-stage">${i.name}</div>
                        <div class="dc-op-order">${i.date}</div>
                        <div class="dc-store-grades">
                            <span class="dc-grade-a">Grade A: ${i.grade_a}</span>
                            <span class="dc-grade-b">Grade B: ${i.grade_b}</span>
                            <span class="dc-grade-c">Scrap: ${i.grade_c}</span>
                        </div>
                        <div class="dc-op-actions">
                            <button class="btn dc-op-btn dc-store-submit"
                                data-se="${i.name}">Review & Submit</button>
                        </div>
                    </div>`).join(""));
                this.$main.find(".dc-store-submit").on("click", (e) => {
                    frappe.set_route("Form", "Stock Entry", $(e.target).data("se"));
                });
            }
        });
    }
}
