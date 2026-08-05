# DESAR Manufacturing — Complete System Reference

Everything in this system: every doctype, every field, why it exists, where its
value comes from, and how the pieces connect end to end. Written for
presentation prep — if someone asks "why does X happen" or "where does that
number come from," the answer is in here.

Site: `excel`. Demo scenario used throughout: Design 560 (sizes 55/58/60,
article "Zephyr") and Design 561 (sizes 55/58/60/62, article "Atlas"), one
Sales Order, 7 Design/Size lines, 15% production buffer.

---

## 1. The big picture

Two layers work together:

- **Core ERPNext** (unmodified): Sales Order → Production Plan → Work Order →
  Stock Entry → BOM → Item. Standard manufacturing primitives, untouched.
- **DESAR custom layer**: everything ERPNext has no native concept for —
  rolls, beams, grade splitting, stage-by-stage QC, and traceability. Built
  as data-driven configuration (Stage Configuration table) so adding a new
  production stage never requires a code change.

```
Sales Order (core)
   → Production Plan (core, + DESAR: buffer %, warehouse autofill)
      → Work Order × 5 stages per design (core, + DESAR: design context autofill)
         → DESAR Production Order (custom — the shop-floor "flight recorder")
            → Warping → Beam Split → [per roll: Grey → Finished → Packing → QI → Repack]
```

---

## 2. Master data — what needs to exist before you sell anything

### 2.1 Items

Three kinds, three different rules:

| Kind | Examples | Shared across designs? | How created |
|---|---|---|---|
| Raw material | `Yarn-100-2-White`, `Boxes`, `Chemical Materials` | Yes — plain, ordinary Items | Manual, one per material |
| Shared WIP (intermediate) | `Warping Beam`, `Beam Roll`, `Grey Roll`, `Finished Roll` | **Yes, same item name for every design** — this is deliberate, tracked apart by Batch, not by item code | Created once, reused forever |
| Finished good | `Shemagh-ZEP-55-A`, `Shemagh-ATL-62-C` | No — one per Design×Size×Grade | **Real ERPNext Item Variants** (see 2.2) |

**Why WIP items are shared**: a "Grey Roll" from Design 560 and a "Grey Roll"
from Design 561 are physically different fabric, but the system tracks that
difference via **Batch** (each Work Order's Manufacture Stock Entry creates a
distinct batch) and via **BOM chain linkage** (`bom_no`, section 3.2), not by
giving each design its own item name. This is what caused the biggest bug
found this session — see section 8.1.

### 2.2 Finished goods are real Item Variants, not hand-typed Items

Item **`Shemagh`** has `has_variants=1` with 3 attributes, in this exact order:

1. **Article** (values: Vicente/VIC, Vesenti/VES, Classic/CLS, Premium/PRM, Zephyr/ZEP, Atlas/ATL — abbreviations in parentheses)
2. **Shemagh Size** (55, 58, 60, 62 — abbreviation = same as the value)
3. **Grade** (A/B/C)

ERPNext's own variant-naming rule concatenates attribute abbreviations in
that order: `{template}-{Article.abbr}-{Size.abbr}-{Grade.abbr}` →
`Shemagh-ZEP-55-A`. This is not a coincidence the code depends on — it's what
clicking **Create Variants** on the `Shemagh` item does automatically. All 21
of this demo's finished items (7 Design×Size × 3 Grades) are real variants,
each with `variant_of = Shemagh` and a proper `Item Variant Attribute` row set.

**Why this matters for the presentation**: nothing downstream (BOM, grading,
Repack) cares whether an item code came from a real variant or a hand-typed
Item — every consumer just reads the item code string. Variants are a
catalog-quality choice (reporting, no typos, no duplicate-name risk), not a
functional requirement.

### 2.3 DESAR Settings (singleton) — every warehouse, one place

