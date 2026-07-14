# P2 — Real Test Coverage + CI

Follow-up to the Production-Readiness Audit (P0/P1 done). Two findings:
- ~53% of existing tests reimplement logic locally ("Mirror of...") instead of calling real `services`/`events` code — wouldn't catch a real regression.
- No CI at all. `test_e2e_cycle.py` is a manual `bench execute` script; nothing runs automatically.

## Tracer bullet

Smallest slice through all layers first, before committing to converting all ~105 mirror tests or building a full CI matrix:

1. Convert one real, low-risk mirror test — `test_new_features.py::TestGradeAdjustmentMath` — to call the actual `events.quality_inspection._validate_adjustment_quantities` instead of reimplementing its math. Proves the pattern: real function is pure enough to unit-test directly, just needs a bound `frappe.db` (guarded with `self.skipTest(...)` when run outside `bench`, so plain `pytest` still degrades gracefully instead of erroring).
2. Add `.github/workflows/run-tests.yml` — spins up mariadb + a fresh bench + site, installs `erpnext` + `desar_manufacturing`, runs `bench run-tests --app desar_manufacturing`. Standard Frappe-app CI skeleton — **unverified**, no way to run GitHub Actions from this environment. First real push will surface any bench-version/CLI-flag mismatches; iterate from there.

## Deferred (not in this slice)

- Converting the other ~100 mirror tests to call real code — bigger, do only if the tracer bullet's pattern holds up in CI.
- Fixing `bench --site excel run-tests` site-wide breakage from the `hrms` app's `IntegrationTestCase` import (noted in PROGRESS.md) — doesn't affect this repo's CI since CI installs a clean site without `hrms`.
