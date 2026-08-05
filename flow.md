# Design 560/561 Demo — Manual Implementation Flow

Step-by-step guide to build and run this scenario **by hand in the UI**, to
verify the BOM/stage automation actually works end to end. Site: `excel`.
Full rationale: `/home/ameer/.claude/plans/1-sales-order-details-imperative-mango.md`.

## What's already done for you (code, not data)

- Design Master has 2 new fields: **Sticker Item** (`sticker_item`) and
  **Chemical Materials (Kg)** (`chemical_materials_qty_kg`), next to the existing
  Branded Box Item / Label Item / Finish Chem Qty fields.
- `bom_service.py`'s automation now folds Sticker Item into the Packing BOM
  (alongside Box/Label) and Chemical Materials into the Finished Roll BOM
  (alongside WashAgent/FinishChem/FlowerChem).
- **3 pre-existing app bugs fixed globally** (Operation master records), or the
  automation will throw when you click "Create All BOMs" — see the box below.
- **Warp Recipe** now supports rate-based Qty (Kg) (Planned Qty + Rate (Kg/Piece)
  per row) instead of hand-calculated quantities — see A2.
- **Production Plan** now has a **Production Buffer %** field that auto-applies
  to `planned_qty` on save — see B2. No more manually retyping 7 numbers.
- **`production_plan_service.py`** now correctly supports a Production Plan
  containing Work Orders for multiple designs (`design_master` param on
  `create_desar_po`/`preview_plan`, new `list_plan_designs` lookup) — see B3.
- No demo data exists yet. You're building it from scratch.

> **Known gotcha — read before you start:** `BOMService.create_all_boms()`
> needs, for every stage name in your Stage Configuration, either (a) an
> `Operation` master record of that exact name with a `Workstation` set, or
> (b) a keyword match in `bom_service.py`'s `_DEFAULT_WORKSTATION_BY_KEYWORD`
> (warp/weav/loom/dye/finish/wash/pack/cut). **The per-stage "Operations" child
> grid nested inside a Stage Configuration row does NOT reliably save/reload**
> — a Frappe framework limitation with two-levels-deep child tables, confirmed
> by direct testing this session. Don't rely on it. If you hit
> `"No workstation configured for stage X"`, go to **Manufacturing → Operation**,
> open the Operation named exactly `X`, and set its Workstation directly.
> Already fixed for you: `Warping`, `Beam Split` → Sorting Table, `Grey Roll` →
> Loom 62, `Finished Roll` → Finishing Machine, `Packing` — all resolve now.

## Part A — Master data (do this first, in order)

### A1. Items
Create these as new Items (Stock UOM as noted, `Is Stock Item` checked):

| Item Code | Group | UOM | Rate |
|---|---|---|---|
| Yarn-34-2-Red | Yarn | Kg | 14 |
| Yarn-34-2-Brown | Yarn | Kg | 14 |
| Yarn-20-2-Beige | Yarn | Kg | 12 |
| Boxes | Packing Material | Nos | 2 |
| Stamps | Accessories | Nos | 0.5 |
| Stickers | Accessories | Nos | 0.2 |
| Chemical Materials | Chemicals | Kg | 5 |

`Yarn-100-2-White` and `Yarn-34-2-White` already exist in the system — reuse them, don't recreate.

Set an **Item Price** (Standard Buying, matching the rate above) for each new item, and receive opening stock via **Stock Entry (Material Receipt)** into the matching DESAR Settings warehouse (check current values in DESAR Settings — as of now: `Yarn Store - ST`, `Accessories Store - ST`, `Chemical Store - ST`):
- Yarn-34-2-Red: 200 kg, Yarn-34-2-Brown: 100 kg, Yarn-20-2-Beige: 50 kg → Yarn Store
- Boxes/Stamps/Stickers: 3000 each → Accessories Store
- Chemical Materials: 100 kg → Chemical Store
- Top up `Yarn-100-2-White` by however much is short of 700 kg total, and `Yarn-34-2-White` by however much is short of 50 kg total (check current Bin qty first — likely already enough).

