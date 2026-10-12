# DESAR Manufacturing: Audit and Target Design

Status: DRAFT for review. No code changed. Date: 2026-10-11.

Sources: code base (about 21.8k lines, app v3.6.0), `DESAR Factory Manufacturing Process Review.docx`, `work order.pdf`, `Loom Ticket to Production.pdf`, the Process screenshot, and the factory flow described by the user.

Limit of this audit: the `excel` site named in PROGRESS.md does not exist in this bench (sites: st-prod, sr_const, tzamun). Findings come from reading code and docs, not from live data or a browser run.

## 0. What the factory actually does

- Sales Order (several designs, several sizes) -> Production Plan -> Work Order per final product (e.g. Shemagh-VIC-60, Shemagh-VIC-58).
- Paper Work Order: PO no., design no., size, warp recipe (yarn count, colour, ends), and a beam table (beam length 1350 / 1400 m, loom 57 / 62). Beams run on separate looms in parallel.
- Loom Ticket per machine: weft count/colour, flower yarn, number of rolls (5), roll length (300), picks/cm (planned, adjusted, counted).
- Flow: Warping (beam) -> Beam split -> Weaving on loom (grey roll) -> Gray inspection -> Chemical finishing (finished roll) -> Finishing inspection -> Packing (cut, steam, iron, stamp, box) -> final A/B/C.
- Grades A (premium), B (sellable, lower), C (scrap). A single roll holds a mix of A/B/C pieces, so grading is by piece count per roll, not one grade per roll. Grades change between stages. Packing can upgrade B to A or downgrade A to B/C. Gray and finishing grades are recorded only, not cut or moved in stock.
- Stock: raw material goes out once at the start, finished goods come in once at the end. Finished inventory exists only after Packing. The review document says no Job Cards are needed for Packing.
- The roll is the main tracking unit. The client wants Roll ID, Beam ID, Work Order, current operation, quality history, measurements and yield/scrap per Work Order and per roll.

## Part 1. How well is it implemented today

Overall verdict: good engineering, wrong shape for the factory. The code is careful (locking, cancel-safety, 225 tests, role checks), but it models the factory as a chain of stock-managed intermediate items and many Work Orders. The client review document asks ST to justify exactly this, and it is the main source of complexity.

### 1.1 What is solid (keep)

- Layering: services / repositories / events / utils. Event hooks are thin.
- Concurrency: `for_update=True` on stage transitions, savepoint on beam split, no mid-function commits.
- Cancel safety: `on_cancel` handlers for Stock Entry, QI and Work Order refuse when downstream stage has started.
- Roll Ticket with per-stage grade rows, Roll Chain, batch genealogy, `Grade Adjustment` table that forces a reconciled upgrade/downgrade log at packing (matches the client requirement).
- Reports: Grade Yield Analysis, Roll Life Tracker.
- Role-gated RPC endpoints, DESAR roles, settings doctype.
- Production Plan fixes: multi-design plans, production buffer %.
- DESAR Production Order as a single place to see everything for an order: the user wants this, keep the idea.

### 1.2 Gaps against the business (ranked)

