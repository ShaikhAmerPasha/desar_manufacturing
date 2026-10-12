// Display-only mirror of desar_manufacturing/utils/grade_movement.py. The server is authoritative.
export function applyMovements(opening, movements) {
	const counts = { ...opening }
	for (const move of movements) {
		if (!move.from_grade || !move.to_grade || !move.qty) continue
		counts[move.from_grade] = (counts[move.from_grade] || 0) - move.qty
		counts[move.to_grade] = (counts[move.to_grade] || 0) + move.qty
	}
	return counts
}

export function applyAdjustments(counts, adjustments) {
	const result = { ...counts }
	for (const row of adjustments) {
		if (row.grade_code) result[row.grade_code] = (result[row.grade_code] || 0) + (row.qty || 0)
	}
	return result
}

export function countsOf(rows) {
	return Object.fromEntries(rows.map((row) => [row.grade_code, row.qty || 0]))
}

export function totalOf(counts) {
	return Object.values(counts).reduce((sum, qty) => sum + qty, 0)
}
