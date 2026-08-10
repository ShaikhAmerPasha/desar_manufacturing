# DESAR Manufacturing - Complete User Manual

Welcome to the DESAR Manufacturing system. This custom ERPNext module is designed to streamline the production of Shemaghs, from initial engineering design all the way to final packing and scrap management.

This guide is written for a new user to understand and execute the entire manufacturing flow from start to finish.

---

## Phase 1: One-Time System Setup
*This phase is typically done once by the System Administrator or Factory Manager.*

### 1. DESAR Settings
Navigate to **DESAR Settings** via the search bar. This is the control center for all factory automations.

* **Warehouse Configuration:** Map your physical factory floor to the system. You must link your Yarn Store, Chemical Store, Warping WIP, Grey Roll Store, and Finished Goods warehouses here. The system uses these to route inventory automatically.
* **Grade Configuration:** Define your quality grades (e.g., Grade A = 100% valuation, Grade B = 60% valuation, Grade C = 0% Scrap). Check `Is Scrap` for the scrap row.
* **New Design Defaults:** Enter the standard items used in almost every design (e.g., standard boxes, stickers, labels). This saves the planner from typing them manually every time.
* **Default Stage Template:** Build the 5-stage factory path. Add 5 rows:
  1. Warping (Output: Warping Beam, Skip Transfer: Yes)
  2. Beam Split (Output: Beam Roll, Skip Transfer: Yes, Can Split: Yes)
  3. Weaving (Output: Grey Roll, Skip Transfer: Yes, Creates Roll Ticket: Yes, QI Required: Yes)
  4. Finishing (Output: Finished Roll, QI Required: Yes)
  5. Packing (Output Item: *Leave Blank*, QI Required: Yes, Final Stage: Yes)

---

## Phase 2: Engineering & Planning
*This phase is done by the Production Planner when a new design is required.*

### 1. The Design Master
The Design Master is the single source of truth for a Shemagh design. Navigate to **Design Master** and click **Add**.

**Tab 1: Design Info**
* **Design No:** e.g., `801`
* **Article Name:** e.g., `Oasis`
* **Default Size:** e.g., `58`
* *Note:* The system will automatically construct the **Finished Item** code (e.g., `Shemagh-OAS-58-A`) when you save.

**Tab 2: Yarn Specification**
* Enter the **Planned Qty (Pieces)** (e.g., `500`).
* Add rows to the **Warp Yarn** and **Weft Yarn** tables. Simply select the Yarn Item and type the **Total Qty (Kg)** needed for the whole batch. 
* *Automation:* When you save, the system automatically calculates the `Rate (Kg/Piece)` so the Bill of Materials is perfectly accurate per roll.
* You can attach an image of the physical thread pattern in the `Repeat Pattern` field for workers to look at later.

**Tab 3 & 4 (Materials & Stages)**
* You don't need to do anything here! The system automatically copies all the defaults you set up in DESAR Settings directly into these tabs.

### 2. Generating Bills of Materials (BOMs)
* Once the Design Master is saved and looks correct, click the **Create All BOMs** button at the top right.
* The system will instantly generate 5 interconnected BOMs (one for each production stage) and link them to the Design Master.

---

## Phase 3: Triggering Production
*This phase is done by the Sales/Planning team.*

1. **Sales Order:** Create a standard Sales Order for `Shemagh-OAS-58-A` for `200` pieces. Submit it.
2. **Production Plan:** 
   * Create a Production Plan from the Sales Order.
   * Click **Get Items for Work Order**.
   * Click **Create Work Orders**.
   * Submit the Production Plan. The system automatically creates a parent **DESAR Production Order** that groups the 5 stages together for the factory floor.

---

## Phase 4: Factory Floor Execution
*This phase is done by the Factory Workers using tablets on the floor.*

### 1. Warping (Stage 1)
* Open the **DESAR Production Order**.
* Under Stage 1 (Warping), click **Start**, wait for processing, then click **Complete**. 
* The system instantly deducts the yarn from the warehouse and creates a virtual "Warping Beam".

### 2. Beam Splitting (Stage 2)
* Because one giant beam cannot fit on one weaving loom, it must be split.
* Click **Split Beam** under Stage 2.
* A dialog appears. If your order is for 200 pieces, you might split it into two physical rolls (e.g., Row 1: 100 pieces, Row 2: 100 pieces).
* Submit the split. The system automatically clones the downstream operations!

### 3. Weaving & Roll Tickets (Stage 3)
* After the split, Stage 3 (Weaving) will now show **two** separate rows.
* When a worker finishes weaving a roll, a custom **Roll Ticket** is generated. The Roll Ticket acts as a digital barcode/passport that travels with that specific physical roll through the rest of the factory.

---

## Phase 5: Quality Control & Auto-Repack
*This phase is done by Quality Inspectors.*

### 1. Intermediate QC
* On the Roll Ticket, click the **QC** button after Weaving and Finishing. 
* Fill out the standard ERPNext Quality Inspection to ensure the fabric is good before moving to the next machine.

### 2. Final Packing & Auto-Repack (The Magic)
* At the very end of the line (Stage 5), the worker completes the final Quality Inspection.
* They enter the exact yield. Example for a 100-piece roll:
  * **Grade A:** 90 pieces
  * **Grade B:** 8 pieces
  * **Scrap (Grade C):** 2 pieces
* **Submit the Inspection.**

*Automation:* The moment the inspection is submitted, the system triggers the **Repack Service**. It creates a Stock Entry that physically sorts the inventory:
* 90 pieces go to the Grade A Warehouse.
* 8 pieces go to the Grade B Warehouse (valued at a discount).
* 2 pieces are financially disposed of (Scrap), absorbing their cost into the good items, while their quantities are permanently saved on the Roll Ticket for management yield reporting.

**End of Flow.** The inventory is now ready to be shipped to the customer!