| Field | Warehouse (this demo) | Used by |
|---|---|---|
| Yarn Store | Yarn Store - ST | Warping stage's raw material source |
| Chemical Store | Chemical Store - ST | Finished Roll stage's chemical source |
| Accessories Store | Accessories Store - ST | Packing stage's Box/Stamp/Sticker source |
| Warping WIP | Warping WIP - ST | Warping Beam & Beam Roll's home |
| Loom Floor | Loom Floor - ST | Grey Roll's home |
| Grey Roll Store | Grey Roll Store - ST | (legacy-mode Finished Roll BOM source; unused in dynamic mode) |
| Finishing WIP | Finishing WIP - ST | Finished Roll's home |
| Finished Roll Store | Finished Roll Store - ST | (legacy-mode Packing BOM source; unused in dynamic mode) |
| Cutting & Packing Floor | Cutting and Packing Floor - ST | Packing stage's WIP location |
| FG - Grade A / B | Finished Goods Grade A/B - ST | Repack SE target (legacy mode) |
| Scrap Yard | Scrap Yard - ST | Work Order scrap warehouse |

Plus **Grade Configuration** (a child table on this same singleton) — one row
per grade, each with: `grade_code` (A/B/C...), `grade_label`, `valuation_pct`
(100/60/20), `target_warehouse` (where that grade's stock lands — can be a
*different* warehouse per grade, e.g. Grade C could route to a discount-goods
warehouse instead of the header-level "FG - Grade B" field), `item_suffix`
(`-A`/`-B`/`-C`), `is_scrap` (if checked, that grade is disposed — consumed
but never given a valued stock row).

**Why a table instead of fixed A/B/C fields**: a client can add Grade D
tomorrow by adding one row here — every piece of code (BOM generation, QI
validation, Repack) reads this table, nothing is hardcoded to 2 or 3 grades.
This is "dynamic mode." An empty table falls back to "legacy mode"
(hard-coded A=100%/B=60%, C=disposed) — kept only for backward compatibility
with designs built before Grade Configuration existed.

### 2.4 Warp Recipe — yarn quantities, per Design×Size

See the earlier detailed walkthrough (Part 6 below has the field table). One
recipe per Design×Size, linked from that Design Master's **Warp Recipe**
field. Only ever read by `bom_service.py` when building the Warping stage's
BOM — nothing else touches it.

### 2.5 Design Master — one per (Design, Size)

**Confirmed convention, not a guess**: one Design Master = one specific size,
even though it has a `sizes` field that looks like it should hold "55,58,60" —
that field is informational only. The *actual* production Design 563 in this
system has `sizes="55,58,60,62"` but only ever built a BOM for its single
`default_size`. So Design 560 (3 sizes) + Design 561 (4 sizes) = **7 Design
Masters**, not 2.

| Field | Purpose |
|---|---|
| Design No. / Article Name | Identity — `560`/"Zephyr", `561`/"Atlas" |
| Sizes | Informational only, comma text |
| Default Size | The *one* size this specific Design Master is actually for |
| Warp Recipe | Link to section 2.4 |
| Weft Recipe | **Exists in the schema, read by nothing** — dead field, safe to ignore |
| Finish/Wash/Flower Chemical (Litre) | Legacy 3 fixed chemical fields — left at 0 in this demo, since the source data only gave one lump "Chemical Materials (Kg)" figure, not litres split 3 ways |
| Chemical Materials (Kg) | **New field, added this session.** Feeds the Finished Roll stage's BOM |
| Pieces per Roll | How many finished pieces one physical roll yields — `115` in this demo, chosen so 575÷115=5 and 230÷115=2 (no partial rolls) |
| Branded Box Item / Label/Stamp Item / Sticker Item | Link to the 3 packing accessories — Sticker Item is **new this session** (previously only 2 slots existed) |
| BOM L1-L4 | Read-only, auto-filled when you click Create All BOMs (legacy-mode naming — still shown even in dynamic mode, just shows the Warping/Grey/Finished/Packing chain) |
| Stage Configuration | The table that drives everything — see 2.6 |

### 2.6 DESAR Stage Configuration — the data-driven engine

One row per production stage, in `stage_seq` order. This table is why adding
a new stage (say, a dyeing step) never needs a code change — every service
(`bom_service.py`, `roll_service.py`, `production_plan_service.py`,
`events/work_order.py`) reads this table to know what to do.

