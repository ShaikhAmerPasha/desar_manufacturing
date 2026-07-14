# P3 — Scale/Performance

Three audit findings. Tracer bullet: measure before optimizing, fix the cheap/safe ones now.

## 1. Beam Split per-roll inserts — measured, not rewritten

Benchmarked the real `wo_split_helpers._clone_combined_wo` against a live Work Order on `excel` (rolled back after each batch, nothing persisted):

| rolls | time | queries | queries/roll |
|---|---|---|---|
| 4 | 0.11s | 144 | 36 |
| 20 | 0.84s | 720 | 36 |
| 50 | 2.12s | 1800 | 36 |
| 100 | 4.01s | 3600 | 36 |

Real production data on `excel` shows actual beam splits are 1-4 rolls (`roll_count` column on `tabDESAR Production Order`). At that scale this is sub-second and not worth touching — a bulk-insert rewrite would mean bypassing Work Order's own `validate`/BOM-explosion hooks, real risk for no current benefit. **Deferred, not rewritten.** Revisit only if real usage grows toward 30-50+ rolls per split (~1-2s) or 100+ (~4s, real timeout risk, and split_beam does this 3x for grey/finished/packing).

## 2. Missing DB indexes — done

Added `search_index: 1` to `DESAR Roll Chain.beam_roll_batch` and the `Quality Inspection.custom_desar_stage_name` custom field. Verified via `SHOW INDEX` on `excel` — both indexes exist now (`beam_roll_batch_index`, `custom_desar_stage_name_index`).

## 3. Dashboard 1000-row cap — made visible, not removed

`desar_production_order.js`'s 3 dashboard queries (Job Card/Stock Entry/Quality Inspection) were silently truncating at `limit: 1000`. Added `_warn_if_truncated()` — shows an orange alert when a query actually hits the cap, instead of just showing incomplete data with no signal. Raising the limit or adding real pagination is a bigger UI change, deferred until this cap is actually observed hitting in practice.
