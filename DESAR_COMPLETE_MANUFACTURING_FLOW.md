# DESAR Factory — Complete Manufacturing Flow, Start to Finish

A single continuous walk-through of everything that happens, in the order it
happens, from raw yarn to a packed, costed, traceable Shemagh in a Finished
Goods warehouse. Every doctype, every field, every warehouse, every
automatic vs manual step, in sequence. Site: `excel`.

Worked example used throughout: Design 560 "Zephyr" (sizes 55/58/60, 500 pcs
sold each) and Design 561 "Atlas" (sizes 55/58/60/62, 200 pcs sold each), one
Sales Order, 15% production buffer, 115 pieces per physical roll.

---

## Phase 0 — Master data that must exist before anyone sells anything

Nothing below can happen until this phase is done. It's one-time setup per
new Design; it never repeats for a re-order of the same design.

### 0.1 Raw material Items

Plain ERPNext Items, one per distinct material — a material is defined by
**spec + color**, not just type:

- Yarn: `Yarn-100-2-White`, `Yarn-34-2-White`, `Yarn-34-2-Red`, `Yarn-34-2-Brown`, `Yarn-20-2-Beige` (Item Group "Yarn", UOM Kg)
- Packing accessories: `Boxes` (Packing Material), `Stamps` (Accessories), `Stickers` (Accessories) — all UOM Nos
- `Chemical Materials` (Item Group Chemicals, UOM Kg)

Each gets an **Item Price** (Standard Buying) and opening stock via a **Stock
Entry (Material Receipt)** into its home warehouse (Phase 0.4). No Item Price
= the item can still be produced with, but nothing values it until it's
consumed somewhere with a real rate on record.

### 0.2 Shared WIP (intermediate) Items — created once, forever

Four items, same name used by **every** design that will ever exist in this
factory: `Warping Beam`, `Beam Roll`, `Grey Roll`, `Finished Roll`. All 4 are
**batch-tracked** (`has_batch_no=1`) — the item name never changes between
designs, only the Batch number does. This is a deliberate factory-floor
convention (a grey roll is a grey roll, regardless of whose design it's
weaving) that has one real cost: every BOM that consumes one of these 4 items
must pin an exact `bom_no` to it (Phase 0.6) or ERPNext will silently use the
wrong recipe the moment two designs share the shop floor.

### 0.3 Finished-good Items — real ERPNext Item Variants

Not hand-typed Items. Item **`Shemagh`** is a template (`has_variants=1`)
with 3 attributes, in this exact order: **Article** (Zephyr/ZEP,
Atlas/ATL, plus pre-existing Vicente/VIC, Atlas/ATL, etc.), **Shemagh Size**
(55/58/60/62), **Grade** (A/B/C). Add any missing Article values, then click
**Create Variants** on the `Shemagh` item, selecting the right
Article×Size×Grade combinations. ERPNext's naming rule concatenates
abbreviations in that order: `Shemagh-ZEP-55-A`. 21 variants for this
example (7 Design×Size × 3 Grades). Nothing downstream cares that these are
"real" variants vs hand-typed — every consumer just reads the code string —
but it means proper `variant_of` lineage, no typo risk, and clean reporting.

### 0.4 DESAR Settings — the one place every warehouse is defined

A singleton. Every warehouse used anywhere in this flow is a Link field here
— nothing is hardcoded in code:

| Field | This factory's warehouse | Used at |
|---|---|---|
| Yarn Store | Yarn Store - ST | Warping — raw material source |
| Chemical Store | Chemical Store - ST | Finished Roll — chemical source |
| Accessories Store | Accessories Store - ST | Packing — Box/Stamp/Sticker source |
| Warping WIP | Warping WIP - ST | Warping Beam & Beam Roll's home |
| Loom Floor | Loom Floor - ST | Grey Roll's home |
| Finishing WIP | Finishing WIP - ST | Finished Roll's home |
| Cutting & Packing Floor | Cutting and Packing Floor - ST | Packing WIP location |
| FG - Grade A / Grade B | Finished Goods Grade A/B - ST | Where graded stock lands (legacy mode) |
| Scrap Yard | Scrap Yard - ST | Work Order scrap |