| Field | Purpose |
|---|---|
| Stage Seq / Stage Name | Order and label — "Warping", "Beam Split", "Grey Roll", "Finished Roll", "Packing" in this demo |
| Output Item | What this stage produces — `Warping Beam`, `Beam Roll`, `Grey Roll`, `Finished Roll`, and the specific `Shemagh-X-Y-A` for Packing |
| Output Qty | How much — `1` for intermediate stages, `115` (=pieces_per_roll) for Packing |
| QI Required | Checkbox — if set, a QI button appears after this stage's Work Order completes |
| QI Template | Which Quality Inspection Template to use — `Grey Inspection - Shemagh`, `Finishing Inspection - Shemagh`, `Final Packing Inspection - Shemagh` (shared across all designs, not design-specific) |
| Sample Size Formula | `1` (inspect one roll) or `wo_qty` (inspect every piece) — Packing always uses `wo_qty` since grade counting needs every piece checked |
| Roll Ticket Trigger | If checked, submitting this stage's Manufacture SE auto-creates a Roll Ticket — set on Beam Split and Grey Roll |
| Skip Transfer | If checked, raw materials backflush automatically, no manual Transfer SE — used for Warping (keyword-matched, see below) |
| Is Final Stage | If checked, submitting this stage's QI auto-triggers the Repack SE — only Packing has this |
| BOM (bom_no) | Read-only, auto-filled by Create All BOMs — this is the field that makes the whole shared-WIP-item architecture work (section 8.1) |
| Operations | **Known dead end — do not use.** A nested child table (Operations inside a Stage Configuration row) that Frappe cannot reliably save/reload two levels deep. Confirmed by direct testing. Leave empty on every row; workstations are resolved another way (section 3.3) |

---

## 3. BOM generation — turning master data into a production recipe

### 3.1 The chain, concretely (Design 560, size 55)

```
Warp Recipe (yarn kg)
   → BOM: Warping Beam    consumes: Yarn-100-2-White, Yarn-34-2-White, Yarn-34-2-Red
   → BOM: Beam Roll        consumes: Warping Beam (1 unit)
   → BOM: Grey Roll        consumes: Beam Roll (1 unit)
   → BOM: Finished Roll    consumes: Grey Roll (1 unit) + Chemical Materials
   → BOM: Shemagh-ZEP-55-A consumes: Finished Roll (1 unit) + Boxes + Stamps + Stickers
```

5 BOMs per Design Master × 7 = **35 BOMs total** for this demo. Click "Create
All BOMs" on each Design Master — `bom_service.py::BOMService.create_all_boms()`
walks the Stage Configuration table in order and builds each one.

### 3.2 The bug that mattered most: `bom_no` chain linking

Every BOM Item row that references a *manufactured* component (e.g. "Grey
Roll" as an input to "Finished Roll") has a `bom_no` field — this tells
ERPNext's multi-level explosion **exactly which BOM to follow** for that
component. Miss it, and explosion falls back to "whichever BOM currently
happens to be flagged default for that item name" — which is wrong the
instant two designs share an item name (every design here does, for all 4
WIP items).

`bom_service.py`'s `_make_bom_item()` now always sets this explicitly,
threading each stage's own `bom_no` down to the next. This is *the* reason 7
different designs, all sharing "Warping Beam"/"Grey Roll"/"Finished Roll" as
item names, each correctly explode into their own distinct yarn/chemical
quantities instead of everyone accidentally using Design 560/55's numbers.

### 3.3 Workstation resolution — 3 ways, in priority order

Every BOM needs at least one Operation for `with_operations`. Since the
per-stage Operations table (section 2.6) doesn't work, resolution goes:

1. Does an `Operation` master record named exactly the stage name (e.g.
   "Beam Split") have a `Workstation` set? Use it.
2. Else, keyword-match the stage name against a fixed dict (`warp`→Warping
   Machine, `weav`→Loom 62, `pack`→Cutting Table, etc.) and use that
   Workstation if it exists.
3. Else, throw — no silent guessing.

Three stage names in this app (`Beam Split`, `Grey Roll`, `Finished Roll`)
match **no** keyword and had no Operation workstation set — fixed this
session by assigning them one directly (Sorting Table, Loom 62, Finishing
Machine respectively).

---

## 4. Sales Order → Production Plan

### 4.1 Sales Order

Plain core ERPNext. 7 lines, one per Design/Size variant, at real sales qty
(500×3 for 560, 200×4 for 561).

### 4.2 Production Plan — where planned qty gets decided

**"Get Items"** pulls Sales Order qty into `planned_qty` 1:1 — core has no
concept of a manufacturing-loss buffer. We added one:

- **Production Buffer %** (new custom field on Production Plan). Set it to
  `15`, save (while still Draft) — `events/production_plan.py`'s `validate()`
  hook recomputes every Sales-Order-linked line's `planned_qty` from the
  **Sales Order Item's own `qty`** (500 → 575, 200 → 230).
- **Why not read from `pending_qty`** (the obvious "current planned qty"
  field): core ERPNext has a real bug — `set_pending_qty_in_row_without_reference()`
  uses `if not sales_order or not material_request` (an `or`, should be
  `and`), so it resets `pending_qty = planned_qty` on *every* save for *any*
  Sales-Order-linked row (they never have `material_request` set). Reading
  from `pending_qty` would compound the buffer every time you resave
  (500→575→661→...). Reading from the Sales Order Item's real `qty` sidesteps
  that bug entirely — it's never touched by any of this.

### 4.3 Get Sub Assembly Items — per-item target warehouse

Core only fills each row's `fg_warehouse` when the *whole plan* has one
uniform "Sub Assembly Warehouse" set — doesn't fit here (4 different WIP
items, 4 different warehouses). Same `validate()` hook auto-fills per item,
straight from DESAR Settings, **always overriding** (not just filling
blanks — Item Default fallback can leave a wrong-but-not-blank value):

