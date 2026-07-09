frappe.pages["desar-production-workspace"].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Production Workspace",
        single_column: true,
    });

    $(wrapper).find(".layout-main").html(frappe.render_template("desar_production_workspace", {}));

    var ws = new DESARWorkspace(wrapper);
    ws.init();
};

class DESARWorkspace {
    constructor(wrapper) {
        this.$w = $(wrapper);
    }

    init() {
        this._set_date();
        this._bind_tabs();
        this._bind_refresh();
        this.load_production();
        this.load_inspections();
    }

    _set_date() {
        this.$w.find(".desar-ws-date").text(frappe.datetime.str_to_user(frappe.datetime.get_today()));
    }

    _bind_tabs() {
        this.$w.find(".desar-tab").on("click", (e) => {
            const tab = $(e.target).data("tab");
            this.$w.find(".desar-tab").removeClass("active");
            $(e.target).addClass("active");
            this.$w.find(".desar-tab-content").hide();
            this.$w.find(`#tab-${tab}`).show();
        });
    }

    _bind_refresh() {
        this.$w.find(".desar-refresh").on("click", () => {
            this.load_production();
            this.load_inspections();
        });
    }

    load_production() {
        const $list = this.$w.find(".desar-orders-list").html("");
        const $loading = this.$w.find(".desar-loading").show();
        const $empty = this.$w.find(".desar-empty").hide();

        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_workspace.desar_production_workspace.get_production_orders",
            callback: (r) => {
                $loading.hide();
                const orders = r.message || [];
                if (!orders.length) { $empty.show(); return; }
                orders.forEach(o => $list.append(this._render_order(o)));
                this._bind_order_actions();
            },
            error: () => $loading.text("Error loading orders. Please refresh.")
        });
    }

    load_inspections() {
        const $list = this.$w.find(".desar-qi-list").html("");
        const $loading = this.$w.find(".desar-qi-loading").show();
        const $empty = this.$w.find(".desar-qi-empty").hide();

        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_production_workspace.desar_production_workspace.get_pending_inspections",
            callback: (r) => {
                $loading.hide();
                const items = r.message || [];
                if (!items.length) { $empty.show(); return; }
                items.forEach(i => $list.append(this._render_qi_card(i)));
                this._bind_qi_actions();
            },
            error: () => $loading.text("Error loading inspections. Please refresh.")
        });
    }

    _render_order(order) {
        const status_color = {
            "Completed": "green",
            "In Process": "blue",
            "Not Started": "gray",
        }[order.overall_status] || "gray";

        const wo_rows = (order.work_orders || []).map(wo => {
            const stage_done = wo.status === "Completed";
            const stage_active = wo.status === "In Process";
            const btn = stage_done
                ? `<span class="badge badge-success">Done ✓</span>`
                : stage_active
                    ? `<button class="btn btn-xs btn-primary desar-complete-wo" data-wo="${wo.name}">Mark Complete</button>`
                    : `<span class="badge badge-default">Pending</span>`;

            const qi_btn = wo.qi_required && wo.manufacture_se && !wo.qi_exists
                ? `<button class="btn btn-xs btn-warning desar-create-qi" data-wo="${wo.name}" data-stage="${wo.stage_name}">Create ${wo.stage_name} Inspection</button>`
                : "";

            return `
            <div class="desar-wo-row ${stage_active ? 'active' : ''} ${stage_done ? 'done' : ''}">
                <div class="desar-wo-stage">${wo.stage_name || wo.production_item}</div>
                <div class="desar-wo-actions">${btn} ${qi_btn}</div>
            </div>`;
        }).join("");

        return `
        <div class="desar-order-card">
            <div class="desar-order-header">
                <div>
                    <strong>${order.article_name || order.design_no || "Unknown Design"}</strong>
                    <span class="text-muted"> · ${order.sales_order}</span>
                </div>
                <span class="indicator ${status_color}">${order.overall_status}</span>
            </div>
            <div class="desar-wo-list">${wo_rows}</div>
        </div>`;
    }

    _render_qi_card(item) {
        return `
        <div class="desar-qi-card">
            <div class="desar-qi-info">
                <strong>${item.stage_name} Inspection</strong>
                <div class="text-muted">${item.article_name || item.design_no} · ${item.production_item}</div>
            </div>
            <button class="btn btn-sm btn-warning desar-create-qi"
                data-wo="${item.work_order}"
                data-stage="${item.stage_name}">
                Create Inspection
            </button>
        </div>`;
    }

    _bind_order_actions() {
        this.$w.find(".desar-complete-wo").on("click", (e) => {
            const wo = $(e.target).data("wo");
            frappe.confirm(
                __("Complete all job cards for this stage?"),
                () => {
                    frappe.call({
                        method: "desar_manufacturing.desar_manufacturing.page.desar_production_workspace.desar_production_workspace.complete_stage",
                        args: { work_order: wo },
                        callback: () => {
                            frappe.show_alert({ message: "Stage completed", indicator: "green" });
                            this.load_production();
                        }
                    });
                }
            );
        });
    }

    _bind_qi_actions() {
        this.$w.find(".desar-create-qi").on("click", (e) => {
            const wo = $(e.target).data("wo");
            const stage = $(e.target).data("stage");
            frappe.call({
                method: "desar_manufacturing.api.manufacturing.create_quality_inspection_dynamic",
                args: { work_order: wo, stage_name: stage },
                callback: (r) => {
                    if (r.message) {
                        frappe.set_route("Form", "Quality Inspection", r.message);
                    }
                }
            });
        });
    }
}
