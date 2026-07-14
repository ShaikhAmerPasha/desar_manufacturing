# Spec: grade tracking fix, scrap disposal fix, production-order UX simplification

## Context

Comparing the client's real factory workflow against the app surfaced three gaps (see conversation for full detail):

1. Grade movement (Grade A → B, A → C, etc.) reporting appears missing to the client, but the capture mechanism already works — `DESAR Roll Ticket Stage Grade` child table is written on every Quality Inspection submit. The bug is downstream: `grade_yield_analysis`, `roll_life_tracker`, and `api/manufacturing.get_grade_summary` all read flat `Roll Ticket` columns (`grey_qty_a`, `cutted_qty_a`, etc.) that were deleted in the v3.0 refactor. They silently return nothing.
2. Scrap (Grade C) is booked into inventory with a valuation (5% legacy ratio, or configurable `valuation_pct`). Client disposes scrap entirely, never sells it — it shouldn't be a valued stock movement.
3. The DESAR Production Order form exposes all 4 underlying Work Orders / Stock Entries / Quality Inspections as direct navigable links and requires leaving the form to submit several of them. Client's factory workers find this harder than their own single-Work-Order habit. Decision: keep the 4-stage backend (needed for stage costing), simplify what the operator sees/does.

Full technical detail (exact files, line numbers, code paths) is in the approved plan at `/home/ameer/.claude/plans/polymorphic-popping-diffie.md` — this spec restates it as tracer-bullet phases per project convention (`specs/` + `PROGRESS.md`, build the minimum working slice first, verify, then iterate).

Skills loaded per CLAUDE.md: `frappe-app-dev` (backend/doctype conventions — used throughout). `frappe-ui` is a Vue 3 component library for standalone frontend apps; this app has no Vue frontend (Desk forms + plain client-script JS only), so it doesn't apply to Phase 3's UI work — noted here rather than silently skipped.

## Tracer-bullet phases

Each phase is a complete, independently-verifiable slice — don't start the next until the current one is confirmed working.

### Phase 1a — Tracer bullet: one report, end to end
Smallest possible slice that proves the fix approach works before repeating it three more times.
- Add `desar_manufacturing/utils/grade_utils.py`: one function to resolve a roll ticket's final-stage name (via `DESAR Stage Configuration.is_final_stage=1`, reusing the logic already in `events/quality_inspection.py:_is_final_stage`), one function to fetch+pivot `DESAR Roll Ticket Stage Grade` rows into `{grade_code: qty}` for a given roll ticket + stage.
- Rewrite `grade_yield_analysis.get_data()` to use it instead of the deleted `cutted_*` columns.
- Verify: manually run the report on the dev site against at least one completed Roll Ticket with `stage_grades` rows, confirm non-empty, correct grade split.

### Phase 1b — Apply the same fix to the remaining two consumers
- `roll_life_tracker.get_data()` — same helper, three stage buckets (first stage / finishing / final).
- `api/manufacturing.get_grade_summary()` — same helper.
- Clean up `roll_ticket.json` `field_order` (drop the 15 dead entries, add the 4 missing current ones).
- Verify: same manual report run, plus `get_grade_summary` called via `bench execute` or the browser console.

### Phase 1c — Regression test
- Add `desar_manufacturing/tests/test_grade_reports.py` using `frappe.tests.IntegrationTestCase` (not plain `unittest.TestCase` — existing test files use the wrong base class, don't copy that).
- Verify: `bench --site <site> run-tests --module desar_manufacturing.tests.test_grade_reports`.

### Phase 2 — Scrap disposal (depends on Phase 1 being done, since its own verification leans on the fixed grade_yield_analysis report)
- `services/repack_service.py`: `_build_items_legacy`, `_build_items_dynamic`, `_build_items` — drop the scrap valuation/stock line; decide server-side whether the source-consumption qty excludes scrap or routes it to a zero-value disposal warehouse (see plan file for the reconciliation tradeoff).
- Update `tests/test_e2e_cycle.py`, `tests/test_dynamic_architecture.py`, `tests/test_roll_ticket_service.py` scrap-row assertions.
- Verify: updated test suite passes; manually submit one Final Packing QI with nonzero scrap on the dev site, confirm no scrap stock line, confirm scrap qty still visible via the now-fixed `grade_yield_analysis` report.

### Phase 3 — Production Order UI simplification
- `desar_manufacturing/desar_manufacturing/doctype/desar_production_order/desar_production_order.js` only — no backend changes.
- Collapse WO/SE/QI links behind a per-stage "Details" disclosure; extend the existing inline-submit pattern (already present for the packing Manufacture SE) to the Warping Transfer SE and QI submission; add a roll-level status badge.
- Verify: `agent-browser` manual click-through of one full roll cycle, confirm no forced navigation away from the form for in-role actions.

## Out of scope (flagged, not fixed here)
- `desar_manufacturing/page/desar_production_controller/` + `desar_production_workspace/` — a second, disconnected prototype UI, not wired to the live flow.
- `desar_production_order_stage` child doctype — orphaned, unreferenced by the live schema.
- `events/work_order.py`'s native ERPNext `scrap_warehouse` — different concept (BOM scrap), not touched.

See `PROGRESS.md` at the app root for live phase status.