| # | Gap | Evidence | Impact |
|---|-----|----------|--------|
| 1 | Work Order explosion. Warping WO plus a Grey, Finished and Packing WO cloned per roll. | `wo_split_helpers.split_wo_per_roll`, `warping_service._apply_fresh_split` | 5-roll order = 16 Work Orders. Client wants one per final product. Sub-assembly WOs must clear `sales_order` to avoid OverProductionError, a sign of fighting ERPNext. |
| 2 | Many Stock Entries. Per roll: Grey (2), Finished (2), Packing (transfer, manufacture, repack) = 7, plus warping 2 and beam split 1. | `roll_service.py`, `repack_service.py` | 5 rolls = 38 SEs. Factory does 2. Stock noise, slow, more failure points. |
| 3 | Intermediate items (Warping Beam, Beam Roll, Grey Roll, Finished Roll) are stock items with batches and BOMs. 1 beam = 1 grey roll = `pieces_per_roll` pieces is forced. | `bom_service.py` | Produces fractional sub-assembly qty. Fixed by rounding UP in `events/work_order.py`, `events/stock_entry.py`, `events/production_plan.py`: this silently over-consumes and over-plans. A symptom, not a fix. |
| 4 | Beam is not a real entity. No Beam ID, length, loom/machine, or beam-to-loom assignment. Beam = qty 1 batch. | `desar_roll_chain` fields, `warping_service.split_beam` | Cannot reproduce the paper work order (2 beams, 2 looms, 1350/1400 m). Parallel looms not modelled. |
| 5 | Loom Ticket missing: picks/cm, roll length, flower yarn, weft by colour, machine. Weft Recipe exists but is not linked into the flow or consumption. | `Weft Recipe`, `Roll Ticket` fields | Weft yarn is not consumed or costed from the recipe. Warp is. |
| 6 | Chemical consumption is a fixed per-roll standard from Design Master (WashAgent, FinishChem, FlowerChem hard-coded item codes). No actual consumption, no per-roll record. | `bom_service._get_chemical_items` | Client question 4 (how consumed and costed) only half answered. |
| 7 | Grade model: three Item variants per size (-A/-B/-C), grade B/C created by a manual-submit Repack SE with valuation 100/60/20 %. | `repack_service.py`, Grade Configuration | Draft Repack must be submitted by hand. 60 % and 20 % are invented numbers, not cost. C is zero-value (ok as scrap). Extra SE per roll. |
| 8 | Packing runs Job Cards with 8 operations; client doc says no Job Cards for Packing. | `roll_service._validate_job_cards`, PROGRESS.md "8 Packing sub-operations" | Contradiction to confirm with client. |
| 9 | Quality via core Quality Inspection plus custom grade readings, keyed on `custom_desar_stage_name` string matching. | `events/quality_inspection.py`, `grade_utils.py` | Piece-level counts work, but QI is built for pass/fail on an item and batch. Stage identity by name string is brittle. |
| 10 | Two parallel configuration systems: dynamic Stage Configuration and legacy `bom_level_1..4`. Bom creation is one stage per click, left in Draft, repeat. Workstation by keyword (`warp`, `weav`, `dye`, `pack`...). Nested operations table that "does NOT reliably save" (flow.md). | `bom_service.py`, `flow.md` | Fragile setup. Answers client question 10 (4 BOMs per design) badly: 4 to 5 BOMs per design-size, hand-driven. |
| 11 | State machine duplicated in DESAR Production Order and Roll Chain (status strings per stage, 18 columns per roll) instead of derived from Work Order, Job Card and inspections. | `desar_roll_chain.json`, `_refresh_po_status` | Two sources of truth; needed the whole cancel-revert layer to stay in sync. |
| 12 | Three custom Desk pages (controller 635 py + 564 js, workspace, supervisor) plus 764-line form JS. Not Frappe UI / espresso as CLAUDE.md asks. | `page/*`, `desar_production_order.js` | High UI maintenance. |

### 1.3 Code hygiene against CLAUDE.md

- File size over 300: `roll_service.py` 632, `desar_production_controller.py` 635, `desar_production_order.js` 764, `desar.js` 546, `api/manufacturing.py` 509, `bom_service.py` 503.
- `services/temp_script.py` is committed.
- Silent `except Exception: pass` in `events/stock_entry._get_roll_ticket_trigger_items`.
- Hard-coded names: "Beam Roll", "Warping Beam", chemical item codes, company suffix "-ST", `Shemagh-{ART}-{size}-A` string construction.
- Many tests mirror logic instead of calling it (noted in PROGRESS.md). `bench run-tests` was reported broken by the `hrms` app. No Playwright e2e exists (CLAUDE.md says so).
- `DESAR_MANUFACTURING_DOCUMENTATION.md`, `flow.md`, `complete_flow.md`, `MANUAL_TEST_GUIDE.md` overlap and drift; CLAUDE.md names a site that does not exist.

### 1.4 Scorecard

| Area | Score /10 | Note |
|------|-----------|------|
| Code quality, safety | 7 | Careful, tested, some size and duplication debt |
| Fit to factory process | 4 | Wrong grain: stages as Work Orders, beam not an entity |
| ERPNext standard reuse | 4 | Works around Work Order, Production Plan, Stock Entry rules |
| Traceability (roll) | 7 | Roll Ticket + batches good; beam/loom missing |
| Quality / grades | 6 | Piece counts + adjustments ok; valuation and SE flow heavy |
| Reporting | 5 | Yield and roll life exist; no cost per roll, no per-beam view |
| Maintainability | 4 | Dual modes, 4-5 BOMs per design, 3 UIs |

## Part 2. How I would build it in ERPNext

Principle: use standard ERPNext for planning, materials, operations and costing. Add custom doctypes only for what ERPNext has no concept of: Beam, Roll, piece-level grades. Do not model WIP stages as stock items.

