# Design Principles and Flow (configurable, reusable)

Status: DRAFT for review. Extends `specs/audit-and-target-design.md` and `specs/implementation-plan.md`. B grade valuation fixed at 60 percent (decided).

## 1. Principles

1. Configuration over code. Anything a second textile company would change lives in a master or a setting, never in Python or JS.
2. No factory names in code: no item codes (`Beam Roll`, `WashAgent`, `Shemagh-VIC-60-A`), no warehouse names, no company suffix (`-ST`), no keyword matching on stage names, no fixed grade letters.
3. Reuse ERPNext first: Item and Item Variant, BOM with Routing, Work Order, Job Card, Workstation, Operation, Warehouse, Stock Entry, assignment (ToDo), permissions, translations. Custom only for beams, rolls, piece-level grades.
4. One source of truth per fact. State is derived from documents (Job Cards, Roll Inspections), not stored as parallel status strings.
5. Thin layers: doctype controller (validation) -> service (business rule) -> repository (queries). API and UI call services only.
6. Scale by constant document count per Work Order, incremental counters, indexed SQL reports, background jobs for bulk creation.
7. Small slices: tracer bullet per phase, tests on real documents, files 100 to 300 lines.

## 2. What is configurable

| Concept | Where it is configured | Today |
|---------|------------------------|-------|
| Steps of the process (names, order, type Job Card / Inspection, where rolls are created, which step is final) | `Production Process` master (new, ordered child table) linked from Design Master or Settings | Hard-coded in `roll_service`, `warping_service`, `bom_service` |
| Operations and workstations | ERPNext `Operation`, `Workstation`, Routing generated from the Production Process | Keyword to workstation map in `bom_service` |
| Grades: code, label, valuation percent, scrap flag, target warehouse, item suffix | `DESAR Grade Configuration` (keep) | Partly config, partly hard-coded A/B/C |
| Inspection stages | Rows in the Production Process marked Inspection, with grade set and reason lists | Stage name strings |
| Reasons for grade movement and loss | Two masters | Not present |
| Material to operation | BOM Item `operation`, generated from recipes and Design Master rates | Fixed code per stage |
| Warehouses, default company, scrap warehouse | Settings | Settings, but with hard-coded fallbacks |
| Unit names (beam, roll, piece) | Translation and field labels | Fixed |
| Roll and piece conversion | Design Size row (pieces per roll, roll length) | Design Master field |
| Language | Standard translations (en, ar) | Mixed |

A second company changes: the Production Process steps, grades, reasons, recipes and items. It does not change code.

## 3. Master data review: Design Master, Warp Recipe, Weft Recipe

Reviewed against the paper Work Order and Loom Ticket and the `tzamun` data. (You wrote "var over SCP"; I read it as the warp and weft recipes. Tell me if you meant something else.)

### 3.1 Evidence from `tzamun`
- 8 Design Masters. Design 561 has two masters. Master for 563 has default size 63, the paper says 60. Master for 562 lists sizes "55,58,62" in a text field, other masters have no sizes. One master per design+size is the intent in `flow.md`, but the data mixes both styles.
- Warp Recipes: 7 records, 5 empty. `total_ends` is 0 on all. WR-2026-0002 is shared by 3 designs; it has the same yarn row twice. A recipe says planned qty 500 and a recipe for design 701 size 50 is used by design 560.
- Weft Recipes: 0 records. No design links a weft recipe. Weft yarn is never consumed.
- Warp Recipe Items carry yarn, count, colour, ends, kg rate. There is no sequence, repeat or section.

### 3.2 What the paper documents need and the system lacks
Work Order paper: issue date, PO number, design number, size, working date, beam table (number of beams, beam length, loom number), warp repeat table (yarn count, colour, ends per block, repeat blocks, totals, grand total 3482), missing ends (16), selvedge, flower yarn and its ends, sizes the arrangement applies to (55, 58, 60, 62).
Loom Ticket: machine, PO, design, size, installation date, number of rolls, flower yarn, weft count and colour list, roll length, picks per cm (planned, adjusted, counted), signatures, remarks.
Weft page: ordered weft arrangement with count, colour, pick count and repeat blocks; weft winding note; flower and selvedge enlargement note.