**Finished goods — use real Item Variants, not plain Items.** The app already
has a working Item Variant setup for Shemagh, undocumented until now: Item
`Shemagh` has `has_variants=1` with 3 attributes in this order — **Article**,
**Shemagh Size**, **Grade**. `Shemagh-VIC-58-A`, `Shemagh-VIC-60-B`, etc. are
real variants of it (not hand-typed Items), and their BOMs already target the
variant correctly. `Shemagh Size` already has 55/58/60/62 — everything 560/561
need. `Grade` already has A/B/C. Only `Article` needs 2 new values:

| Attribute | New Value | Abbr |
|---|---|---|
| Article | Zephyr | ZEP |
| Article | Atlas | ATL |

Then open Item **`Shemagh`** and click **Create Variants**:
- Article = Zephyr, Shemagh Size = 55/58/60, Grade = A/B/C → 9 variants (Design 560)
- Article = Atlas, Shemagh Size = 55/58/60/62, Grade = A/B/C → 12 variants (Design 561)

21 variants total, named exactly `Shemagh-ZEP-55-A` etc. by ERPNext's own
naming rule (concatenates attribute abbreviations in order — reproduces the
same pattern as `Shemagh-VIC-60-A`). Spot-check one: it should show
`variant_of = Shemagh` and the 3 attribute values on its own Attributes tab.
No code anywhere cares whether an item code came from a real variant or a
hand-typed Item — `bom_service.py`, grade-derivation, and Repack all just read
the item code string — so everything from here on works identically either way.

### A2. Warp Recipes (one per Design+Size — 7 total)
**Use the rate-based fields instead of hand-calculating kg.** Warp Recipe now has a
**Planned Qty (Pieces)** field, and each Yarn Items row has a **Rate (Kg/Piece)**
field — set both and **Qty (Kg)** auto-computes on save (`row.qty_kg = rate ×
planned_qty`), with **Total Yarn (Kg)** auto-summing too. Leave Rate blank on a
row to type Qty (Kg) manually instead — both modes coexist per row.

Set Planned Qty = 575 for every 560 recipe, 230 for every 561 recipe. Rate
(Kg/Piece) per yarn item — same rate across all sizes of a design, since it's
kg needed per piece, not per size:

| Design | Yarn 100/2 White | Yarn 34/2 White | Yarn 34/2 Red | Yarn 34/2 Brown | Yarn 20/2 Beige |
|---|---|---|---|---|---|
| 560 (rate, kg/pc) | 0.173913 | 0.028986 | 0.115942 | – | – |
| 561 (rate, kg/pc) | 0.173913 | – | – | 0.108696 | 0.054348 |

(= each design's total kg ÷ its total planned qty: 560 → 1725 pcs total, 561 → 920 pcs total. At Planned Qty 575, 560's rates reproduce 100/16.67/66.67 kg exactly, matching the original hand-calculated numbers — this is the same math, just computed instead of typed, so no rounding drift.)

### A3. Design Masters (one per Design+Size — 7 total)
For each: Design No., Article Name (e.g. "Zephyr" for 560, "Atlas" for 561), Sizes (informational, e.g. "55,58,60"), Default Size = that specific size, Warp Recipe (from A2), Pieces per Roll = **115** (chosen so 575÷115=5 and 230÷115=2 — no partial rolls), Branded Box Item = Boxes, Label/Stamp Item = Stamps, Sticker Item = Stickers, Chemical Materials (Kg) = 21.74 (Design 560 sizes) or 8.70 (Design 561 sizes) — proportional to each size's share of the whole order's 2645 planned pieces.

**Stage Configuration** (5 rows, identical shape for all 7 — this is the part that drives everything downstream):

