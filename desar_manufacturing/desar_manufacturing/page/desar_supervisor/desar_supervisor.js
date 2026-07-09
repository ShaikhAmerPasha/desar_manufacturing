frappe.pages["desar-supervisor"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "Production Status",
        single_column: true,
    });

    $(wrapper).find(".layout-main").html(frappe.render_template("desar_supervisor", {}));
    new DESARSupervisor(wrapper).init();
};

class DESARSupervisor {
    constructor(wrapper) {
        this.$w = $(wrapper);
    }

    init() {
        this.$w.find(".desar-sup-refresh").on("click", () => this.load());
        this.load();
        // Auto-refresh every 60 seconds
        this._timer = setInterval(() => this.load(), 60000);
    }

    load() {
        const $list = this.$w.find(".desar-sup-list").html("");
        const $loading = this.$w.find(".desar-sup-loading").show();
        const $empty = this.$w.find(".desar-sup-empty").hide();

        frappe.call({
            method: "desar_manufacturing.desar_manufacturing.page.desar_supervisor.desar_supervisor.get_production_status",
            callback: (r) => {
                $loading.hide();
                const orders = r.message || [];
                if (!orders.length) { $empty.show(); return; }
                orders.forEach(o => $list.append(this._render(o)));
            },
            error: () => $loading.text("Error loading. Click Refresh.")
        });
    }

    _render(order) {
        const pct = order.total ? Math.round(order.completed / order.total * 100) : 0;
        const color = pct === 100 ? "#27ae60" : pct > 0 ? "#2E86AB" : "#888";

        const stages = (order.work_orders || [])
            .sort((a, b) => (a.stage_name > b.stage_name ? 1 : -1))
            .map(wo => {
                const icon = wo.status === "Completed" ? "✅" :
                             wo.status === "In Process" ? "⏳" : "○";
                const url = `/app/work-order/${wo.name}`;
                return `<span class="desar-stage-pill ${wo.status === 'Completed' ? 'done' : wo.status === 'In Process' ? 'active' : ''}">
                    ${icon} <a href="${url}">${wo.stage_name || wo.production_item}</a>
                </span>`;
            }).join("");

        const so_link = order.sales_order
            ? `<a href="/app/sales-order/${order.sales_order}">${order.sales_order}</a>`
            : "—";

        return `
        <div class="desar-sup-card">
            <div class="desar-sup-card-header">
                <div>
                    <strong>${order.article_name || order.design_no || "Unknown"}</strong>
                    <span class="text-muted"> · ${so_link}</span>
                    <span class="text-muted"> · ${order.planned_date || ""}</span>
                </div>
                <div class="desar-progress-wrap">
                    <div class="desar-progress-bar">
                        <div class="desar-progress-fill" style="width:${pct}%;background:${color}"></div>
                    </div>
                    <span class="desar-pct" style="color:${color}">${pct}%</span>
                </div>
            </div>
            <div class="desar-stages">${stages}</div>
        </div>`;
    }
}