### 3.3 Proposed structure

```
Design (Design Master, one per design)
  Design Size (child): size, finished item (Item Variant), warp recipe, weft recipe,
                       pieces per roll, roll length, picks per cm, box/label/sticker items,
                       chemical rates per piece
Warp Recipe   header: applicable sizes, selvedge ends, missing ends, flower yarn, total ends (computed)
  Section (child, ordered): sequence, kind (body / selvedge / flower / border), yarn item,
                            count, colour, ends per block, block repeats, total ends (computed)
Weft Recipe   header: weft winding note
  Pick block (child, ordered): sequence, yarn item, count, colour, picks per block, repeats, total picks (computed)
```

- Totals (3482 ends) are computed, never typed.
- One recipe can serve several sizes via applicable sizes, as the paper shows.
- Yarn kg is computed: ends x beam length x yarn weight per metre. The weight per metre comes from a field on the yarn Item (set once per yarn count). Needs a factory check of the formula before Phase 3; until then the manual kg per piece rate stays as an override.
- Weft kg per piece: picks per cm x width x weight per metre, same approach. Also confirmed with the factory first.
- Design Master drops: `stage_configuration`, `bom_level_1..4`, chemical fields named for specific chemicals. Chemicals become rows (item, rate per piece, operation) so any chemical works.
- Duplicate yarn rows, empty recipes and missing weft links get validation errors on the new flow.

### 3.4 Production Plan
Keep: the production buffer percent, the guard against duplicate Work Orders for the same item and BOM (`overrides/production_plan.py`), the one-Work-Order-per-design behaviour.
Remove: sub-assembly handling (`events/production_plan.py` rounding, hard-coded sub-assembly warehouses). Sub-assembly items stop existing.
Add: "Production Plan and Costing" from the process chart: estimated cost per Work Order from BOM materials plus Routing operation time times workstation rate, shown on the plan and on the Work Order.

## 4. Flow

```
Sales Order
 -> Production Plan (buffer %, estimated cost)
     -> Work Order per design+size   (BOM per piece + Routing from Production Process)
          [Technical user: Create Beams, Issue Materials]
          Stock Entry 1: Material Transfer, all materials once
          Beam(s) -> split beams -> loom
          Job Cards per beam: steps of type Operation (Warping, Beam Split, Weaving, Chemical Finishing)
          Rolls created at the step flagged "creates rolls"
          Roll Inspection stages in step order (Gray, Finishing, Final):
              opening fetched from previous stage, movements (any grade to any, reason),
              process loss (reason), Final enters real counts
          Job Cards per beam for packing steps (Classification .. Boxing), after Finishing inspection
          [Supervisor: Close Order]
          Stock Entry 2: Manufacture, A and B valued (B 60 percent), C to scrap at zero, loss posts nothing
 -> DESAR Production Order (kept): read-only summary of all of the above for one Sales Order
```

Order of steps comes from the Production Process, so another company can add Dyeing or drop Packing sub-steps without code.

## 5. Hard-coded items to remove (from the audit)

`Warping Beam`, `Beam Roll`, `Grey Roll`, `Finished Roll`, `WashAgent`, `FinishChem`, `FlowerChem`, `Chemical Materials`, `BrandedBox-{size}`, `LabelStamp`, `Sticker`, `Shemagh-{ART}-{size}-A`, `Warping Machine`, `Loom 62`, `Sorting Table` and all workstation keywords, the legacy BOM operations list, `-ST` company suffix, grade letters A/B/C in code paths, stage-name LIKE matching in QI hooks, hard-coded sub-assembly warehouses.

## 6. Naming and reuse for another company

- Keep neutral doctype names (Production Beam, Roll Ticket, Roll Inspection, Production Process).
- Prefix only the app module, not each document, for new doctypes.
- Packaging: patches and fixtures create defaults (grades A/B/C, reasons, an example Production Process) so a new site works after install; the company edits them.
- Installation checklist doc replaces `flow.md` and `complete_flow.md`.

## 7. Open points

- Yarn kg formula (ends x length x weight per metre) and weft formula: confirm with the factory.
- Does one warp recipe serve several sizes (paper suggests yes), or does the arrangement differ per size?
- "SCP" in your message: confirm meaning.
