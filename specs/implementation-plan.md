# DESAR Piece-Based Manufacturing: Implementation Plan

Status: DRAFT for review. Builds on `specs/audit-and-target-design.md` (audit, decisions). Site: `tzamun` (ERPNext 15.121.5). No code written yet.

## 1. Agreed rules

- One Work Order and one BOM per final product (Shemagh design + size). One Sales Order gives many Work Orders. DESAR Production Order stays as a read-only summary over them.
- Beam, split beam, grey roll, finished roll are records, never Items, never BOM rows, never stock.
- BOM holds all raw materials as per-piece quantities, each tagged to the operation that uses it (BOM Item `operation`): warp yarn to Warping, weft and flower yarn to Weaving, chemicals to Chemical Finishing, box, label, sticker to Boxing. Work Order qty is in pieces. A 100-piece order needs 100 boxes and no roll item.
- Exactly 2 Stock Entries per Work Order: Material Transfer for Manufacture at the start, Manufacture at the end.
- Operations are Job Cards: Warping, Beam Split, Weaving, Chemical Finishing, packing sub-steps (classification, cutting, piece finishing, steaming, ironing, stamping, boxing). Inspections are `Roll Inspection` documents, not Job Cards.
- Grades A, B, C. A and B valued, C zero value in the scrap warehouse. Process loss posts nothing.
- Individual worker logins. A worker sees only assigned work. English and Arabic.
- Old flow on `tzamun` finishes untouched. New flow is switched per Design Master.

## 2. Data model

### Design Master (existing, trimmed)
Add: `process_version` (Legacy / Piece based), `roll_length_m`, `picks_per_cm`, `routing`. Keep: warp recipe, weft recipe, pieces per roll, box/label/sticker items. Piece-based masters use no Stage Configuration and no `bom_level_*`.

### New doctypes
| Doctype | Key fields |
|---------|-----------|
| Production Beam (tree) | beam_id, work_order, parent_production_beam, is_group, length_m, workstation, planned_rolls, planned_pieces, yarn_batch, status |
| Roll Inspection (submittable) | roll_ticket, work_order, stage (Gray / Finishing / Final), opening grades table, movements table (from, to, qty, reason), process loss table (qty, reason), closing grades table, count_difference |
| Grade Movement Reason, Process Loss Reason | simple masters, seeded |

### Existing doctypes evolved
- Roll Ticket: add production_beam, work_order, current_operation, meters, assumed pieces, final A/B/C, process loss total. Batch link no longer required.
- Job Card custom field `custom_production_beam`. `custom_assigned_to` already exists.
- Work Order: keep `custom_design_master`, add `custom_process_version`.

### Roles
`DESAR Factory Worker` (tablet, assigned work only), `DESAR Supervisor` (assign, approve, close), technical roles use standard ERPNext roles.

## 3. Behaviour

### Planning to start (Desk, technical user)
Production Plan makes one Work Order per design+size (standard, buffer % field kept). Work Order submit, then "Create Beams" button: beam length, loom, planned rolls per beam. "Issue Materials" button creates and submits the one Material Transfer for Manufacture.

### Weaving and finishing
Job Card per beam per operation (standard "make job card" split by beam). Beam screen creates Roll Tickets (Roll ID, QR). Roll keeps one ID to the end.

### Inspections
Same controller for all three stages (`RollInspection`):
- Gray: worker enters assumed A/B/C.
- Finishing: opening fetched from Gray closing; worker adds movement rows (any to any, reason required) and process loss; closing computed.
- Final: opening fetched from Finishing closing; worker adds movements, then enters real counted A/B/C; difference becomes process loss (fewer) or count gain (more), each with reason.
- Rules: movement cannot exceed source grade's opening count; submitted inspection is read-only; cancel only if no later inspection exists.
- On submit: update the roll's totals, and counters on the beam and Work Order incrementally.

### Closing
Supervisor "Close Order": checks all rolls have a submitted Final inspection, then builds the Manufacture Stock Entry. A to the Shemagh A item, B to the B item, C to the scrap warehouse as scrap item. Cost split between A and B by a weight (D4, B weight to be confirmed); C zero. Fallback if v15.121 rejects multiple output rows: Manufacture for A plus one Repack for B and C.