| Seq | Stage Name | Output Item | Output Qty | QI Required | QI Template | Sample Size | Roll Ticket Trigger | Final Stage |
|---|---|---|---|---|---|---|---|---|
| 1 | Warping | Warping Beam | 1 | – | – | – | – | – |
| 2 | Beam Split | Beam Roll | 1 | – | – | – | ✓ | – |
| 3 | Grey Roll | Grey Roll | 1 | ✓ | Grey Inspection - Shemagh | 1 | ✓ | – |
| 4 | Finished Roll | Finished Roll | 1 | ✓ | Finishing Inspection - Shemagh | 1 | – | – |
| 5 | Packing | *(this size's Shemagh-X-Y-A item)* | 115 | ✓ | Final Packing Inspection - Shemagh | wo_qty | – | ✓ |

Save the Design Master. Ignore the Operations sub-grid entirely (see the gotcha box above) — leave it empty on every row.

### A4. Generate BOMs
On each Design Master, click **Create All BOMs**. Should produce 5 draft BOMs (Warping Beam, Beam Roll, Grey Roll, Finished Roll, Shemagh-X-Y-A). If you get `"No workstation configured for stage X"`, that stage's Operation master record needs a Workstation — see the gotcha box.

**Verify before submitting**: open the Finished Roll BOM and confirm it lists `Grey Roll` + `Chemical Materials` as inputs; open the Shemagh BOM and confirm it lists `Finished Roll` + `Boxes` + `Stamps` + `Stickers`. If Finished Roll's BOM failed silently and Packing's BOM ends up listing `Grey Roll` directly instead of `Finished Roll`, that's the same failure mode found and fixed this session — the Finished Roll stage's Operation/workstation resolution failed, and the code fell through and used the last successful stage's output. Fix the underlying error, clear that stage's `bom_no`, and re-click Create All BOMs.

Submit all 35 BOMs once verified.

## Part B — Transactions

### B1. Sales Order
One order, 7 lines at real sales qty, with a rate on each line (none was given in the source data):
`Shemagh-ZEP-55-A`×500, `-58-`×500, `-60-`×500, `Shemagh-ATL-55-A`×200, `-58-`×200, `-60-`×200, `-62-`×200. Submit.

### B2. Production Plan — 15% allowance
Run Get Items/MRP — this can land as 1 combined Production Plan (all 7 lines) or 7 separate ones; either is fine now (see B3).

Set **Production Buffer %** = 15 on the Production Plan and save (Draft only) — `planned_qty` on every Sales-Order-linked line auto-recomputes from `pending_qty × 1.15` (575/575/575/230/230/230/230), no manual retyping. Safe to save repeatedly while still Draft (recomputes from the stable `pending_qty` each time, doesn't compound) — but the buffer stops re-applying once submitted, so get it right before submitting. Submit.

### B3. DESAR Production Orders
If Get Items produced 7 separate Production Plans, create one DESAR PO per plan as before (`create_desar_po(production_plan)`)

If they landed in **1 combined plan**: call `list_plan_designs(production_plan)` first — returns the distinct Design Masters found on that plan's Work Orders (should be all 7). Then call `create_desar_po(production_plan, design_master=<name>)` once per Design Master returned, instead of once for the whole plan — each call now scopes itself to only that design's Work Orders (Warping WO config, total_qty resolution, and design tagging no longer leak across designs sharing one plan).

**Check `total_qty` on each PO immediately** — must read 575/230 exactly, not `pieces_per_roll` (115) — that would mean the B2 buffer didn't take.

### B4. Per-roll shop floor cycle (23 rolls: 15 for Design 560, 8 for Design 561)
Per `MANUAL_TEST_GUIDE.md`, via the Production Controller/Workspace UI:
1. Start Warping → submit Transfer SE → Complete Warping.
2. Split Beam — rows in multiples of 115 (5 rolls for a 575-qty PO, 2 rolls for a 230-qty PO).
3. Per roll: Start Grey Roll → submit Transfer SE → Complete Grey Roll (auto-QI, fill Grade A/B/C, submit) → Start Finished Roll (consumes Chemical Materials here — this *is* the chemical finishing step) → submit Transfer SE → Complete Finished Roll (auto-QI) → Start Packing → Complete Packing (drafts a Manufacture SE — submit it) → Finalize Packing (Final QI, reconcile grade adjustments if needed, submit → auto-creates a Repack SE valuing A/B/C at 100%/60%/20% — submit that too) → Complete Roll.

## Part C — Verification

1. Stock Ledger: Yarn Store depletes by recipe totals; Accessories Store depletes Boxes/Stamps/Stickers 1:1 with packed pieces; Chemical Store depletes 100 kg total; `Finished Goods Grade A/B/C - ST` gain stock per roll's Repack SE.
2. Sample Roll Ticket: stage-grade rows present for Grey/Finish/Packing, status Completed.
3. Sample Repack SE: Grade A/B/C `basic_rate` = 100%/60%/20% of the Finished-Roll-derived valuation rate.
4. Regression: `bench --site excel run-tests --app desar_manufacturing` and `bench --site excel execute desar_manufacturing.tests.test_e2e_cycle.run_full_cycle` (confirms nothing broke for existing Design Masters 563/564).