### 2.1 Structure

```
Sales Order
  -> Production Plan (standard; no sub-assembly items)
     -> Work Order per final product (Shemagh-<ART>-<size>)   [ONE per product]
          BOM: raw materials + Routing (operations)
          Stock Entry 1: Material Transfer for Manufacture (yarn, weft, chemicals, accessories)
          Production Beam x N          (new)  Beam ID, length, loom, planned rolls
            Job Card per beam per loom operation
            Roll x M                   (new; evolves Roll Ticket)  Roll ID, beam, meters
              Roll Inspection (Gray)       A/B/C piece counts
              Roll Inspection (Finishing)  A/B/C piece counts
              Packing Entry                A/B/C final + grade movements
          Stock Entry 2: Manufacture (Shemagh A in, B/C as secondary items)
```

### 2.2 Master data

- Item: finished goods only. `Shemagh` template with Article, Size, Grade variants (already exists, keep). Yarn, chemicals, accessories as raw items. NO Beam / Grey Roll / Finished Roll items.
- BOM: ONE per design+size. Items = yarn from Warp Recipe + weft from Weft Recipe + chemicals + box/label/sticker. Operations come from one shared Routing "Shemagh Standard". BOM generated by one button on Design Master (existing idea), single click, auto-submit.
- Routing "Shemagh Standard": Weaving (loom workstation), Chemical Finishing. Gray Inspection, Finishing Inspection and Packing are roll documents, not Job Cards (matches client note). To confirm with client (decision D3).
- Workstations: each loom and the finishing machine. Hour rate gives labour/overhead cost through Job Card time logs.
- Design Master: keep, slimmed. Links Warp Recipe, Weft Recipe, pieces per roll, packing items, default roll length and picks/cm. Remove Stage Configuration and `bom_level_1..4`.
- Settings: DESAR Settings keeps warehouses and grade rules only.

### 2.3 New / changed doctypes

| Doctype | Type | Purpose |
|---------|------|---------|
| Production Beam | new, child of nothing, links WO | Beam ID, work order, length (m), loom/workstation, planned rolls, yarn batch, status |
| Roll Ticket (existing, evolve) | keep | Roll ID, beam, WO, job card, meters, picks/cm, current operation, status, final A/B/C. Replaces Roll Chain |
| Roll Inspection | new, submittable | Roll, stage (Gray / Finishing / Final), A/B/C piece counts, defects, inspector. Replaces custom use of Quality Inspection |
| Roll Grade Movement | child | Packing upgrades/downgrades (from, to, qty, reason). Reuse `DESAR Grade Adjustment` |
| Chemical Consumption | child of Roll or Job Card | Actual chemical qty per roll, summed into the end Stock Entry |
| Loom Ticket | print format on Production Beam / Roll | Machine, PO, design, size, rolls, weft, flower yarn, picks/cm |
| Work Order paper | print format on Work Order | Warp repeat table, beam table, as on the paper form |

DESAR Production Order: keep as a thin "Order Dossier" (read-only dashboard: SO, PP, WOs, beams, rolls, yield) or drop it and use a Work Order custom tab. Decision D5.

### 2.4 Stock and grades

- Start: standard "Material Transfer for Manufacture" on the Work Order (1 SE).
- End: standard "Manufacture" SE. Finished item = Shemagh grade A. Grade B (sellable, own item variant) and grade C (scrap warehouse, zero or salvage value) added as additional output rows from the Packing Entry totals. If v15.83 does not accept multiple finished rows cleanly, fall back to Manufacture for A plus one Repack for B/C. Verify in the tracer bullet (D4).
- Grade valuation: split cost by a configurable ratio on Grade Configuration, but default to standard cost allocation, not invented 60 % / 20 %. Business owner confirms (D4).
- Gray and finishing grades: recorded only, no stock movement. Matches factory.
- Result: 2 Stock Entries per Work Order, regardless of roll count.

### 2.5 Roll lifecycle and tracking

Roll status derives from the latest Roll Inspection and Packing Entry, not from stored state strings. Roll Ticket shows a timeline: weaving, gray inspection, finishing, final, with beam, loom, meters, chemical use and grade history. Roll Life Tracker report reads it directly. Cancelling an inspection reverts by deleting a document, with no revert layer.

### 2.6 Reports

