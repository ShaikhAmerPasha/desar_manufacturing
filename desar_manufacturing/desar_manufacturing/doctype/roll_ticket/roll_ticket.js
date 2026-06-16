// Roll Ticket client script
frappe.ui.form.on("Roll Ticket", {
    refresh(frm) {
        // Delay render to ensure DOM is ready
        setTimeout(() => _desar_render_grade_adjustment(frm), 500);
    },
    stage_grades_add(frm) {
        setTimeout(() => _desar_render_grade_adjustment(frm), 300);
    },
    stage_grades_remove(frm) {
        setTimeout(() => _desar_render_grade_adjustment(frm), 300);
    }
});

/**
 * Grade Adjustment Summary — Option A
 * Compares Finishing vs Final (Packing) grades.
 * Shows upgrades (+) and downgrades (-) per grade.
 * Pure client-side computation from stage_grades child table.
 */
function _desar_render_grade_adjustment(frm) {
    const grades = frm.doc.stage_grades || [];
    if (!grades.length) return;

    // Get unique grade codes
    const grade_codes = [...new Set(grades.map(r => r.grade_code))].sort();

    // Get unique stage names
    const stage_names = [...new Set(grades.map(r => r.stage_name))];

    // Find Finishing and Packing stages
    const finishing_stage = stage_names.find(s =>
        s.toLowerCase().includes('finish')
    );
    const packing_stage = stage_names.find(s =>
        s.toLowerCase().includes('pack') || s.toLowerCase().includes('final')
    );

    if (!finishing_stage || !packing_stage) return;

    // Build grade maps
    const finishing = {};
    const packing = {};
    grades.forEach(r => {
        if (r.stage_name === finishing_stage) finishing[r.grade_code] = r.qty;
        if (r.stage_name === packing_stage)   packing[r.grade_code]   = r.qty;
    });

    // Build HTML table
    let rows = '';
    let has_changes = false;

    grade_codes.forEach(code => {
        const fin_qty  = finishing[code] || 0;
        const pack_qty = packing[code]   || 0;
        const diff     = pack_qty - fin_qty;

        let diff_html = `<span style="color:gray">0</span>`;
        if (diff > 0) {
            diff_html = `<span style="color:green;font-weight:bold">+${diff} ↑</span>`;
            has_changes = true;
        } else if (diff < 0) {
            diff_html = `<span style="color:red;font-weight:bold">${diff} ↓</span>`;
            has_changes = true;
        }

        rows += `
        <tr>
            <td style="padding:6px 12px;font-weight:bold">Grade ${code}</td>
            <td style="padding:6px 12px;text-align:center">${fin_qty}</td>
            <td style="padding:6px 12px;text-align:center">${pack_qty}</td>
            <td style="padding:6px 12px;text-align:center">${diff_html}</td>
        </tr>`;
    });

    const status_msg = has_changes
        ? `<span style="color:orange">⚠ Grade adjustments occurred during Packing</span>`
        : `<span style="color:green">✓ No grade changes during Packing</span>`;

    const html = `
    <div style="margin:10px 0">
        <p style="margin-bottom:8px">${status_msg}</p>
        <table style="border-collapse:collapse;width:100%;max-width:500px">
            <thead>
                <tr style="background:#f5f5f5">
                    <th style="padding:6px 12px;text-align:left">Grade</th>
                    <th style="padding:6px 12px;text-align:center">${finishing_stage}</th>
                    <th style="padding:6px 12px;text-align:center">${packing_stage}</th>
                    <th style="padding:6px 12px;text-align:center">Change</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;

    const field = frm.get_field('grade_adjustment_html');
    if (!field || !field.$wrapper) {
        // Section may be collapsed — try again after expanding
        frm.expand_all_sections && frm.expand_all_sections();
        setTimeout(() => {
            const f2 = frm.get_field('grade_adjustment_html');
            if (f2 && f2.$wrapper) f2.$wrapper.html(html);
        }, 300);
        return;
    }
    field.$wrapper.html(html);
}