`Warping Beam`/`Beam Roll` → Warping WIP · `Grey Roll` → Loom Floor ·
`Finished Roll` → Finishing WIP.

### 4.4 Create Work Order — and the second big bug

Clicking this on the Production Plan explodes `sub_assembly_items` +
`po_items` into real Work Orders — **5 per design** (4 WIP stages + 1
finished good) × 7 = 35.

**The bug**: `Production Plan.create_work_order()` sets
`wo.flags.ignore_validate = True` before every single insert it makes. That
flag skips `validate()` entirely — including the hook that copies
`custom_design_master` from each Work Order's BOM onto the Work Order itself.
Confirmed by testing: calling the design-context logic directly always
worked; going through Production Plan's real bulk-creation path, it never
ran. Fixed by moving that logic into `before_validate` (which Frappe's own
`run_before_save_methods()` always calls before checking the
`ignore_validate` flag — confirmed by reading Frappe core directly). Now all
35 Work Orders self-link to their Design Master with zero manual patching,
regardless of whether there are 35 or 35,000.

Note: **Beam Roll never appears as a Work Order in the final state** — see
5.2, it's deliberately deleted.

---

## 5. DESAR Production Order — the shop-floor flight recorder

### 5.1 Fields

| Field | Purpose |
|---|---|
| Sales Order / Production Plan / Design Master | Identity links |
| Total Qty (pcs) | The real planned qty for this design/size — `575` or `230`, resolved from the Sales-Order-linked `po_items` row, **not** an MRP estimate |
| Pieces per Roll | Copied from Design Master at creation time |
| Roll Count | Blank until Beam Split — set automatically then |
| Status | Draft → Submitted → In Progress → Completed |
| Warping WO / Batch / Status / Transfer SE / Manufacture SE | Stage 1 tracking |
| Beam Split SE / Status | Stage 2 tracking (a Stock Entry, not a Work Order — see 5.2) |
| Roll Chains | One row per physical roll, created at Beam Split — see 5.3 |

### 5.2 Why "Beam Split" has no Work Order

MRP auto-creates a "Beam Roll" Work Order (since it has a BOM) alongside
Warping Beam/Grey Roll/Finished Roll. **This gets deliberately deleted** the
moment you click "Create DESAR Production Order"
(`production_plan_service.py::_configure_warping_wo`). Beam Split is instead
a **Repack Stock Entry**: consumes one Warping Beam batch, produces N Beam
Roll batches (one per physical roll). Why not a Work Order: the roll count
and per-roll split sizes aren't known until a supervisor physically looks at
the beam and decides — a Work Order needs a fixed quantity up front, which
doesn't fit "decided later."