- Yield per Work Order, beam, roll: total, A, B, C, yield %, scrap %.
- Grade movement report (upgrades/downgrades at packing).
- Cost per Work Order (standard: material + Job Card + additional cost) and cost per piece by grade.
- WIP by operation: rolls at gray, finishing, packing.
- Chemical standard vs actual.

### 2.7 Two user groups, two UIs

| Group | Does | Where |
|-------|------|-------|
| Technical (planner, ERP user) | Sales Order, Production Plan, BOM, Work Order, create Beams, reports, cancel/correct | Desk (standard forms, tabs and column breaks per CLAUDE.md) |
| Factory worker (low technical skill) | Warping, weaving, inspections, finishing, packing | Tablet app in `frontend/` (Frappe UI, espresso), no Desk access |

Hand-off: the technical user submits the Work Order and clicks "Create Beams" (beam length, loom, planned rolls, taken from the paper work order). From then on the worker only sees tasks.

### 2.8 Shop-floor tablet app

Rules: one task per screen, big touch targets (48 px minimum), numeric steppers instead of keyboards, no ERP words (no "Stock Entry", "Work Order", "Batch"), plain error messages ("Moved pieces are more than Grade B pieces available"), confirm before every save, undo for 10 minutes by the same worker.

Login: a Frappe user per worker with role `DESAR Factory Worker`, limited to the DESAR API methods. Quick login by PIN on a shared tablet is an option (question Q3 below).

Screens:
1. Home: tiles per station (Warping, Loom, Gray Inspection, Chemical Finishing, Finishing Inspection, Packing) with counts of waiting items. Worker sees only stations allowed by role.
2. Task list: cards for beams or rolls waiting at that station (Beam ID or Roll ID, design, size, loom, meters). Scan the printed QR or tap a card.
3. Beam screen: start weaving, set number of rolls actually produced, loom assigned. Creates Roll IDs and prints Roll Tickets with QR.
4. Roll screen: timeline of the roll, one big "next step" button. Only the step the roll is ready for is enabled.
5. Inspection screen: see 2.9.
6. Packing screen: sub-steps (classify, cut, finish pieces, steam, iron, stamp, box) as a tick list, then the packing inspection.
7. Supervisor screen: approve and submit inspections, fix mistakes, see station status. Role `DESAR Supervisor`.

Language: English plus translated labels (Arabic/Urdu/Hindi) through standard Frappe translations; right-to-left layout supported. Confirm needed languages (Q4).

Print: Roll Ticket and Loom Ticket print formats with QR for scanning.

### 2.9 Inspection design (decided)

One `Roll Inspection` doctype for three stages: Gray, Finishing, Final (Packing). Grades A, B, C only; grade X on the process chart is ignored. C is scrap.

Flow per roll:
1. Gray inspection: no previous stage. Worker enters assumed piece counts A / B / C. Save, submit.
2. Finishing inspection: the form opens with the Gray closing counts copied into an Opening table (read-only). Worker adds movement rows (from grade, to grade, qty, reason, any grade to any grade) and optional process loss. The closing A/B/C updates live. Save, submit.
3. Final (Packing) inspection: opening copied from the Finishing closing. Worker adds movement rows, then types the REAL final A/B/C pieces counted after cutting, steaming and ironing. System computes the difference between "opening plus movements" and the real counts per grade.
   - Fewer pieces than expected: the difference must be assigned to a process loss row with a reason.
   - More pieces than expected (cutting gave extra): recorded as a count gain with a reason.
4. Submitting the Final inspection fixes the roll's final A/B/C. The Work Order's end Manufacture Stock Entry sums these across rolls: A to the Shemagh A item, B to the B item, C to scrap warehouse as a scrap item. Process loss posts nothing.

Rules:
- A movement cannot exceed the opening count of its source grade (after earlier rows on the same form).
- Reason is required on every movement and every loss row.
- Submitted inspection is read-only. Correction = technical user cancels and amends; later inspections that depend on it must be cancelled first (same safety as today).
- Gray and Finishing counts are assumed, so no total check against meters. Only Final records real counts.

Reasons (configurable master, seeded with these):
- Grade movement reasons: Chemical finishing improved, Ironing/steaming corrected, Re-inspection correction, Damage in handling, Damage in cutting, Stain or burn, Machine damage, Other (remark required).
- Process loss reasons: Shrinkage, Cutting waste, Edge/selvedge trimming, Sample or test piece, Unaccounted/missing, Other (remark required).

Reports from these rows: upgrades and downgrades per roll, beam, Work Order; loss % by reason; scrap %; yield %.

### 2.10 What gets deleted

