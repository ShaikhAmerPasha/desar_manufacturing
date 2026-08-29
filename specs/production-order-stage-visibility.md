# Production Order list — real stage visibility

## Problem

User report: on the DESAR Production Order list view, every order's Status
column shows "Submitted" regardless of real progress. Expectation: if roll 1
is at Warping and roll 2 is at Packing, the list should say so per order.

## Root cause

1. `warping_service.py` (Stage 1 Warping, Stage 2 Beam Split) sets
   `warping_status`/`beam_split_status` via `db_set` but never called the
   status-refresh helper that `roll_service.py` calls at all 13 of its
   stage-transition points. Warping + Beam Split is usually the longest
   wall-clock stretch before any roll-level action fires, so `status` stayed
   on `"Submitted"` the whole time.
2. Even once refreshed, `status` only has 3 usable buckets (Submitted/In
   Progress/Completed) — it can never say *which* stage a roll is at. That
   granular data (`warping_status`, `beam_split_status`, and per-roll
   `grey_roll_status`/`finished_roll_status`/`packing_status` on `DESAR Roll
   Chain`) already existed and was already rendered correctly on the form
   dashboard (`desar_production_order.js`), just never surfaced to the list.

## Fix

- New field `current_stage` (Data, `in_list_view: 1`) on `DESAR Production
  Order`, additive — `status`'s existing options/semantics are untouched, so
  nothing that reads `status` by value is affected.
- New `services/stage_status_service.py::refresh_stage_status(po)` — single
  source of truth for both fields, called from every stage-transition point
  in `warping_service.py` and `roll_service.py`.
- Stage precedence (mirrors `_add_roll_buttons` in `desar_production_order.js`
  so form and list agree):

  | Condition | `current_stage` |
  |---|---|
  | `warping_status != "Completed"` | `Warping` |
  | `beam_split_status != "Completed"` | `Beam Split` |
  | roll's `packing_status == "In Progress"`, or `finished_roll_status == "Completed"` and `packing_status == "Not Started"` | `Packing` |
  | roll's `finished_roll_status == "In Progress"`, or `grey_roll_status == "Completed"` and `finished_roll_status == "Not Started"` | `Finished Roll` |
  | roll's `roll_status == "Completed"` | `Completed` |
  | otherwise | `Grey Roll` |

- Multi-roll orders: if every roll resolves to the same label, show it
  plainly (`"Grey Roll"`). If rolls differ, group + count instead of listing
  every roll (`"Grey Roll: 2, Packing: 1"`) so the column stays readable
  regardless of roll count.
- One-off patch (`patches/v3_2_backfill_current_stage.py`) backfills
  `current_stage` on already-submitted orders on next `bench migrate`.

## Verified

- `bench --site excel run-tests --app desar_manufacturing`: 292/292 passing.
- Real data on `excel` post-migrate: `DESAR-PO-2026-00017` (mid-cycle, grey
  roll in progress) → `current_stage: "Grey Roll"`; `DESAR-PO-2026-00025`
  (done) → `"Completed"`; pre-warping orders → `"Warping"` (previously all
  showed generic `"Submitted"`).
- Not done: live browser click-through of the list view (no browser tool
  available this session) — see `PROGRESS.md` for the specific manual check
  still needed.