Plus the **Grade Configuration** table (same singleton): one row per grade —
`grade_code`, `valuation_pct` (100/60/20 in this factory), `target_warehouse`
(can differ per grade — Grade C could route somewhere entirely different),
`item_suffix` (`-A`/`-B`/`-C`), `is_scrap`. This table is what makes grading
"dynamic" — add a Grade D by adding a row, no code change, and every
consumer (BOM building, QI validation, Repack, Roll Ticket reporting) picks
it up automatically.

### 0.5 Warp Recipe — one per (Design, Size)

Parent fields: Recipe Name, Design No., Size, **Planned Qty (Pieces)**
(e.g. 575), Total Yarn (Kg) (read-only, auto-summed). Child rows (one per
yarn material): Yarn Item, Yarn Count/Color (descriptive text only — no code
reads these two), **Rate (Kg/Piece)** (optional), **Qty (Kg)** (auto-computed
as `Rate × Planned Qty` if Rate is set, typed directly otherwise).

Rate is per-*design*, constant across all its sizes, because it's a
cost-per-piece figure: `rate = design's total kg ÷ design's total planned
qty across every size`. Design 560's 3 sizes share equal planned qty (575
each), so: White 300kg÷1725=0.173913, 34/2-White 50kg÷1725=0.028986, 34/2-Red
200kg÷1725=0.115942 kg/piece — identical 3 numbers on all 3 of Design 560's
recipes, correctly reproducing 100/16.67/66.67 kg at Planned Qty=575.

### 0.6 Design Master — one per (Design, Size), not one per Design

Confirmed system convention: **Design 560 (3 sizes) + Design 561 (4 sizes) =
7 Design Masters**, not 2. Fields:

- Design No. / Article Name — identity
- Default Size — the one size this specific record is for (`Sizes` is
  informational text only, e.g. "55,58,60" — never read by code)
- Warp Recipe — link to 0.5
- Weft Recipe — exists in the schema, **read by nothing**, dead field
- Finish/Wash/Flower Chemical (Litre) — legacy fixed fields, left at 0 in
  this factory (no litre-split data was ever given for them)
