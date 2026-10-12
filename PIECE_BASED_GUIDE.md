# Piece Based Manufacturing Guide

One Work Order per finished product (design and size). Beams and rolls are records, never stock items. Two Stock Entries per Work Order: materials out at the start, finished goods in at the end. The old stage-per-Work-Order flow still works for Design Masters whose `Process Version` is `Legacy`.

## One-time setup (a second company changes only this data)
1. DESAR Settings: warehouses (yarn, chemical, accessories, finished goods, scrap, Piece Based WIP) and Grade Configuration. Set each grade's valuation percent. Mark the scrap grade as scrap (it is stored at zero value).
2. Operations and Workstations in ERPNext. Set labour, electricity and other rates on each Workstation so cost reports show labour cost.
3. Production Process: ordered steps (operation, workstation, minutes). Tick "Use Beam's Loom" on the weaving step. Choose what each step consumes (Warp Yarn, Weft Yarn, Chemicals, Packing).
4. Inspection Stages and Inspection Reasons are seeded on migrate (Gray, Finishing, Final; reasons for grade moves, loss and count gain). Edit them as needed.
5. Per design: Warp Recipe (Rate Kg/Piece per yarn), Weft Recipe (Rate Kg/Piece), Design Master with Size Configuration rows (finished Grade A item, warp and weft recipe, roll length, picks per cm, flower yarn), Chemicals table, box, label and sticker items, Production Process, and `Process Version = Piece Based`.
6. Users: give factory workers the role `DESAR Factory Worker` (no Desk access, they land on `/shop-floor`). Supervisors keep `DESAR Supervisor`.
7. Build the tablet app once: `cd frontend && npm install && npx vite build`.

## Day to day
1. Technical user: Sales Order, Production Plan, then create the Work Order with `piece_order_service.create_work_order(design_master, size, qty, sales_order)`. This makes the per-piece BOM, the grade items and the Work Order.
2. Create beams for the Work Order (`beam_service.create_beams`), split a beam if needed (`split_beam`), create rolls on each beam (`create_rolls`), and create beam Job Cards (`job_card_service.create_beam_job_cards`). Issue materials once (`piece_order_service.issue_materials`).
3. Supervisor, on the tablet app Assign screen: assign Job Cards and inspections to workers.
4. Workers: start and finish jobs (enter materials actually used), count inspections. Gray takes counts; Finishing takes grade moves and process loss; Final takes the real counted pieces and explains differences.
5. Close the Work Order (`closing_service.close_order`) when every Job Card is finished and every roll has a Final inspection.
6. Reports: Piece Order Yield, Grade Movements, Process Loss by Reason, Piece WIP, Sales Order Production, Piece Order Cost. Print formats: Loom Ticket (Production Beam), Work Order Sheet (Work Order).

## Known limits
- ERPNext checks Job Card order by cumulative completed quantity across beams.
- Work Order submit schedules whole-order Job Cards that are replaced by beam Job Cards; capacity planning is switched off only around that submit.
- Material not used stays in the WIP warehouse after close.
- Grade B and C leave as scrap-type rows of the Manufacture entry because ERPNext allows one finished item per entry. Their values are set explicitly.
- `inspection_candidates` queries per roll; rewrite it as one query past about 5000 open rolls.
