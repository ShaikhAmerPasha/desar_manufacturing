# Desar Manufacturing System: Process & Document Guide

**Target Audience:** Management & Key Stakeholders (e.g., Mr. Nooh)
**Purpose:** This guide explains the complete end-to-end production workflow in the Desar ERP system. It maps the real-world manufacturing steps—from sales to final packing—directly to the system documents used to track them, ensuring clear understanding of how the system manages the production lifecycle.

---

## 1. Planning and Order Initiation

The manufacturing journey begins with capturing customer demand and planning the production floor operations.

### 1.1 Sales Order & Production Plan
* **Process:** A customer order is received, and production planning begins to fulfill the required quantity.
* **System Documents:**
  * **Sales Order (SO):** Captures the customer's requested items and quantities.
  * **Production Plan:** Aggregates Sales Orders to determine overall manufacturing requirements.
  * **Work Orders:** Standard system documents generated to queue production.

### 1.2 The Desar Production Order
* **Process:** Once standard planning is done, a centralized manufacturing order is created to act as the "control center" for the entire textile process.
* **System Document: `Desar Production Order`**
  * **What it does:** Created directly from the Production Plan via a custom button, this is the master document. It manages the complete lifecycle (Weaving → Grey Processing → Chemical Finishing → Packing) from a single screen. You do not need to hunt for different documents; everything is accessible here.

---

## 2. Pre-Weaving and Weaving

Once the production order is active, raw materials are converted into the first physical rolls of fabric.

### 2.1 Start Weaving & Material Consumption
* **Process:** Raw yarn (warp and weft) is issued to the shop floor to begin weaving.
* **System Document: `Stock Entry (Material Manufacture)`**
  * **What it does:** When you click "Start Weaving", the system auto-generates a Stock Entry in **Draft** status. Submitting this document formally deducts the raw yarn from inventory and records the start of production.

### 2.2 Beam Splitting & Roll Creation
* **Process:** Fabric produced on the loom (often on a large beam) needs to be split into manageable rolls that match the Sales Order requirements.
* **System Document: `Desar Beam Split Row` / Split Dialog**
  * **What it does:** A specialized tool allows you to define how a large batch is split into multiple rolls. 
  * **Validation:** The system automatically ensures that the total quantity of the split rolls exactly equals the targeted Sales Order quantity (e.g., splitting a 161m order into 80m and 81m rolls).

---

## 3. Independent Roll Tracking

From this point forward, every single roll of fabric has its own identity and can be processed independently of the others.

### 3.1 The Roll Ticket
* **Process:** Every time a new roll is cut or created, it needs a physical passport.
* **System Document: `Roll Ticket`**
  * **What it does:** Automatically generated for every roll. It acts as the central tracking record, maintaining the complete history, exact length, current production stage, and quality inspections for that specific piece of fabric. 

### 3.2 Traceability
* **Process:** Maintaining a strict record of where a roll came from.
* **System Document: `Desar Roll Chain` & `Batch Number`**
  * **What it does:** At every production stage, the system automatically generates unique **Batch Numbers**. The Roll Chain ensures that if a roll is split again later, you can always trace it back to the original loom and yarn recipe.

---

## 4. Processing & Quality Inspection (QI)

Rolls move through various finishing stages. At each stage, labor is tracked, and quality is verified.

### 4.1 Stage Operations (Grey Roll & Chemical Finishing)
* **Process:** The fabric undergoes washing, dyeing, or chemical treatments. Workers log their time.
* **System Documents:** 
  * **`Desar Stage Operation`:** Defines what needs to be done.
  * **Job Cards:** Workers fill these out to log the exact time taken to complete the operation on a specific roll.

### 4.2 Quality Inspection & Grading
* **Process:** After a stage (like Grey Roll or Finishing), inspectors check the fabric for defects and assign a grade (e.g., Grade A, B, or C).
* **System Documents:**
  * **`Quality Inspection (QI)`:** Inspectors log their findings here.
  * **`Desar QI Grade Reading` & `Desar Roll Ticket Stage Grade`:** The system takes the QI results and records how much of the roll is Grade A, Grade B, etc., specifically for that manufacturing stage.

---

## 5. Final Packing and Inventory Update

The final step before shipping to the customer.

### 5.1 Packing Stage
* **Process:** Finished, inspected rolls are packed for shipment. Final inventory adjustments are made.
* **System Documents:**
  * **Job Cards:** Completed for the packing labor.
  * **`Stock Entry (Manufacture)`:** Created in Draft. Submitting this finalizes the manufacturing process and moves the finished goods into the designated finished goods warehouse.

### 5.2 Final Grade Movement
* **Process:** Ensure the system's inventory matches the exact quality of the final packed goods.
* **System Document: `Desar Grade Adjustment`**
  * **What it does:** Upon submission of the final Quality Inspection at the Packing stage, the system automatically performs "Grade Movement." It updates the final inventory quantities of Grade A, Grade B, and Grade C stock based entirely on the last inspection results, ensuring accurate valuation and sales availability.