- **Chemical Materials (Kg)** — feeds the Finished Roll BOM. Allocated
  proportional to each size's share of the *whole order's* total planned qty
  (not just its own design's): 21.74kg for each 560 size, 8.70kg for each 561
  size, out of a 100kg whole-order total
- **Pieces per Roll** — `115` in this factory, chosen because it divides
  both 575 and 230 evenly (5 rolls, 2 rolls — no partial rolls)
- Branded Box Item / Label/Stamp Item / **Sticker Item** — the 3 packing
  accessory links (Sticker Item added to this doctype specifically for this
  factory's 3-accessory scenario; the app only shipped with 2 slots)
- **Stage Configuration** — the table that drives literally everything from
  here on (0.7)
- BOM L1-L4 — read-only, auto-filled by Create All BOMs

### 0.7 Stage Configuration — the data-driven production sequence

5 rows, `stage_seq` 1-5, identical shape across all 7 Design Masters in this
factory:

| Seq | Stage | Output Item | Output Qty | QI? | QI Template | Sample | Roll Ticket? | Final? |
|---|---|---|---|---|---|---|---|---|
| 1 | Warping | Warping Beam | 1 | – | – | – | – | – |
| 2 | Beam Split | Beam Roll | 1 | – | – | – | ✓ | – |
| 3 | Grey Roll | Grey Roll | 1 | ✓ | Grey Inspection - Shemagh | 1 | ✓ | – |
| 4 | Finished Roll | Finished Roll | 1 | ✓ | Finishing Inspection - Shemagh | 1 | – | – |
| 5 | Packing | *this size's* Shemagh-X-Y-A | 115 | ✓ | Final Packing Inspection - Shemagh | wo_qty | – | ✓ |

`Operations` (nested child grid on each row) — **do not use**, confirmed by
direct testing this session that Frappe cannot reliably save/reload a child
table two levels deep. Workstations are resolved another way (0.8).

### 0.8 BOM generation — building the actual recipe chain

Click **Create All BOMs** on each Design Master. `bom_service.py` walks Stage
Configuration in order:

```
Warp Recipe (yarn kg)
  → BOM: Warping Beam    consumes yarn
  → BOM: Beam Roll        consumes Warping Beam (1)
  → BOM: Grey Roll        consumes Beam Roll (1)
  → BOM: Finished Roll    consumes Grey Roll (1) + Chemical Materials
  → BOM: Shemagh-X-Y-A    consumes Finished Roll (1) + Boxes + Stamps + Stickers
```

5 BOMs × 7 Design Masters = **35 BOMs**.

**The one detail that makes multi-design production work at all**: every
component row that references a *manufactured* item (e.g. "Grey Roll" as
Finished Roll's input) carries an explicit `bom_no` pointing at the exact
upstream BOM. Skip this and ERPNext's explosion falls back to "whichever BOM
currently happens to be flagged default for that item name" — silently wrong
the instant two designs share the item name, which they always do here.

**BOMs must be submitted bottom-up, one at a time.** `create_all_boms` keeps
every BOM in Draft (so you can review before activating), but ERPNext's own
BOM validation requires a referenced `bom_no` to belong to an already-
*submitted* BOM. So the real sequence per Design Master is: click Create All
BOMs (creates only stage 1's BOM) → open it, Submit → click Create All BOMs
again (creates stage 2's BOM, now correctly referencing stage 1) → Submit →
repeat for all 5 stages. 5 rounds of click+submit per Design Master, 35
total for this factory's 7.

Workstation resolution for the `with_operations` requirement, in priority
order: (1) an `Operation` master record named exactly the stage name with a
`Workstation` set, (2) a keyword match (`warp`→Warping Machine,
`pack`→Cutting Table, etc.), (3) throw. Three stage names here (`Beam
Split`, `Grey Roll`, `Finished Roll`) match no keyword and needed a
workstation assigned directly on their Operation record.

---

## Phase 1 — Sales

**Sales Order.** Plain core ERPNext. One order, one line per Design×Size
sold: `Shemagh-ZEP-55/58/60-A` × 500 each, `Shemagh-ATL-55/58/60/62-A` × 200
each. Set a rate per line (no sales price exists yet for these Item Variants
by default). Submit.

---

## Phase 2 — Planning

**Production Plan.** "Get Items" pulls Sales Order qty into `planned_qty`
1:1 — core has no manufacturing-loss-buffer concept.

**Production Buffer %** (custom field, this factory's addition): set to
`15`, save while Draft. `planned_qty` recomputes on every save from the
**Sales Order Item's own `qty`** — 500→575, 200→230. Deliberately *not*
anchored to `pending_qty`: core ERPNext has a real bug
(`set_pending_qty_in_row_without_reference` uses `or` where it should use
`and`, so it resets `pending_qty = planned_qty` on every save for *any*
Sales-Order-linked row) that would otherwise compound the buffer every time
you resave (500→575→661→...). Reading from the Sales Order Item's real qty
sidesteps that bug entirely. Stops recomputing once submitted, on purpose —
so it can't corrupt an in-progress qty later.

**Get Sub Assembly Items.** Explodes down to the 4 shared WIP items. Each
row's `fg_warehouse` auto-fills — always overriding, not just filling blanks
— straight from DESAR Settings: Warping Beam/Beam Roll → Warping WIP,
Grey Roll → Loom Floor, Finished Roll → Finishing WIP. (Core only supports
one uniform warehouse for the whole plan; doesn't fit 4 different WIP
locations.)

**Create Work Order.** Explodes into real Work Orders — 5 per Design Master
× 7 = 35 in this factory. Two things happen automatically here that took
real investigation to get working:

1. **Design context linking.** Every Work Order self-links to its Design
   Master (`custom_design_master`) purely from its own `bom_no` → that BOM's
   own `custom_design_master`. This has to run in `before_validate`, not
   `validate` — Production Plan's real bulk-creation path sets
   `wo.flags.ignore_validate = True` on every insert, which skips
   `validate()` entirely (confirmed by reading Frappe's
   `run_before_save_methods()` directly — `before_validate` always runs
   regardless of that flag, `validate` doesn't).
2. **Duplicate prevention.** Re-clicking "Create Work Order" before
   anything is submitted used to duplicate the whole set every time — core's
   own dedup guard (`ordered_qty`) only updates on Work Order *submit*, never
   on plain insert, and this factory's whole workflow leaves Work Orders in
   Draft for a while. A `CustomProductionPlan` controller override now skips
   re-creating a Work Order for any (item, bom_no) pair that already has a
   non-cancelled one on this plan.

**Note**: "Beam Roll" gets a Work Order created here too (it has a BOM) —
but it's deliberately deleted the moment the DESAR Production Order is
created (Phase 3). Beam Split is never a Work Order in this factory; see
Phase 4.

---

## Phase 3 — DESAR Production Order creation

One custom document per Design Master, created from the Production Plan.
If the Sales Order's 7 lines land in one combined Production Plan (common
with multiple designs), a `list_plan_designs` lookup finds every distinct
design on it, and one DESAR Production Order gets created per design — not
just one for the whole plan.

Fields set at creation: Sales Order / Production Plan / Design Master
(identity), **Total Qty (pcs)** — the *real* planned qty resolved from the
Sales-Order-linked `po_items` row (575 or 230, not an MRP roll estimate),
Pieces per Roll (copied from Design Master), Warping WO (the specific Work
Order this design's Warping stage will use — forced to `qty=1` here
regardless of total order size, since one beam is warped once, split later).

---

## Phase 4 — Warping and Beam Split (once per DESAR Production Order)

1. **Start Warping** — submits the Warping Work Order, drafts a Transfer
   Stock Entry (raw yarn issue from Yarn Store).
2. Submit that Transfer SE.
3. **Complete Warping** — Manufacture Stock Entry, produces one **Warping
   Beam batch** in Warping WIP.
4. **Split Beam** — enter rows summing to Total Qty in multiples of 115 (5
   rows of 115 for a 575-qty PO). Creates a **Repack Stock Entry**: consumes
   the one Warping Beam batch, produces N **Beam Roll batches** — one per
   physical roll, each a new distinct Batch number. Also splits the combined
   Grey/Finished/Packing Work Orders into one set per roll, and creates one
   **DESAR Roll Chain** row per roll (Phase 5's per-roll tracker).

   **Why Beam Split is a Stock Entry, not a Work Order**: roll count and
   split sizes aren't known until a supervisor physically looks at the beam
   and decides — a Work Order needs a fixed quantity up front, which doesn't
   fit "decided later." This is also why the auto-created "Beam Roll" Work
   Order from Phase 2 gets deleted at DESAR Production Order creation time.

---

## Phase 5 — Per-roll shop floor cycle (repeat for every physical roll)

23 rolls total in this factory's example (5 rolls × 3 sizes for Design 560,
2 rolls × 4 sizes for Design 561). Each roll's progress lives on its own
**DESAR Roll Chain** row, and its permanent history lives on its own
**Roll Ticket**.

1. **Start Grey Roll** → submits that roll's Grey Roll Work Order, drafts a
   Transfer SE (Beam Roll batch → Loom Floor).
2. Submit the Transfer SE.
3. **Complete Grey Roll** → Manufacture SE produces a new **Grey Roll
   batch**. Because Stage Configuration flags this stage `roll_ticket_trigger`,
   a **Roll Ticket** gets auto-created (if none exists yet for this roll) —
   the permanent traceability document. Because it's `qi_required`, a
   **Quality Inspection** (Grey Inspection template) auto-creates too.
4. Fill the QI's **Grade Readings** (child table, one row per grade — must
   sum to the Work Order's qty). Submit. This writes a row per grade into
   **DESAR Roll Ticket Stage Grade** on the Roll Ticket — permanent record
   of "this roll was 25 pcs Grade A, 4 Grade B, 1 Grade C at the Grey Roll
   stage."
5. **Start Finished Roll** → Transfer SE (this consumes Chemical Materials
   too — there's no separate "chemical finishing" action, it's just this
   stage's BOM). Submit it.
6. **Complete Finished Roll** → Manufacture SE, new **Finished Roll batch**,
   auto-QI (Finishing template). Fill grades, submit — another Stage Grade
   row recorded. (Grade counts can drift between stages — e.g. 25/4/1 at
   Grey becoming 24/5/1 at Finished — that's real, expected yield loss, not
   an error.)
7. **Start Packing**.
8. **Complete Packing** → drafts a Manufacture SE **deliberately**, not
   auto-submitted (a supervisor-review checkpoint before this roll's pieces
   formally become stock). Open it, submit it.
9. **Finalize Packing** → the **Final QI** (`wo_qty` sample size — every
   piece counted, since this is where sellable grade is finally decided).
   If the grade total differs from the Finishing QI's, the **Grade
   Adjustments** table must be filled first (e.g. "3 pcs upgraded B→A")
   or submission is blocked — this is what explains *why* the numbers moved,
   and gets recorded permanently.
10. Submitting the Final QI, since this stage is flagged `is_final_stage`,
    auto-triggers a **Repack Stock Entry**: consumes this roll's packed
    output from Finished Goods Grade A warehouse (where the Packing Work
    Order's own output actually lands), and produces the graded split —
    `Shemagh-X-Y-A` at 100% valuation, `-B` at 60%, `-C` at 20% (per this
    factory's Grade Configuration), into their respective target
    warehouses. Created in Draft — **submit it**.
11. **Complete Roll** — marks this roll `Completed` on its Roll Chain row.

Repeat all 11 steps for every remaining roll on this DESAR Production Order,
then move to the next DESAR Production Order and repeat Phase 4 + 5 from the
top.

---

## Phase 6 — What you can query when it's all done

**Traceability, per roll.** Open any Roll Ticket → **DESAR Roll Ticket
Stage Grade** shows the complete grade history at every stage. What it does
*not* give you for free: Frappe's Batch doctype has a `parent_batch` field
built for exactly this kind of lineage, but none of this factory's
Manufacture Stock Entries populate it — so the 3 distinct batch numbers a
single roll accumulates (Beam Roll batch → Grey Roll batch → Finished Roll
batch) have **no native Frappe link between them**. The only place that
connects them is the DESAR Roll Chain row (holds all 3 side by side) and the
Roll Ticket. Looking up a Batch directly, outside the Production Order,
shows no lineage at all.

**Costing.** Each roll's Repack Stock Entry is the actual valuation event —
`basic_rate` on the Grade A/B/C output rows equals the base rate (rolled up
from yarn + chemical + accessory costs through the whole BOM chain) times
that grade's `valuation_pct`. Query submitted Repack SEs for a design to see
real realized cost per grade.

**Stock.** Yarn Store depletes by each Warp Recipe's totals; Accessories
Store depletes 1:1 with pieces packed; Chemical Store depletes by the total
Chemical Materials kg allocated; `Finished Goods Grade A/B/C - ST` gain stock
per roll's submitted Repack SE.

---

## Known rough edges (real, found this session, worth knowing for a Q&A)

- **Batch has no native genealogy in use** (Phase 6) — traceability across
  stages exists only via the DESAR custom layer, not Frappe's own
  `parent_batch` field.
- **`ignore_doctypes_on_cancel_all`**: cancelling a Quality Inspection alone
  used to force "cancel the whole DESAR Production Order too" — a generic
  Frappe safety dialog for any Link between submittable doctypes (same thing
  ERPNext itself works around for Sales Invoice/Payment Entry). Fixed via a
  client-script flag; the backend already correctly reverted Roll Ticket/
  Roll Chain state for a standalone QI cancel.
- **Field/role-based visibility inside one DESAR Production Order** (e.g.
  "Warping Operator sees only Warping fields") is architecturally possible
  via Frappe's Permission Levels (`permlevel`) but not configured yet — and
  the API layer (`start_warping`/`start_packing`/etc.) currently gates every
  stage action on the same shared role list, not per-stage roles.
- **BOM chain submission is manual and bottom-up** (Phase 0.8) — 5 rounds
  of click+submit per Design Master, by explicit choice, to keep the
  "review before activating" step instead of auto-submitting the whole
  chain in one click.
