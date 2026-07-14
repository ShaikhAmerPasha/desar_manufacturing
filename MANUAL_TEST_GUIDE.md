# Manual End-to-End Test Guide

Covers everything built/fixed this session. Site: `excel` (not `desar_manufacturing.localhost` — that's stale, see PROGRESS.md). Login: `Administrator`/your admin password, or use **User List → Impersonate** to test as a specific role without knowing its password.

Existing test users (already have the right roles): `supervisor@desar.com`, `operator@desar.com`, `qc@desar.com`.

---

## 1. Dynamic Beam Split — uneven splits

1. Create a **Sales Order** for a Shemagh item (e.g. `Shemagh-VIC-60-A`), qty **161**.
2. Run MRP → create a **Production Plan** for it.
3. On the Production Plan, click **DESAR → Create DESAR Production Order**.
   - ✅ Preview dialog should show qty **161** (not rounded to 200 or similar).
4. Open the new **DESAR Production Order**. Click **Start Warping** → **Complete Warping** (submit the Transfer SE when it appears, then click Complete Warping).
5. Click **Split Beam**. In the dialog, the grid should default to `1 x 161`.
   - Change it to two rows: `1 x 80` and `1 x 81`.
   - Watch the summary line under the grid — should turn green "✓ matches order qty" once it reads `Pieces: 161 / 161`.
6. Click **Split**.
   - ✅ Success message lists 2 rolls with planned qty 80 and 81.
   - ✅ Roll Chains table now shows 2 rows, `Planned Qty (pcs)` = 80 and 81.
7. **Negative test:** repeat steps 4-5 on a fresh PO but enter rows summing to 160 or 162 → clicking Split must be rejected with a clear "short/over" message, nothing created.

---

## 2. Grade tracking + grade-adjustment table

Using the PO from above (or any PO with Beam Split done):

1. Run one roll through **Start Grey Roll → Complete Grey Roll**. When the Quality Inspection opens, fill in Grade A/B/C readings, submit.
2. **Start Finished Roll → Complete Finished Roll**. Fill grade readings again (can differ from grey stage — e.g. grey was 40/5/2, finishing 38/5/4).
3. **Start Packing → Complete Packing → Finalize Packing**. On the final QI:
   - ✅ Enter grade readings again. If they don't match the Finishing-stage totals, submitting must **throw**, asking you to fill the **Grade Adjustments During Packing** table.
   - Fill in the adjustment table (from_grade/to_grade/qty/reason) so the numbers reconcile, then submit.
   - ✅ Submission succeeds once the adjustment math reconciles exactly.

---

## 3. Repack routing — Grade C now goes somewhere real

Right after the final QI submits (step 2.3 above):

1. Open the auto-created **Repack Stock Entry** (linked from the QI, or `Stock Entry` list filtered by `custom_source_qi`).
2. ✅ Check the target rows: Grade A → `Finished Goods Grade A - ST`, Grade B → `Finished Goods Grade B - ST`, **Grade C → `Finished Goods Grade C - ST`** (this warehouse didn't exist before this session — Grade C used to just vanish as unlogged scrap).
3. Submit the Repack SE. Confirm stock actually lands in Grade C's warehouse (Stock Balance report, filter by that warehouse).

---

## 4. Packing job-card operations — 8 ops instead of 1

The config now exists on Design Masters `563`, `DM-2026-0001/0002/0003/0007`, but **4 of those 5 still have an old BOM** cached with only 1 generic "Packing" op — the new config won't show until that BOM is regenerated.

1. Pick **`DM-2026-0007`** first — it has no BOM yet, so this is the clean case.
2. Open that Design Master → click **Create All BOMs**.
3. Open the resulting Packing BOM → **Operations** tab.
   - ✅ Should show 8 rows: Classification, Cutting by Piece, Piece Finishing, Steaming, Ironing, Stamping, Packaging, Boxing — each with a workstation.
4. Run a Packing Work Order for that design through to Job Card creation (submit the WO).
   - ✅ 8 Job Cards should appear, one per operation.
5. **For the other 4 Design Masters** (563, 0001, 0002, 0003): their current BOM still has 1 op. If you want to see 8 ops there too, that BOM needs to be manually regenerated — flag this back to me before doing it, since it touches BOMs some of these designs already have completed production history against.

---

## 5. Concurrency fix — no more duplicate records on double-click

1. Get a PO with a roll at "Grey Roll: Not Started".
2. Open the same PO in **two browser tabs** (or two people, two sessions).
3. Click **Start Grey Roll** in both tabs as close together as you can.
   - ✅ Exactly one Work Order + Transfer Stock Entry should be created. The second click should show an error like "Grey Roll for Roll {n} is already In Progress" — not a second WO/SE.
4. Check `Work Order` list filtered by that roll's item/PO — confirm no duplicates.

---

## 6. Permission checks — role restrictions now actually apply

Use **Impersonate** (User list → pick user → Impersonate) to switch identity without a password.

1. As `qc@desar.com` (DESAR QC Inspector, read-only role): try clicking **Start Warping** or **Split Beam** on any PO.
   - ✅ Should be blocked with a permission error — QC could do this before, shouldn't be able to now.
2. As `operator@desar.com` (DESAR Operator): try running a stage transition (Start Grey Roll etc.) on an existing PO.
   - ✅ Should work — Operator is allowed to run stages.
3. Still as Operator: go to a Production Plan and try **Create DESAR Production Order**.
   - ✅ Should be blocked — only Supervisor/System Manager can create a new PO.
4. As `supervisor@desar.com`: repeat step 3.
   - ✅ Should succeed.
5. Also as Operator, try the older API surface: open a Work Order for this app's flow and use **Finish Work Order** / **Create Transfer Entry** actions if visible in your UI (these are also gated now).
   - ✅ Same pass/fail pattern as steps 1-2.

---

## 7. Things I could not verify myself — please confirm

- **Nothing broke visually.** I only ran the Python test suite (215/215 passing) and checked JS with `node --check` — never opened a real browser this session. Please actually click through sections 1-4 above and watch for anything that looks wrong on screen, not just "did it error."
- **CI workflow** (`.github/workflows/run-tests.yml`) — untested, since I can't run GitHub Actions from here. Push to a branch and check the Actions tab; it will likely need at least one iteration to get the bench-setup steps exactly right.
- **Dashboard truncation warning** — only fires past 1000 Job Cards/Stock Entries/QIs on one PO, unlikely to hit in a manual test. Nothing to check unless you have a PO that large.