### 5.3 DESAR Roll Chain — one row per physical roll

Created when Split Beam runs. Tracks each roll's Grey Roll → Finished Roll →
Packing progress independently: WO, Batch, QI, and status (`Locked` until the
previous stage completes) for each of the 3 stages, plus the `repack_se` link
(recorded as soon as the Repack SE is created, even in Draft, so it's never
orphaned if you navigate away before submitting).

---

## 6. Warp Recipe — field reference (for completeness)

| Field | Fill with |
|---|---|
| Recipe Name | Free text identifier, e.g. `WR-560-55` |
| Design No. / Size | Matches the Design Master |
| Planned Qty (Pieces) | This size's planned qty, e.g. `575` — only matters for Rate-based rows |
| Total Yarn (Kg) | Read-only, auto-sums all rows |
| *(per row)* Yarn Item | The actual stock Item |
| *(per row)* Yarn Count / Color | Descriptive text only — not read by any code |
| *(per row)* Rate (Kg/Piece) | Optional — if set, `Qty (Kg) = Rate × Planned Qty`, computed on save |
| *(per row)* Qty (Kg) | The real BOM quantity — auto-filled if Rate is set, type it directly otherwise |

**Rate is per-design, constant across all its sizes** (it's cost-per-piece,
not cost-per-size): `rate = design's total kg ÷ design's total planned qty
across all sizes`. Design 560: 300kg÷1725=0.173913 (White), 50kg÷1725=0.028986,
200kg÷1725=0.115942 — same 3 numbers on all 3 of its Warp Recipes.

---

## 7. The shop-floor cycle — per DESAR Production Order

**Once per PO** (e.g. `DESAR-PO-2026-00047`, Design 560/55, qty 575):
1. **Start Warping** → submits Warping WO, drafts a Transfer SE.
2. Submit that Transfer SE (raw yarn issue).
3. **Complete Warping** → Manufacture SE, produces the Warping Beam batch.
4. **Split Beam** → rows summing to Total Qty in multiples of Pieces per
   Roll (5 rows of 115 for a 575-qty PO). Creates the Beam→Beam Roll Repack
   SE and splits the combined Grey/Finished/Packing Work Orders into one set
   per roll.

**Per roll** (5× for a 575-qty PO, 2× for a 230-qty PO — 23 total across this
demo):
5. **Start Grey Roll** → submit Transfer SE.
6. **Complete Grey Roll** → Manufacture SE + auto-QI (Grey template). Fill
   Grade A/B/C piece counts, submit.
7. **Start Finished Roll** → submit Transfer SE. **Chemical Materials is
   consumed here** — no separate "chemical finishing" action, it's just this
   stage's BOM.
8. **Complete Finished Roll** → Manufacture SE + auto-QI (Finishing
   template).
9. **Start Packing**.
10. **Complete Packing** → drafts a Manufacture SE deliberately (supervisor
    review checkpoint) — open and submit it.
11. **Finalize Packing** → Final QI (`wo_qty` sample size — every piece
    counted). If the grade total differs from the Finishing QI's, the Grade
    Adjustments table must be filled (e.g. "3 pcs upgraded B→A") before
    submission is allowed. Submitting triggers the **Repack SE** — see 7.1.
12. **Complete Roll**.

### 7.1 Quality Inspection — fields that matter

- `custom_desar_stage_name` — which stage this QI belongs to (Grey/Finished
  Roll/Packing), set at creation.
- `custom_desar_grade_readings` (child table) — one row per grade, qty
  counted. Must sum to the Work Order's qty or submission is blocked.
- `custom_desar_grade_adj_section` / `custom_desar_grade_adjustments` — only
  shown/required on Packing stage QIs, when the Final count differs from the
  Finishing-stage count.
- `custom_roll_ticket` — auto-linked at creation for fast lookup.

### 7.2 Repack Service — grade valuation

Triggered by `events/quality_inspection.py::on_submit` when the just-submitted
QI's stage `is_final_stage`. Reads Grade Configuration (dynamic mode) or
falls back to hardcoded A=100%/B=60%/C=disposed (legacy mode). For each
non-scrap grade: derives the item code by suffix (`Shemagh-ZEP-55-A` →
`-B`/`-C`), values it at `base_valuation_rate × grade.valuation_pct / 100`,
and moves stock into that grade's `target_warehouse`.