Stage Configuration, Stage Operation, legacy BOM mode, Roll Chain (18 status columns), per-roll Work Order cloning, beam split Repack, the three rounding hooks (no fractional sub-assemblies exist), Grade-adjusted Repack per roll, `temp_script.py`, hard-coded item names. Roughly 40 % of today's service and event code.

## Part 3. Tracer-bullet plan

Per CLAUDE.md: thin slice through every layer first. Track each phase in `PROGRESS.md`.

| Phase | Slice | Done when |
|-------|-------|-----------|
| 0 | Resolve decisions D1-D6 below; confirm site name; load real Work Order and Loom Ticket examples as seed data | Decisions written in this file |
| 1 (tracer) | One design (563, size 60): BOM + Routing, one Work Order, 1 Production Beam, 2 Rolls, Gray Inspection, Finishing Inspection, Packing Entry, 2 Stock Entries | End-to-end test passes; Manufacture SE posts A/B/C correctly; yarn out once, FG in once |
| 2 | Multiple beams and looms per Work Order, parallel Job Cards, Loom Ticket + Work Order print formats | Paper forms reproduced from system |
| 3 | Chemical actual consumption, grade valuation, B-grade sales item and price | Cost report matches manual calculation |
| 4 | Reports: yield, grade movement, cost, WIP; Order Dossier | Numbers match the tracer-bullet data |
| 5 | Tablet shop-floor app (2.8) and Roll Inspection screens, built beside Phase 1 screens; remove Desk pages | A worker with no ERP training completes a roll on a tablet without Desk |
| 6 | Migration: in-flight orders finish on old flow; new orders on new flow; patch to map Roll Ticket and Roll Chain data; delete old code | Old tests removed, new tests cover the same rules |
| 7 | Hardening: Playwright e2e, CI on a real site, doc cleanup (one guide) | CI green on fresh site |

Tests: real-document tests with `FrappeTestCase` (auto rollback), no mirror tests. Each phase ships its tests.

## Part 4. Decisions needed from you

- D1. Single Work Order per final product with Beam / Roll documents (recommended, matches the client review) versus keep staged Work Orders. This is the one decision that sets the scope.
- D2. Are Beam and Roll tracked only as documents, or do you also need stock quantity of beams or rolls in a warehouse (for example grey roll held in store)?
- D3. Which steps need Job Cards: only Weaving and Chemical Finishing (recommended), or also inspections? Packing without Job Cards per the client document; is Packing labour still costed some other way?
- D4. Grade B/C inventory: separate Item variants per grade (today) versus by-product rows. Grade valuation: standard cost split or fixed percentages?
- D5. Keep DESAR Production Order as a dashboard document, or drop it?
- D6. Migration: how many orders are in flight on the old flow in production (st-prod?), and can they finish on the old flow?

## Decided so far

- Grades are A, B, C only. X is ignored. C is scrap.
- Roll Inspection prefills from the previous stage, worker edits movements, saves and submits.
- Packing records the real final counts. Process loss and scrap are separate; scrap goes to the scrap warehouse, process loss posts nothing.
- Technical users plan in Desk; factory workers use a tablet app only.
- Workers have individual logins. Supervisor assigns work and roles; a worker sees only assigned tasks (reuse `Job Card-custom_assigned_to`).
- Languages: English and Arabic.
- Packing sub-operations (classification, cutting, piece finishing, steaming, ironing, stamping, boxing) are Job Cards, as in the process chart.

- D2: no stock between stages, confirmed. D5: keep DESAR Production Order for now. D6: site is `tzamun` (ERPNext 15.121.5, 1 Production Order, 8 Design Masters, 2 Roll Tickets, 39 Work Orders, 32 Stock Entries); keep existing data, old order finishes on old flow, new flow switched per Design Master.
- D4 partly: A and B valued, C zero value in scrap warehouse. A:B valuation split still to confirm.

Still open: D1 (one Work Order per design+size, see reply), D4 valuation split, inspection template naming. Earlier list: (D3 is narrowed: Job Cards for Weaving, Chemical Finishing and Packing sub-operations; inspections are roll documents).

## Risks

- The client review and the staged flow in the code disagree. If the ST team already agreed the staged design, Part 2 is a bigger change than assumed.
- ERPNext v15.83 behaviour for multiple finished items in one Manufacture SE must be checked in Phase 1 before relying on it.
- Existing data (Roll Tickets, Batches, Work Orders) needs a migration path; Phase 6 depends on D6.
