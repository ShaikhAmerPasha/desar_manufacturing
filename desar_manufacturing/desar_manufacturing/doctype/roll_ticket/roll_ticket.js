// Roll Ticket client script
frappe.ui.form.on("Roll Ticket", {
    refresh(frm) {
        setTimeout(() => _desar_render_grade_adjustment(frm), 800);
    },
    stage_grades_add(frm) { _desar_render_grade_adjustment(frm); },
    stage_grades_remove(frm) { _desar_render_grade_adjustment(frm); },
});

function _desar_render_grade_adjustment(frm) {
    const grades = frm.doc.stage_grades || [];
    if (!grades.length) return;

    const stage_names = [...new Set(grades.map(r => r.stage_name))];
    const finishing_stage = stage_names.find(s => s.toLowerCase().includes('finish'));
    const packing_stage = stage_names.find(s =>
        s.toLowerCase().includes('pack') || s.toLowerCase().includes('final')
    );

    if (!finishing_stage || !packing_stage) return;

    const finishing = {}, packing = {};
    grades.forEach(r => {
        if (r.stage_name === finishing_stage) finishing[r.grade_code] = r.qty;
        if (r.stage_name === packing_stage)   packing[r.grade_code]   = r.qty;
    });

    const grade_codes = [...new Set(grades.map(r => r.grade_code))].sort();
    let has_changes = false;
    let rows = '';

    grade_codes.forEach(code => {
        const fin  = finishing[code] || 0;
        const pack = packing[code]   || 0;
        const diff = pack - fin;
        let diff_html = `<span style="color:gray">—</span>`;
        if (diff > 0)      { diff_html = `<span style="color:green;font-weight:bold">+${diff} ↑</span>`; has_changes = true; }
        else if (diff < 0) { diff_html = `<span style="color:red;font-weight:bold">${diff} ↓</span>`;   has_changes = true; }
        rows += `<tr>
            <td style="padding:6px 12px;font-weight:bold">Grade ${code}</td>
            <td style="padding:6px 12px;text-align:center">${fin}</td>
            <td style="padding:6px 12px;text-align:center">${pack}</td>
            <td style="padding:6px 12px;text-align:center">${diff_html}</td>
        </tr>`;
    });

    const status = has_changes
        ? `<span style="color:orange">⚠ Grade adjustments occurred during Packing</span>`
        : `<span style="color:green">✓ No grade changes during Packing</span>`;

    const html = `
    <div style="margin:10px 0">
        <p>${status}</p>
        <table style="border-collapse:collapse;width:100%;max-width:500px;border:1px solid #ddd">
            <thead><tr style="background:#f5f5f5">
                <th style="padding:6px 12px;text-align:left;border:1px solid #ddd">Grade</th>
                <th style="padding:6px 12px;text-align:center;border:1px solid #ddd">${finishing_stage}</th>
                <th style="padding:6px 12px;text-align:center;border:1px solid #ddd">${packing_stage}</th>
                <th style="padding:6px 12px;text-align:center;border:1px solid #ddd">Change</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;

    // Try multiple render methods
    // Method 1: via frm field wrapper
    const field = frm.get_field('grade_adjustment_html');
    if (field && field.$wrapper && field.$wrapper.length) {
        field.$wrapper.html(html);
        return;
    }
    // Method 2: direct DOM injection
    const div = document.getElementById('desar-grade-adj');
    if (div) { div.innerHTML = html; return; }
    // Method 3: find by fieldname attribute
    const el = frm.fields_dict['grade_adjustment_html'];
    if (el && el.disp_area) { $(el.disp_area).html(html); }
}