### Materials per operation
All materials are issued once at the start (one Material Transfer, the first of the 2 Stock Entries). The operation tag on each BOM row does not create stock movements. It drives: (1) the materials list shown on that operation's Job Card and tablet screen, (2) actual consumption entered on that Job Card (Phase 3), summed into the end Manufacture Stock Entry, (3) the stage cost report.

### Stage cost report
Job Card cost per operation, plus materials tagged to that operation in the BOM (warp yarn to Warping, weft yarn to Weaving, chemicals to Chemical Finishing, box/label/sticker to Boxing).

## 4. Interfaces

- `api/shop_floor.py` (role-gated, thin): `my_tasks`, `start_job`, `complete_job`, `create_rolls`, `get_inspection`, `save_inspection`, `submit_inspection`. Logic stays in services.
- Assignment reuses standard Frappe assignment (ToDo) on Job Card and on Roll Inspection tasks. `permission_query_conditions` limits a worker to own assigned documents.
- Tablet app in `frontend/` (Vue 3, frappe-ui, espresso): Tasks, Beam, Roll, Inspect screens. Large touch targets, steppers, plain wording, 10-minute undo. Translations en and ar, RTL layout.
- Print formats: Work Order (warp repeat, beam table), Loom Ticket, Roll Ticket with QR.

## 5. Code layout

Files 100 to 300 lines, functions about 10 lines, no abbreviations (CLAUDE.md).

```
doctype/production_beam/        production_beam.py (class), .json, .js
doctype/roll_inspection/        roll_inspection.py (class RollInspection)
services/closing_service.py     Manufacture Stock Entry build
services/inspection_service.py  opening fetch, movement math
services/beam_service.py        create beams and rolls
api/shop_floor.py
frontend/src/...                pages, components, locales/{en,ar}.json
```

Before implementation I will read the `frappe-app-dev` and `frappe-ui` skill files in `.agents/skills/` (CLAUDE.md requires it; they are not registered as invocable skills here).

## 6. Phases (tracer bullet)

Each phase ships its tests and updates `PROGRESS.md`.

| Phase | Slice | Acceptance |
|-------|-------|------------|
| 0 | Confirm D4 weight and first product (Design 563 size 60). Backup `tzamun`. Check `bench --site tzamun run-tests` works. Create masters for the test product | Backup taken, tests runnable |
| 1 tracer | Routing + per-piece BOM for the test product. 1 Work Order of 100 pieces, 1 beam, 2 rolls. Gray, Finishing, Final inspections (Desk forms). Issue Materials and Close Order | 100 pieces need 100 boxes, 0 roll items. 2 Stock Entries only. A/B/C posted correctly. Test: grade movements and difference |
| 2 | Multiple beams and looms, Job Cards per beam, packing sub-step Job Cards, print formats | Paper work order and loom ticket reproduced |
| 3 | Stage cost report, A/B valuation, B sales item and price, chemical actual consumption | Cost report equals manual calculation |
| 4 | Tablet app, assignment, permissions, Arabic | Worker completes a roll on a tablet, sees only assigned tasks |
| 5 | Reports (yield, grade movement, loss by reason, WIP by operation), Production Order summary rewired to new records | Numbers match Phase 1 data |
| 6 | Load test on a copy of `tzamun`: 50 beams, 1000 rolls; time limits per screen and per submit. Fix indexes and queries | Documented timings within limit |
| 7 | Retire old code paths once no legacy order is open: stage configuration, roll chain, split WO cloning, rounding hooks, `temp_script.py`. Playwright e2e and CI. One guide replaces `flow.md` and `complete_flow.md` | Suite green, no dead code |

## 7. Risks and checks

- Job Card quantity unit: define in pieces from the Design Master conversion. Check in Phase 1.
- Multiple output rows in one Manufacture Stock Entry on 15.121.5. Check in Phase 1, fallback above.
- ERPNext Job Card rules on sequence and quantity when splitting by beam. Check in Phase 2.
- Two flows coexisting: guard every hook and endpoint by `process_version` so legacy orders are untouched. Test both.
- Production data on `tzamun`: backup before every phase that touches schema; patches reversible.
- If the ST team already agreed the staged design with the client, this is a larger change than they expect.

## 8. Open items

- D4: B valuation weight relative to A.
- First test product: Design 563 size 60 (assumed).
