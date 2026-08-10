# DESAR Factory — The Real Manufacturing Flow (Business Process, Not System)

What DESAR actually wants demonstrated — the physical, business process of
turning yarn into a boxed, sold Shemagh. No doctype names, no field names,
no software terms. This is the "what and why" the system in
`DESAR_COMPLETE_MANUFACTURING_FLOW.md` was built to support.

---

## 1. The order

A customer places an order for Shemaghs — a specific **design** (pattern),
in specific **sizes**, at specific quantities.

Real example DESAR gave: Design 560 in sizes 55, 58, 60 cm (500 pieces of
each, 1,500 total), and Design 561 in sizes 55, 58, 60, 62 cm (200 pieces of
each, 800 total). 2,300 pieces sold, across 2 designs and 7 size variants.

## 2. Planning how much to actually produce

A factory never weaves *exactly* the sold quantity — weaving, dyeing,
cutting, and grading all lose some material to defects, trimming, and
below-standard output. DESAR's rule: **plan 15% more than what was sold**,
to make sure enough Grade A pieces come out the other end to fulfil the
order.

500 sold → 575 planned. 200 sold → 230 planned. Across the whole order,
2,300 sold becomes 2,645 planned.

This is a **planning** decision, made before any material is touched — it
determines how much yarn to draw, how many looms/beams to run, and shapes
everything downstream.

## 3. Raw materials

Two categories:

**Design-specific — yarn.** Each design has its own recipe of yarn types
(by count/thickness and color) and quantities, because different designs use
different amounts of colored thread for their pattern:

- Design 560: 300kg of 100/2 White, 50kg of 34/2 White, 200kg of 34/2 Red
- Design 561: 400kg of 100/2 White, 100kg of 34/2 Brown, 50kg of 20/2 Beige

**Common to every design — packing materials and chemicals**, needed
regardless of which design is being made: 3,000 boxes, 3,000 stamps, 3,000
stickers, and 100kg of finishing chemicals for the whole order.

Every material has a cost per unit (per kg of yarn, per box, per liter of
chemical) — this is what eventually makes up the *cost* of a finished piece,
not just its selling price.

## 4. Warping — preparing the yarn to be woven

Before a loom can weave, yarn has to be wound onto a **beam** — a large
cylindrical spool holding hundreds of parallel yarn threads ("ends") at the
exact width and pattern the design needs. This is **Warping**: the recipe
of yarn types and quantities (step 3) gets physically wound together into
one beam.

One beam is warped per design/size combination being produced — it's the
foundation that determines the fabric's width and base pattern before a
single thread is woven.

## 5. Beam splitting — one beam becomes several rolls

A single warped beam typically holds more yarn than one loom run can weave
in one go, or the factory wants to run multiple looms in parallel to hit the
planned quantity faster. So the beam gets **physically split into several
rolls** before weaving — the beam's total yardage is divided evenly (or
however the supervisor decides) across N physical rolls, each big enough to
weave through one loom independently.

This is a **supervisor decision made by looking at the physical beam**, not
something calculated in advance — the exact split (how many rolls, how big
each one) is decided at this point, on the shop floor.

Real example: 115 pieces worth of fabric per roll (chosen because it divides
both 575 and 230 evenly) — 5 rolls for each 575-piece size, 2 rolls for each
230-piece size.

## 6. Weaving — beam roll becomes grey fabric

Each split roll goes onto a loom and gets woven into **grey fabric** — plain,
undyed, unfinished cloth, straight off the loom. This is the first point a
**quality check** happens: the grey fabric roll is inspected and graded.

## 7. Quality grading — A / B / C, at every stage from here on

At each remaining stage, every roll is inspected and classified:

- **Grade A** — meets full quality standard, sells at full price.
- **Grade B** — usable but with visible minor defects (weave irregularities,
  slight color unevenness) — sold at a discount, DESAR's rule: **60% of
  Grade A's value**.
- **Grade C** — significant defects — sold at a further discount, **20% of
  Grade A's value** (or in some setups, disposed as scrap entirely,
  depending on the defect).

Grading isn't a one-time judgment — a roll graded mostly-A at the grey stage
can lose pieces to B or C at the finishing stage, and again at packing, as
more of the fabric is examined more closely at each step. The factory needs
to know, for every batch, exactly how many pieces ended up in each grade at
each stage — both for costing (a B piece is worth less) and for quality
tracing (which stage introduced the defect).

## 8. Chemical finishing — grey roll becomes finished roll

The grey fabric roll goes through **chemical finishing** — washing, chemical
treatment, and pattern/color finishing (e.g. flower/print application) that
turns raw grey cloth into finished, sellable-quality fabric. This consumes
the chemical materials from step 3. Another quality grading happens on the
output.

## 9. Cutting and packing — finished roll becomes individual pieces

The finished fabric roll gets cut into individual Shemagh pieces (per the
specific size), ironed/steamed, stamped with the brand, and packed — boxed,
labeled, and stickered (the common materials from step 3). This is the
**final** quality check: every single piece gets classified A/B/C at this
point, since this is what actually determines what ships as full-price
stock vs discounted stock.

If grading at packing differs from grading at the finishing stage (e.g. a
piece that looked fine at finishing shows a defect once cut and pressed),
the factory needs that difference explained and recorded — not just
silently overwritten — since it affects both cost accounting and any
quality investigation later.

## 10. Grade movement and final inventory

Once packing is graded, the finished pieces move into inventory **by
grade** — Grade A stock, Grade B stock, Grade C stock, each valued
differently (100% / 60% / 20% of base cost, per DESAR's rule) and, in a real
factory, often physically stored/sold through different channels. This is
the point real, sellable inventory exists — everything before this was
work-in-progress.

## 11. Costing

The cost of one finished piece is the sum of everything that went into it:
its share of the yarn (by weight), its share of the finishing chemicals, its
box/stamp/sticker, all rolled up through warping → weaving → finishing →
packing. Grade A carries that full cost at full value; Grade B and C carry
the same production cost but are *valued* (for accounting/resale) at their
discounted percentage — the factory absorbs that difference as a real yield
loss, which is exactly why the 15% production buffer (step 2) exists: to
plan for it in advance rather than come up short on sellable Grade A stock.

## 12. Traceability

For any finished piece — or any batch of finished pieces — DESAR wants to be
able to trace backward: which roll it came from, which beam that roll was
split from, which yarn lot that beam was warped from, and every grade
reading recorded at every stage along the way. This matters for two real
business reasons: **quality investigation** (if a customer reports a defect,
find every other piece that came from the same roll/beam) and **costing
audit** (confirm the value assigned to a piece is actually traceable to real
material costs, not an estimate).

---

## Summary — the physical chain, start to finish

```
Yarn (by design's recipe)
  → Warping (beam)
  → Beam Split (N rolls, decided on the shop floor)
  → Weaving (grey fabric roll) — [grade check]
  → Chemical Finishing (finished roll) — [grade check]
  → Cutting & Packing (individual pieces, boxed) — [final grade check]
  → Graded Inventory (A / B / C, valued differently)
```

Every arrow has a quantity, a cost, and — from the grey stage onward — a
grade attached to it. That's the complete real-world process; everything in
`DESAR_COMPLETE_MANUFACTURING_FLOW.md` is how it gets recorded and enforced
in the system.