**A real bug fixed here**: the outgoing (consumed) line was sourced from
`cutting_packing_warehouse` — a WIP staging warehouse — but the Packing Work
Order's actual output lands in `fg_grade_a_warehouse`. The item was never
physically in the warehouse the Repack tried to consume it from, so Frappe
couldn't find a valuation rate and the whole Stock Entry failed to insert
(caught, logged to Error Log, silently skipped — the QI submission itself
still succeeded, which is why it looked like "everything worked but no
Repack appeared").

### 7.3 Roll Ticket — the traceability ledger

Auto-created at Grey Roll (per Stage Configuration's `roll_ticket_trigger`).
One row in `DESAR Roll Ticket Stage Grade` per (stage, grade) combination,
populated every time a QI is submitted for that roll — this is the complete,
queryable history of "how much of this exact roll ended up as Grade A vs B
vs C, at every stage."

---

## 8. Known architecture decisions — the "why" behind the odd parts

### 8.1 Why WIP items are shared across designs (and what that costs)

Sharing "Grey Roll" etc. as one item name across all designs keeps the Item
list small and matches how a real factory floor talks about the product (a
grey roll is a grey roll, regardless of which design). The cost: every BOM
chain link needs an *explicit* `bom_no` (section 3.2) or explosion silently
uses the wrong recipe. This is the single most consequential design decision
in the whole system — it's what made the multi-design Production Plan bug
possible, and fixing `_make_bom_item()` to always pin `bom_no` is what makes
it safe.

### 8.2 Why Grade isn't a variant attribute, but Design/Size are

Design/Size are known at *order time* — a customer orders a specific
Design×Size, so they're real catalog attributes. Grade is only known *after*
production (QI result) — you don't sell "Grade B" on purpose, it's a yield
outcome. Modeling it as a suffix-derived sibling item (not a variant
selection) matches that reality.

### 8.3 Why the 15% buffer is a Production Plan field, not a Sales Order one

The buffer is a *manufacturing* decision (loss allowance), not a *sales*
commitment — the customer is owed 500 pieces regardless of how many you plan
to produce to get there. Keeping it on Production Plan means the Sales Order
stays a clean record of what was promised.

### 8.4 Why some things are wrapped in try/except and fail silently

Several DESAR hooks (`_autofill_warehouses`, `_apply_skip_transfer`, Repack
creation) catch their own exceptions and log to Error Log + show an orange
`msgprint` instead of blocking the parent action (Work Order save, QI
submit). Deliberate: a warehouse-autofill failure shouldn't block someone
from submitting a Quality Inspection. The tradeoff — and the reason several
bugs in this session took real investigation to find — is that "it didn't
error" doesn't mean "it worked." Error Log is the first place to check
whenever something *should* have happened automatically and didn't.

---

## 9. Likely presentation questions

**"Why 7 Design Masters and not 2?"** — One Design Master = one size, by
confirmed system convention. 3 sizes (560) + 4 sizes (561) = 7.

**"Why 35 BOMs for what's conceptually 2 products?"** — 5 stages × 7
Design/Size combos. Each stage's BOM is genuinely different per size (yarn
qty scales with size), so this isn't waste — it's real distinct recipes.

**"Where does the 115 pieces-per-roll number come from?"** — Chosen, not
derived: it's the largest number that divides both 575 and 230 evenly (no
partial rolls). Not a physical constraint from the source data.

**"How does the system know Grade B is worth 60%?"** — DESAR Settings' Grade
Configuration table, one row per grade, editable without touching code.

**"What happens if I add Grade D?"** — Add a row to Grade Configuration.
Repack, QI validation, and Roll Ticket reporting all read that table — no
code change needed.

**"Why doesn't Beam Split show up as a Work Order?"** — Deliberately deleted;
it's a Repack Stock Entry instead, because roll count isn't known until a
human decides it at Split Beam time.

**"Is the 15% allowance automatic?"** — Yes, via the Production Buffer %
field, but only while the Production Plan is still Draft — it deliberately
stops recomputing after submit so it can't corrupt an in-progress qty.
