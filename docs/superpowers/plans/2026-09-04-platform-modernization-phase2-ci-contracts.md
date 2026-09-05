# Platform Modernization — Phase 2: CI Depth + Data Contracts (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen CI (scoped mypy strict, coverage gate, ruff format + pre-commit) and gate the gold layer with dbt contracts, backed by a hermetic fixture bronze snapshot that drives `dbt build` end-to-end in CI.

**Architecture:** Static typing lands on the four packages Phase 1 kept clean (`src/orchestration`, `src/ingest`, `src/utils`, `src/quality`) — `src/transform` stays excluded, recorded as a known gap. A version-controlled fixture bronze snapshot (~10 studies covering all statuses and phases) seeds a temp project root in a session-scoped pytest fixture: real `run_transform`, then `dbt build` in a subprocess (dbt's in-process adapter holds the DuckDB file open, which blocks the read-only assertion connections — subprocess isolation is deliberate). Mart shape/grain assertions read the fixture warehouse; contracts with declared `data_type` per column are enforced on all 15 marts models so schema drift fails the build. Every number in this plan was validated against the real toolchain before planning: the fixture passes the full 106-node dbt build (3 seeds, 30 models, 73 tests) with contracts enforced, and the mypy fix set passes `--strict` clean.

**Tech Stack:** Python 3.13 (floor 3.11), uv dependency groups, mypy (2.3.1 verified), pandas-stubs, pre-commit, ruff (line length 100), pytest + pytest-cov, dbt-core 1.11.14 / dbt-duckdb 1.10.1, DuckDB.

**Spec:** `docs/superpowers/specs/2026-09-04-platform-modernization-design.md` (this plan implements its "Week 2 — CI depth + contracts" milestone; Phase 3 covers scheduling + GCS lake, Phase 4 BigQuery portability).

## Baselines (measured 2026-09-04 in this worktree)

- mypy `--strict src/orchestration src/ingest src/utils src/quality`: **17 errors in 11 files** (Task 1 fixes all; verified clean with the exact edits below).
- pytest coverage `--cov=src`: **TOTAL 71%** (716/1009 statements = 70.96%, 67 passed / 8 skipped). Gate set to 70 whole-percent floor in Task 3 because 71 would fail against 70.96; Task 6 ratchets the gate upward if the fixture suite pushes TOTAL ≥ 71.
- dbt build on the fixture snapshot: **PASS=106 WARN=0 ERROR=0** (with and without contracts).

## Global Constraints

- Python floor: `requires-python = ">=3.11"` (unchanged).
- Dependency management exclusively via `uv` and dependency groups in `pyproject.toml`; never `pip install`.
- `mypy` and `pandas-stubs` join the existing `dev` group (spec's dependency-placement rule).
- Ruff: line length 100, rules `E,F,I,W,UP,B`; all new code must pass `uv run ruff check src tests dashboard` (and, from Task 2, `uv run ruff format --check src tests dashboard`).
- mypy strict on `src/orchestration`, `src/ingest`, `src/utils`, `src/quality` from Task 1 onward; `src/transform` deliberately excluded (pandas-heavy annotation churn deferred — recorded known gap per spec).
- Tests never hit the real ClinicalTrials.gov API and never read/write outside `tmp_path`/`tmp_path_factory` (via `CTI_PROJECT_ROOT`).
- `data/` is git-ignored and must never be staged.
- Conventional Commits for every commit.
- The existing 67 pytest tests must stay green after every task (`uv run pytest`); expected counts grow with new tests.
- Work happens in the worktree `.worktrees/feat/platform-modernization` on branch `feat/platform-modernization`.

## File Structure (Phase 2)

| File | Responsibility |
|---|---|
| `pyproject.toml` | dev-group deps (mypy, pandas-stubs, pre-commit), `[tool.mypy]`, `[tool.coverage.*]` |
| `.github/workflows/ci.yml` | type-check step, format check, coverage gate |
| `.pre-commit-config.yaml` | hygiene hooks + ruff check/format + scoped mypy (local hooks) |
| `Makefile` | `lint` target extended to format-check + mypy |
| `src/utils/logging.py`, `src/ingest/retry_policy.py`, `src/ingest/ctg_client.py` | mypy strict fixes (annotations only) |
| `src/quality/reconciliation.py`, `src/quality/profiling.py`, `src/quality/data_quality_report.py` | mypy strict fixes (assert narrowing, dict type args) |
| `src/orchestration/assets/bronze.py`, `src/orchestration/assets/silver.py`, `src/orchestration/assets/dbt_assets.py` | mypy strict fixes (generic type args) |
| `tests/fixtures/bronze_snapshot/page=00001.json` | Fixture API page: 10 studies, all statuses/phases |
| `tests/conftest.py` | + session fixture `fixture_project_root` (seeds fixture project, runs transform, dbt build) |
| `tests/test_dbt_fixture_build.py` | Build test, mart grain/shape assertions, contract-enforcement test |
| `dbt_clinical_trials/models/marts/_marts.yml` | Contracts: `enforced: true` + declared `data_type` on all 15 marts models |

---

### Task 1: mypy strict on the four scoped packages

**Files:**
- Modify: `pyproject.toml` (dev group + new `[tool.mypy]` section)
- Modify: `.github/workflows/ci.yml` (add Type check step)
- Modify: `src/utils/logging.py`, `src/ingest/retry_policy.py`, `src/ingest/ctg_client.py`, `src/quality/reconciliation.py`, `src/quality/profiling.py`, `src/quality/data_quality_report.py`, `src/orchestration/assets/bronze.py`, `src/orchestration/assets/silver.py`, `src/orchestration/assets/dbt_assets.py`
- Test: full suite + `uv run mypy` (no new test files; behavior-neutral edits verified by existing suite)

**Interfaces:**
- Consumes: nothing new.
- Produces: `uv run mypy` (reads `[tool.mypy]` with `files = [...]`) exits 0 and stays green for Tasks 2–6; `setup_logging() -> "Logger"` makes every caller type-clean.

- [ ] **Step 1: Add dev dependencies and the mypy config**

```bash
uv add --group dev "mypy>=1.11" "pandas-stubs>=2.2"
```

Then add to `pyproject.toml` (after the `[tool.ruff.lint]` section):

```toml
[tool.mypy]
python_version = "3.11"
files = ["src/orchestration", "src/ingest", "src/utils", "src/quality"]
strict = true
```

- [ ] **Step 2: Run mypy to see the baseline fail**

Run: `uv run mypy`
Expected: FAIL — 17 errors across the 9 files fixed below (missing return annotations, missing param annotations, bare `dict`/`list` generics, unindexed `tuple | None` from `fetchone()`, bare `MaterializeResult`/`Output` generics, missing pandas stubs).

- [ ] **Step 3: Fix `src/utils/logging.py`** — annotate the return type; the `Logger` import is type-checking-only (loguru does not export it at runtime).

Change the top of the file to:

```python
import os
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Logger
```

and change the signature to:

```python
def setup_logging() -> "Logger":
```

- [ ] **Step 4: Fix `src/ingest/retry_policy.py`** — annotate the tenacity callback parameter.

Add to the import block (stdlib first):

```python
from typing import Any
```

and change the nested function signature to:

```python
    def _before_sleep(retry_state: Any) -> None:
```

- [ ] **Step 5: Fix `src/ingest/ctg_client.py`** — annotate the context-manager args.

Change:

```python
    def __exit__(self, *exc_info: object) -> None:
```

- [ ] **Step 6: Fix `src/quality/reconciliation.py`** — narrow the three `fetchone() -> tuple | None` sites with asserts (count queries always return one row; the assert documents that invariant).

In `_silver_trial_stats`, change:

```python
    row = duckdb.sql(
        f"select count(*), count(distinct nct_id) from read_parquet('{path.as_posix()}')"
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])
```

In the warehouse block of `run_reconciliation`, change:

```python
            row = con.execute("select count(*) from main_marts.dim_trial").fetchone()
            assert row is not None
            dim_trial_count = row[0]
```

and:

```python
            flag_row = con.execute(
                "select count(*) from main_marts.fct_trial_snapshot where current_record_flag"
            ).fetchone()
            assert flag_row is not None
            current_flags = flag_row[0]
```

- [ ] **Step 7: Fix `src/quality/profiling.py`** — type-arg the dicts.

Add `from typing import Any` to the import block (stdlib group, before `import pandas as pd`... exact position: after `from pathlib import Path`, before `import pandas as pd`). Then change:

```python
def profile_entity(path: Path) -> dict[str, Any]:
```

```python
def profile_run(run_id: str, config: ProjectConfig | None = None) -> dict[str, Any]:
```

```python
    report: dict[str, Any] = {
```

- [ ] **Step 8: Fix `src/quality/data_quality_report.py`** — type-arg the row list.

Add `from typing import Any` after `from pathlib import Path` in the import block, and change:

```python
def _reliability_rows(cfg: ProjectConfig) -> list[dict[str, Any]]:
```

- [ ] **Step 9: Fix the three orchestration asset modules** — dagster's `MaterializeResult` and `Output` are generic; metadata-only results are `MaterializeResult[None]`.

In `src/orchestration/assets/bronze.py` and `src/orchestration/assets/silver.py`, change the asset signature:

```python
) -> MaterializeResult[None]:
```

In `src/orchestration/assets/dbt_assets.py`, change the return annotation union:

```python
) -> Iterator[
    Output[Any] | AssetMaterialization | AssetObservation | AssetCheckResult | AssetCheckEvaluation
]:
```

- [ ] **Step 10: Run mypy to verify clean**

Run: `uv run mypy`
Expected: `Success: no issues found in 25 source files`.

- [ ] **Step 11: Add the CI type-check step**

In `.github/workflows/ci.yml`, after the `Lint` step, insert:

```yaml
      - name: Type check
        run: uv run mypy
```

- [ ] **Step 12: Full suite and lint**

Run: `uv run ruff check src tests dashboard && uv run pytest`
Expected: ruff clean; `67 passed, 8 skipped`.

- [ ] **Step 13: Commit**

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml src
git commit -m "feat(ci): enforce mypy strict on orchestration, ingest, utils, quality"
```

---

### Task 2: ruff format + pre-commit

**Files:**
- Modify: `pyproject.toml` (add `pre-commit` to dev group)
- Create: `.pre-commit-config.yaml`
- Modify: `.github/workflows/ci.yml` (lint step gains format check)
- Modify: `Makefile` (lint target gains format check + mypy)
- Modify: whichever files `ruff format` rewrites across `src tests dashboard` (mechanical reformatting, committed as-is)

**Interfaces:**
- Consumes: the ruff configuration in `pyproject.toml` (line length 100).
- Produces: `.pre-commit-config.yaml` that Tasks 3–6 rely on for local gates; CI enforces `ruff format --check` from here on — later tasks must author format-clean files.

- [ ] **Step 1: Add the pre-commit dependency**

```bash
uv add --group dev "pre-commit>=3.7"
uv sync --all-groups
```

- [ ] **Step 2: Create `.pre-commit-config.yaml`**

Local hooks keep ruff/mypy versions pinned by `uv.lock` instead of a second, drifting pin set; mypy runs scoped (its own `files` config) with `pass_filenames: false` because mypy needs whole-program context.

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace

  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --force-exclude
        language: system
        types: [python]

      - id: ruff-format
        name: ruff format
        entry: uv run ruff format --force-exclude
        language: system
        types: [python]

      - id: mypy
        name: mypy (scoped)
        entry: uv run mypy
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 3: Adopt the formatter**

```bash
uv run ruff format src tests dashboard
uv run ruff check src tests dashboard && uv run pytest
```

Expected: ruff clean; `67 passed, 8 skipped` (formatting is behavior-neutral).

- [ ] **Step 4: Enforce format in CI**

In `.github/workflows/ci.yml`, replace the `Lint` step with:

```yaml
      - name: Lint
        run: |
          uv run ruff check src tests dashboard
          uv run ruff format --check src tests dashboard
```

- [ ] **Step 5: Extend the Makefile lint target**

Replace the `lint` target with:

```make
lint: ## Lint and type-check Python code
	uv run ruff check src tests dashboard
	uv run ruff format --check src tests dashboard
	uv run mypy
```

(`lint` is already listed in `.PHONY`.)

- [ ] **Step 6: Verify pre-commit runs green**

```bash
uv run pre-commit run --all-files
```

Expected: all hooks pass (end-of-file-fixer / trailing-whitespace may auto-fix tracked files — re-stage any fixes). If the mypy hook is slow on first run, that is mypy building its cache; subsequent runs are seconds.

- [ ] **Step 7: Commit**

```bash
git add -A
git status  # confirm nothing under data/ is staged
git commit -m "chore(ci): adopt ruff format and pre-commit hooks"
```

---

### Task 3: Coverage gate

**Files:**
- Modify: `pyproject.toml` (`[tool.coverage.run]`, `[tool.coverage.report]`)
- Modify: `.github/workflows/ci.yml` (pytest step gains coverage flags)

**Interfaces:**
- Consumes: pytest-cov (already in the dev group).
- Produces: CI fails below the coverage floor. Task 6 ratchets the floor.

- [ ] **Step 1: Record the baseline**

```bash
uv run pytest --cov=src --cov-report=term-missing 2>&1 | tail -5
```

Expected: `TOTAL ... 71%` (716/1009 = 70.96% as of 2026-09-04). If the measured TOTAL differs by more than a point, stop and report before choosing the floor.

- [ ] **Step 2: Add coverage config to `pyproject.toml`**

```toml
[tool.coverage.run]
source = ["src"]

[tool.coverage.report]
show_missing = true
```

- [ ] **Step 3: Wire the gate into CI**

Replace the `Unit tests` step with:

```yaml
      - name: Unit tests with coverage gate
        run: uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=70
```

70 is the whole-percent floor the 70.96% baseline passes with margin; `--cov-fail-under=71` would fail today (70.96 < 71). Task 6 ratchets this upward.

- [ ] **Step 4: Verify the gate passes**

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=70
```

Expected: `67 passed, 8 skipped`, `Required test coverage of 70% reached. Total percentages: 70.96%`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml
git commit -m "feat(ci): add coverage gate at 70 percent floor"
```

---

### Task 4: Fixture bronze snapshot + hermetic dbt build integration test

**Files:**
- Create: `tests/fixtures/bronze_snapshot/page=00001.json`
- Modify: `tests/conftest.py` (add `shutil`, `sys` imports + session fixture `fixture_project_root`)
- Create: `tests/test_dbt_fixture_build.py`

**Interfaces:**
- Consumes: `src.config.load_config()` (env-driven via `CTI_PROJECT_ROOT`); `src.ingest.snapshot_manifest.IngestionManifest / write_manifest / write_summary`; `src.transform.build_silver_entities.run_transform(config=...)`; the dbt project `dbt_clinical_trials`; `tests.conftest.CONFIG_YAML`.
- Produces: session fixture `fixture_project_root` returning the temp project root `Path` containing `data/warehouse/clinical_trials.duckdb` (built gold warehouse) and `dbt_target/manifest.json` (dbt manifest). Tasks 5–6 assert against both. Fixture run ID: `20260901T120000Z_fixture01`.

**Fixture design (why these 10 studies):** statuses RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, ENROLLING_BY_INVITATION, NOT_YET_RECRUITING, SUSPENDED, TERMINATED, WITHDRAWN; phases EARLY_PHASE1, PHASE1, PHASE2, PHASE4, PHASE2/PHASE3 (multi), PHASE3, NA→NOT_APPLICABLE (observational), missing→UNKNOWN; one non-US site (Berlin) and one Canadian site to exercise the U.S.-scope exclusion; conditions spanning taxonomy groups alzheimers_disease, mild_cognitive_impairment, lewy_body_dementia, frontotemporal_dementia, cognitive_impairment_other, non_dementia_other; apostrophe variant "Alzheimer's Disease" (exact-match path); a collaborator sponsor on two studies; one `hasResults: true` study with a results-post date; one multi-condition study. Verified: this page drives the full 106-node dbt build green.

- [ ] **Step 1: Create the fixture page**

Create `tests/fixtures/bronze_snapshot/page=00001.json` with exactly:

```json
{
  "studies": [
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000001",
          "briefTitle": "Donepezil Add-On in Mild Alzheimer Disease",
          "officialTitle": "A Phase 3 Study of Donepezil Add-On Therapy in Mild Alzheimer Disease"
        },
        "statusModule": {
          "overallStatus": "RECRUITING",
          "lastKnownStatus": "RECRUITING",
          "statusVerifiedDate": "2026-07-01",
          "startDateStruct": { "date": "2025-02-01" },
          "primaryCompletionDateStruct": { "date": "2027-06-30" },
          "completionDateStruct": { "date": "2027-12-31" },
          "studyFirstPostDateStruct": { "date": "2025-03-15" },
          "lastUpdatePostDateStruct": { "date": "2026-07-15" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "NeuroPharm Inc", "class": "INDUSTRY" },
          "collaborators": [
            { "name": "Alzheimer Research Network", "class": "NETWORK" }
          ]
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE3"],
          "enrollmentInfo": { "count": 500, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Alzheimer Disease"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "Donepezil 10mg", "type": "Drug", "description": "Once daily oral dose." },
            { "name": "Placebo oral tablet", "type": "Drug" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "ADAS-Cog13 change from baseline", "timeFrame": "78 weeks" }
          ],
          "secondaryOutcomes": [
            { "measure": "ADCS-ADL change", "timeFrame": "78 weeks" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "55 Years",
          "maximumAge": "85 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: diagnosis of mild Alzheimer disease. Exclusion: severe renal impairment."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Duke Memory Center", "city": "Durham", "state": "North Carolina", "zip": "27710", "country": "United States", "status": "RECRUITING" },
            { "facility": "UCSF Memory Clinic", "city": "San Francisco", "state": "CA", "zip": "94143", "country": "United States", "status": "RECRUITING" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000002",
          "briefTitle": "Biomarkers in Amnestic Mild Cognitive Impairment"
        },
        "statusModule": {
          "overallStatus": "ACTIVE_NOT_RECRUITING",
          "statusVerifiedDate": "2026-06-15",
          "startDateStruct": { "date": "2024-05-01" },
          "primaryCompletionDateStruct": { "date": "2026-01-31" },
          "completionDateStruct": { "date": "2026-01-31" },
          "studyFirstPostDateStruct": { "date": "2024-06-01" },
          "lastUpdatePostDateStruct": { "date": "2026-06-20" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "National Institute on Aging", "class": "NIH" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE2"],
          "enrollmentInfo": { "count": 120, "type": "Actual" }
        },
        "conditionsModule": {
          "conditions": ["Mild Cognitive Impairment"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "CSF biomarker panel", "type": "Procedure" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "CSF tau concentration", "timeFrame": "12 months" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "50 Years",
          "maximumAge": "80 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: amnestic MCI diagnosis."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Mass General Hospital", "city": "Boston", "state": "Massachusetts", "zip": "02114", "country": "United States", "status": "COMPLETED" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000003",
          "briefTitle": "Glucose Control in Type 2 Diabetes"
        },
        "statusModule": {
          "overallStatus": "COMPLETED",
          "statusVerifiedDate": "2026-05-01",
          "startDateStruct": { "date": "2023-01-15" },
          "primaryCompletionDateStruct": { "date": "2025-08-01" },
          "completionDateStruct": { "date": "2025-10-31" },
          "studyFirstPostDateStruct": { "date": "2023-02-01" },
          "resultsFirstPostDateStruct": { "date": "2026-02-15" },
          "lastUpdatePostDateStruct": { "date": "2026-02-15" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "MetaDiab Labs", "class": "INDUSTRY" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE3"],
          "enrollmentInfo": { "count": 2000, "type": "Actual" }
        },
        "conditionsModule": {
          "conditions": ["Type 2 Diabetes"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "Metformin extended release", "type": "Drug" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "HbA1c change", "timeFrame": "52 weeks" }
          ],
          "otherOutcomes": [
            { "measure": "Body weight change", "timeFrame": "52 weeks" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "18 Years",
          "maximumAge": "75 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: HbA1c 7.5-10.5%."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Stanford Diabetes Center", "city": "Palo Alto", "state": "California", "zip": "94305", "country": "United States", "status": "COMPLETED" },
            { "facility": "Baylor Endocrine Clinic", "city": "Houston", "state": "Texas", "zip": "77030", "country": "United States", "status": "COMPLETED" },
            { "facility": "Mount Sinai Diabetes Center", "city": "New York", "state": "NY", "zip": "10029", "country": "United States", "status": "COMPLETED" }
          ]
        }
      },
      "hasResults": true
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000004",
          "briefTitle": "Neoadjuvant Therapy in HER2+ Breast Cancer"
        },
        "statusModule": {
          "overallStatus": "ENROLLING_BY_INVITATION",
          "statusVerifiedDate": "2026-08-01",
          "startDateStruct": { "date": "2025-09-01" },
          "primaryCompletionDateStruct": { "date": "2028-03-01" },
          "completionDateStruct": { "date": "2028-09-01" },
          "studyFirstPostDateStruct": { "date": "2025-09-20" },
          "lastUpdatePostDateStruct": { "date": "2026-08-10" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "Pacific Oncology Institute", "class": "ACADEMIC" },
          "collaborators": [
            { "name": "Oncology Trials Group", "class": "NETWORK" }
          ]
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE4"],
          "enrollmentInfo": { "count": 300, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Breast Cancer"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "Trastuzumab", "type": "Drug" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "Pathologic complete response rate", "timeFrame": "6 months" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "18 Years",
          "maximumAge": "70 Years",
          "sex": "FEMALE",
          "eligibilityCriteria": "Inclusion: HER2-positive breast cancer."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Seattle Cancer Center", "city": "Seattle", "state": "Washington", "zip": "98109", "country": "United States", "status": "ENROLLING_BY_INVITATION" },
            { "facility": "Northwestern Oncology", "city": "Chicago", "state": "IL", "zip": "60611", "country": "United States", "status": "ENROLLING_BY_INVITATION" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000005",
          "briefTitle": "Cognitive Health Screening in Older Adults"
        },
        "statusModule": {
          "overallStatus": "NOT_YET_RECRUITING",
          "statusVerifiedDate": "2026-08-20",
          "startDateStruct": { "date": "2026-10-01" },
          "primaryCompletionDateStruct": { "date": "2027-09-30" },
          "completionDateStruct": { "date": "2027-09-30" },
          "studyFirstPostDateStruct": { "date": "2026-08-25" },
          "lastUpdatePostDateStruct": { "date": "2026-08-25" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "Cedar Cognitive Institute", "class": "ACADEMIC" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE1"],
          "enrollmentInfo": { "count": 60, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Cognitive Health"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "Computerized cognitive training", "type": "Behavioral" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "Memory composite score", "timeFrame": "24 weeks" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": true,
          "minimumAge": "60 Years",
          "maximumAge": "80 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: community-dwelling older adults."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Cedar Clinic Los Angeles", "city": "Los Angeles", "state": "California", "zip": "90095", "country": "United States", "status": "NOT_YET_RECRUITING" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000006",
          "briefTitle": "Rivastigmine in Lewy Body Dementia"
        },
        "statusModule": {
          "overallStatus": "SUSPENDED",
          "statusVerifiedDate": "2026-04-10",
          "startDateStruct": { "date": "2024-11-01" },
          "primaryCompletionDateStruct": { "date": "2027-05-01" },
          "completionDateStruct": { "date": "2027-11-01" },
          "studyFirstPostDateStruct": { "date": "2024-12-01" },
          "lastUpdatePostDateStruct": { "date": "2026-04-15" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "NeuroPharm Inc", "class": "INDUSTRY" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE2", "PHASE3"],
          "enrollmentInfo": { "count": 240, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Lewy Body Dementia"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "Rivastigmine patch", "type": "Drug" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "CIBIC-plus score", "timeFrame": "48 weeks" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "50 Years",
          "maximumAge": "85 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: probable DLB."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Charite Memory Clinic", "city": "Berlin", "country": "Germany", "status": "SUSPENDED" },
            { "facility": "Johns Hopkins Memory Center", "city": "Baltimore", "state": "Maryland", "zip": "21287", "country": "United States", "status": "SUSPENDED" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000007",
          "briefTitle": "Anti-Amyloid Antibody in Early Alzheimer's Disease"
        },
        "statusModule": {
          "overallStatus": "TERMINATED",
          "statusVerifiedDate": "2026-03-01",
          "startDateStruct": { "date": "2023-06-01" },
          "primaryCompletionDateStruct": { "date": "2025-12-01" },
          "completionDateStruct": { "date": "2025-12-01" },
          "studyFirstPostDateStruct": { "date": "2023-07-01" },
          "lastUpdatePostDateStruct": { "date": "2026-03-10" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "National Institute on Aging", "class": "NIH" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE3"],
          "enrollmentInfo": { "count": 800, "type": "Actual" }
        },
        "conditionsModule": {
          "conditions": ["Alzheimer's Disease"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "Anti-amyloid antibody infusion", "type": "Biological" }
          ]
        },
        "outcomesModule": {
          "primaryOutcomes": [
            { "measure": "CDR-SB change", "timeFrame": "18 months" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "50 Years",
          "maximumAge": "90 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: early Alzheimer disease with amyloid confirmation."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Mayo Clinic Florida", "city": "Jacksonville", "state": "Florida", "zip": "32224", "country": "United States", "status": "TERMINATED" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000008",
          "briefTitle": "Memory Loss Caregiver Support Withdrawn Study"
        },
        "statusModule": {
          "overallStatus": "WITHDRAWN",
          "statusVerifiedDate": "2026-01-05",
          "startDateStruct": { "date": "2026-03-01" },
          "studyFirstPostDateStruct": { "date": "2026-01-10" },
          "lastUpdatePostDateStruct": { "date": "2026-01-15" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "Cedar Cognitive Institute", "class": "ACADEMIC" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "enrollmentInfo": { "count": 40, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Memory Loss"]
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Cedar Clinic Durham", "city": "Durham", "state": "NC", "zip": "27705", "country": "United States", "status": "WITHDRAWN" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000009",
          "briefTitle": "Natural History of Mild Cognitive Impairment"
        },
        "statusModule": {
          "overallStatus": "RECRUITING",
          "statusVerifiedDate": "2026-07-20",
          "startDateStruct": { "date": "2025-01-01" },
          "primaryCompletionDateStruct": { "date": "2028-01-01" },
          "completionDateStruct": { "date": "2028-01-01" },
          "studyFirstPostDateStruct": { "date": "2025-01-20" },
          "lastUpdatePostDateStruct": { "date": "2026-07-25" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "Pacific Oncology Institute", "class": "ACADEMIC" }
        },
        "designModule": {
          "studyType": "OBSERVATIONAL",
          "phases": ["NA"],
          "enrollmentInfo": { "count": 400, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Mild Cognitive Impairment", "Normal Aging"]
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Toronto Memory Program", "city": "Toronto", "country": "Canada", "status": "RECRUITING" },
            { "facility": "UC San Diego Shiley Center", "city": "San Diego", "state": "California", "zip": "92093", "country": "United States", "status": "RECRUITING" }
          ]
        }
      },
      "hasResults": false
    },
    {
      "protocolSection": {
        "identificationModule": {
          "nctId": "NCT00000010",
          "briefTitle": "Early Phase 1 Study in Frontotemporal Dementia Spectrum"
        },
        "statusModule": {
          "overallStatus": "RECRUITING",
          "statusVerifiedDate": "2026-08-05",
          "startDateStruct": { "date": "2026-02-01" },
          "primaryCompletionDateStruct": { "date": "2027-08-01" },
          "completionDateStruct": { "date": "2027-08-01" },
          "studyFirstPostDateStruct": { "date": "2026-02-15" },
          "lastUpdatePostDateStruct": { "date": "2026-08-10" }
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": { "name": "NeuroPharm Inc", "class": "INDUSTRY" }
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["EARLY_PHASE1"],
          "enrollmentInfo": { "count": 30, "type": "Anticipated" }
        },
        "conditionsModule": {
          "conditions": ["Frontotemporal Dementia", "Alzheimer Disease"]
        },
        "armsInterventionsModule": {
          "interventions": [
            { "name": "TAU aggregation inhibitor", "type": "Drug" }
          ]
        },
        "outcomesModule": {
          "otherOutcomes": [
            { "measure": "Safety and tolerability", "timeFrame": "6 months" }
          ]
        },
        "eligibilityModule": {
          "healthyVolunteers": false,
          "minimumAge": "45 Years",
          "maximumAge": "80 Years",
          "sex": "ALL",
          "eligibilityCriteria": "Inclusion: ftld spectrum diagnosis."
        },
        "contactsLocationsModule": {
          "locations": [
            { "facility": "Columbia University Medical Center", "city": "New York", "state": "New York", "zip": "10032", "country": "United States", "status": "RECRUITING" }
          ]
        }
      },
      "hasResults": false
    }
  ],
  "totalCount": 10,
  "nextPageToken": null
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_dbt_fixture_build.py` with exactly:

```python
"""Hermetic end-to-end test: fixture bronze snapshot through the full dbt graph.

The session fixture in tests/conftest.py builds one warehouse from
tests/fixtures/bronze_snapshot; every test in this module asserts against it.
No network, no real API, everything under tmp_path_factory.
"""

from pathlib import Path

FIXTURE_RUN_ID = "20260901T120000Z_fixture01"


def test_dbt_build_passes_on_fixture_snapshot(fixture_project_root: Path) -> None:
    # The session fixture asserts dbt's exit code before returning; this pins
    # the artifacts the later assertions read.
    assert (fixture_project_root / "data/warehouse/clinical_trials.duckdb").exists()
    assert (fixture_project_root / "dbt_target/manifest.json").exists()
```

- [ ] **Step 3: Add the session fixture to `tests/conftest.py`**

Add `shutil` and `sys` to the stdlib import block, add module constants below `CONFIG_YAML`:

```python
REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RUN_ID = "20260901T120000Z_fixture01"
```

and append the fixture (its layout mirrors the Phase 1 `dbt_manifest` session fixture):

```python
@pytest.fixture(scope="session")
def fixture_project_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build bronze→silver→gold from the fixture snapshot; dbt build once per session.

    dbt runs in a subprocess: dbt's in-process adapter keeps the DuckDB file
    open, which would block the read-only connections the assertions use.
    """
    root = tmp_path_factory.mktemp("fixture_project")
    mp = pytest.MonkeyPatch()
    mp.setenv("CTI_PROJECT_ROOT", str(root))
    try:
        (root / "config").mkdir()
        (root / "config" / "project_config.yml").write_text(CONFIG_YAML, encoding="utf-8")
        for name in (
            "condition_taxonomy.yml",
            "geography_rules.yml",
            "score_weights.yml",
            "roi_assumptions.yml",
        ):
            shutil.copy(REPO_ROOT / "config" / name, root / "config" / name)

        from src.config import load_config
        from src.ingest.snapshot_manifest import (
            IngestionManifest,
            write_manifest,
            write_summary,
        )
        from src.utils.dates import utc_now

        run_dir = root / "data/bronze/api_responses" / f"run_id={FIXTURE_RUN_ID}"
        run_dir.mkdir(parents=True)
        shutil.copy(
            Path(__file__).parent / "fixtures/bronze_snapshot/page=00001.json",
            run_dir / "page=00001.json",
        )

        cfg = load_config()
        manifest = IngestionManifest(
            ingestion_run_id=FIXTURE_RUN_ID,
            query_hash="fixturequeryhash0001",
            endpoint="https://clinicaltrials.gov/api/v2/studies",
            condition="Alzheimer Disease",
            params={"query.cond": "Alzheimer Disease"},
            mode="incremental",
            status="success",
            started_at_utc=utc_now(),
            ended_at_utc=utc_now(),
            page_count=1,
            record_count=10,
            total_count_reported=10,
        )
        write_manifest(cfg.paths.bronze_manifests, manifest)
        write_summary(cfg.paths.bronze_manifests, manifest)

        from src.transform.build_silver_entities import run_transform

        assert run_transform(config=cfg) == [FIXTURE_RUN_ID]

        (root / "profiles.yml").write_text(
            """clinical_trials:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: data/warehouse/clinical_trials.duckdb
      threads: 4
""",
            encoding="utf-8",
        )
        (root / "data/warehouse").mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "dbt.cli.main",
                "build",
                "--project-dir",
                str(REPO_ROOT / "dbt_clinical_trials"),
                "--profiles-dir",
                str(root),
                "--target-path",
                str(root / "dbt_target"),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"dbt build failed:\n{result.stdout[-3000:]}\n{result.stderr[-1000:]}"
        )
        return root
    finally:
        mp.undo()
```

- [ ] **Step 4: Run the test to verify it passes for the right reason**

Run: `uv run pytest tests/test_dbt_fixture_build.py -v`
Expected: PASS (~15s; the fixture builds seeds + 30 models + 73 dbt tests = 106 nodes). If it fails, the assert message carries the dbt stdout tail — fix the fixture, not the assertion.

- [ ] **Step 5: Lint, type-check, full suite**

Run: `uv run ruff check src tests dashboard && uv run ruff format --check src tests dashboard && uv run mypy && uv run pytest`
Expected: clean; `68 passed, 8 skipped` (mypy and format-check now cover the new files).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures tests/conftest.py tests/test_dbt_fixture_build.py
git commit -m "test(dbt): add fixture bronze snapshot and hermetic dbt build integration test"
```

---

### Task 5: Mart grain and shape assertions on the fixture warehouse

**Files:**
- Modify: `tests/test_dbt_fixture_build.py` (append tests)

**Interfaces:**
- Consumes: `fixture_project_root` (Task 4); expected values verified against the fixture-built warehouse: `dim_trial` 10 rows / 8 distinct statuses; `fct_trial_snapshot` 10 rows all current; `fct_trial_site` 14 US rows with 2-letter states and no non-US facilities; `bridge_trial_condition` 12 rows across 6 taxonomy groups; `mart_feasibility_priority_queue` 6 rows, scores in [0,1]; `mart_data_reliability` one reconciled success row.
- Produces: nothing consumed downstream; this is the spec's integration tier ("mart shapes/grains").

- [ ] **Step 1: Append the tests**

Append to `tests/test_dbt_fixture_build.py` (add `duckdb` to imports):

```python
import duckdb


def _rows(root: Path, sql: str) -> list[tuple]:
    con = duckdb.connect(
        str(root / "data/warehouse/clinical_trials.duckdb"), read_only=True
    )
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_dim_trial_grain(fixture_project_root: Path) -> None:
    assert _rows(
        fixture_project_root,
        "select count(*), count(distinct nct_id) from main_marts.dim_trial",
    ) == [(10, 10)]
    statuses = {
        r[0]
        for r in _rows(
            fixture_project_root,
            "select distinct current_overall_status from main_marts.dim_trial",
        )
    }
    assert statuses == {
        "RECRUITING",
        "ACTIVE_NOT_RECRUITING",
        "NOT_YET_RECRUITING",
        "COMPLETED",
        "ENROLLING_BY_INVITATION",
        "SUSPENDED",
        "TERMINATED",
        "WITHDRAWN",
    }


def test_fct_trial_snapshot_one_current_record_per_trial(
    fixture_project_root: Path,
) -> None:
    assert _rows(
        fixture_project_root,
        "select count(*), sum(case when current_record_flag then 1 else 0 end) "
        "from main_marts.fct_trial_snapshot",
    ) == [(10, 10)]


def test_fct_trial_site_us_scope(fixture_project_root: Path) -> None:
    assert _rows(
        fixture_project_root, "select count(*) from main_marts.fct_trial_site"
    ) == [(14,)]
    assert (
        _rows(
            fixture_project_root,
            "select state_normalized from main_marts.fct_trial_site "
            "where not regexp_matches(state_normalized, '^[A-Z]{2}$')",
        )
        == []
    )
    assert _rows(
        fixture_project_root,
        "select count(*) from main_marts.fct_trial_site where facility_normalized in "
        "('charite memory clinic', 'toronto memory program')",
    ) == [(0,)]


def test_bridge_trial_condition_taxonomy_groups(fixture_project_root: Path) -> None:
    assert _rows(
        fixture_project_root,
        "select count(*) from main_marts.bridge_trial_condition",
    ) == [(12,)]
    groups = {
        r[0]
        for r in _rows(
            fixture_project_root,
            "select distinct condition_group from main_marts.bridge_trial_condition",
        )
    }
    assert groups == {
        "alzheimers_disease",
        "cognitive_impairment_other",
        "frontotemporal_dementia",
        "lewy_body_dementia",
        "mild_cognitive_impairment",
        "non_dementia_other",
    }


def test_mart_feasibility_priority_queue_shape(fixture_project_root: Path) -> None:
    assert _rows(
        fixture_project_root,
        "select count(*) from main_marts.mart_feasibility_priority_queue",
    ) == [(6,)]
    assert _rows(
        fixture_project_root,
        "select count(*) from main_marts.mart_feasibility_priority_queue "
        "where feasibility_review_priority_score < 0 "
        "or feasibility_review_priority_score > 1",
    ) == [(0,)]


def test_mart_data_reliability_reconciles(fixture_project_root: Path) -> None:
    assert _rows(
        fixture_project_root,
        "select status, manifest_record_count, trial_row_count, "
        "manifest_reconciled_flag, unique_nct_flag "
        f"from main_marts.mart_data_reliability where ingestion_run_id = '{FIXTURE_RUN_ID}'",
    ) == [("success", 10, 10, True, True)]
```

- [ ] **Step 2: Run the module to verify**

Run: `uv run pytest tests/test_dbt_fixture_build.py -v`
Expected: 7 passed.

- [ ] **Step 3: Lint, type-check, full suite**

Run: `uv run ruff check src tests dashboard && uv run ruff format --check src tests dashboard && uv run mypy && uv run pytest`
Expected: clean; `73 passed, 8 skipped`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_dbt_fixture_build.py
git commit -m "test(dbt): assert mart grains and shapes on fixture warehouse"
```

---

### Task 6: Contracts on gold marts

**Files:**
- Modify: `dbt_clinical_trials/models/marts/_marts.yml` (full replacement below)
- Modify: `tests/test_dbt_fixture_build.py` (append the contract test)
- Modify: `.github/workflows/ci.yml` (ratchet the coverage floor if earned)
- Modify: `pyproject.toml` (only if the ratchet fires)

**Interfaces:**
- Consumes: the 15 marts models' physical types as built by dbt-duckdb from the fixture (declared `data_type` values below were read via `DESCRIBE` from the fixture-built warehouse and verified by a full green dbt build with contracts on).
- Produces: `contract: {enforced: true}` on every marts model — schema drift in marts now fails `dbt build`.

- [ ] **Step 1: Replace `dbt_clinical_trials/models/marts/_marts.yml`**

Replace the file's entire content with exactly:

```yaml
version: 2

models:
  - name: dim_trial
    description: One row per NCT ID (current record from latest snapshot).
    contract:
      enforced: true
    columns:
      - name: trial_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: nct_id
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: registry_url
        data_type: VARCHAR
        description: Public ClinicalTrials.gov record URL derived from the NCT ID.
        tests: [not_null]
      - name: current_overall_status
        data_type: VARCHAR
        tests: [not_null]
      - name: current_brief_title
        data_type: VARCHAR
      - name: current_phase
        data_type: VARCHAR
      - name: current_study_type
        data_type: VARCHAR
      - name: current_lead_sponsor
        data_type: VARCHAR
      - name: current_lead_sponsor_normalized
        data_type: VARCHAR
      - name: start_date
        data_type: DATE
      - name: primary_completion_date
        data_type: DATE
      - name: completion_date
        data_type: DATE
      - name: study_first_post_date
        data_type: DATE
      - name: enrollment_count
        data_type: INTEGER
      - name: enrollment_type
        data_type: VARCHAR
      - name: current_has_results_flag
        data_type: BOOLEAN
      - name: record_quality_flag
        data_type: VARCHAR
      - name: first_seen_snapshot_date
        data_type: DATE
      - name: latest_seen_snapshot_date
        data_type: DATE
      - name: active_in_latest_snapshot_flag
        data_type: BOOLEAN

  - name: dim_condition
    contract:
      enforced: true
    columns:
      - name: condition_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: condition_normalized
        data_type: VARCHAR
      - name: condition_display_name
        data_type: VARCHAR
      - name: condition_group
        data_type: VARCHAR
      - name: dementia_relevance_flag
        data_type: BOOLEAN
      - name: mapping_confidence
        data_type: VARCHAR
      - name: trial_count
        data_type: BIGINT

  - name: dim_sponsor
    contract:
      enforced: true
    columns:
      - name: sponsor_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: sponsor_normalized
        data_type: VARCHAR
      - name: sponsor_display_name
        data_type: VARCHAR
      - name: sponsor_class
        data_type: VARCHAR
      - name: trial_count
        data_type: BIGINT
      - name: lead_sponsor_trial_count
        data_type: BIGINT

  - name: dim_geography
    contract:
      enforced: true
    columns:
      - name: geography_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: state_code
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: geo_level
        data_type: VARCHAR
      - name: country
        data_type: VARCHAR
      - name: county_fips
        data_type: VARCHAR
      - name: metro_area
        data_type: VARCHAR
      - name: trial_count
        data_type: BIGINT
      - name: listed_site_count
        data_type: BIGINT

  - name: dim_date
    contract:
      enforced: true
    columns:
      - name: date_day
        data_type: DATE
        tests: [not_null, unique]
      - name: year
        data_type: BIGINT
      - name: month
        data_type: BIGINT
      - name: quarter
        data_type: BIGINT
      - name: month_start_date
        data_type: DATE
      - name: quarter_start_date
        data_type: DATE
      - name: year_month
        data_type: VARCHAR
      - name: day_name
        data_type: VARCHAR
      - name: is_weekend
        data_type: BOOLEAN

  - name: fct_trial_snapshot
    description: One row per NCT ID per complete snapshot date.
    contract:
      enforced: true
    columns:
      - name: snapshot_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: trial_key
        data_type: VARCHAR
        tests:
          - not_null
          - relationships:
              to: ref('dim_trial')
              field: trial_key
      - name: nct_id
        data_type: VARCHAR
        tests: [not_null]
      - name: snapshot_date
        data_type: DATE
        tests: [not_null]
      - name: ingestion_run_id
        data_type: VARCHAR
      - name: snapshot_timestamp_utc
        data_type: TIMESTAMP
      - name: overall_status
        data_type: VARCHAR
      - name: previous_status
        data_type: VARCHAR
      - name: status_changed_from_previous_snapshot_flag
        data_type: BOOLEAN
      - name: entered_recruiting_flag
        data_type: BOOLEAN
      - name: left_recruiting_flag
        data_type: BOOLEAN
      - name: phase_normalized
        data_type: VARCHAR
      - name: study_type
        data_type: VARCHAR
      - name: enrollment_count
        data_type: INTEGER
      - name: lead_sponsor_name
        data_type: VARCHAR
      - name: lead_sponsor_normalized
        data_type: VARCHAR
      - name: has_results_flag
        data_type: BOOLEAN
      - name: study_first_post_date
        data_type: DATE
      - name: record_quality_flag
        data_type: VARCHAR
      - name: first_seen_snapshot_date
        data_type: DATE
      - name: days_since_first_seen
        data_type: BIGINT
      - name: condition_group_count
        data_type: BIGINT
      - name: site_count_us
        data_type: BIGINT
      - name: record_hash
        data_type: VARCHAR
      - name: current_record_flag
        data_type: BOOLEAN

  - name: fct_trial_site
    description: One row per trial x U.S. facility x snapshot date.
    contract:
      enforced: true
    columns:
      - name: trial_site_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: trial_key
        data_type: VARCHAR
        tests:
          - not_null
          - relationships:
              to: ref('dim_trial')
              field: trial_key
      - name: state_normalized
        data_type: VARCHAR
        tests: [not_null]
      - name: site_key
        data_type: VARCHAR
      - name: nct_id
        data_type: VARCHAR
      - name: ingestion_run_id
        data_type: VARCHAR
      - name: snapshot_date
        data_type: DATE
      - name: facility_name
        data_type: VARCHAR
      - name: facility_normalized
        data_type: VARCHAR
      - name: city
        data_type: VARCHAR
      - name: city_normalized
        data_type: VARCHAR
      - name: zip_code
        data_type: VARCHAR
      - name: location_status
        data_type: VARCHAR
      - name: trial_overall_status
        data_type: VARCHAR
      - name: phase_normalized
        data_type: VARCHAR
      - name: lead_sponsor_normalized
        data_type: VARCHAR

  - name: bridge_trial_condition
    contract:
      enforced: true
    columns:
      - name: trial_condition_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: trial_key
        data_type: VARCHAR
        tests:
          - not_null
          - relationships:
              to: ref('dim_trial')
              field: trial_key
      - name: condition_group
        data_type: VARCHAR
        tests: [not_null]
      - name: nct_id
        data_type: VARCHAR
      - name: dementia_relevance_flag
        data_type: BOOLEAN
      - name: mapping_confidence
        data_type: VARCHAR
      - name: source_condition_count
        data_type: BIGINT

  - name: bridge_trial_sponsor
    contract:
      enforced: true
    columns:
      - name: trial_sponsor_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: trial_key
        data_type: VARCHAR
        tests:
          - not_null
          - relationships:
              to: ref('dim_trial')
              field: trial_key
      - name: sponsor_key
        data_type: VARCHAR
      - name: nct_id
        data_type: VARCHAR
      - name: sponsor_name
        data_type: VARCHAR
      - name: sponsor_normalized
        data_type: VARCHAR
      - name: sponsor_role
        data_type: VARCHAR
      - name: sponsor_class
        data_type: VARCHAR
      - name: lead_sponsor_flag
        data_type: BOOLEAN

  - name: mart_trial_activity
    description: >
      Segment activity per snapshot. Counts are registry listings,
      not patient availability.
    contract:
      enforced: true
    columns:
      - name: trial_count
        data_type: BIGINT
        tests: [not_null]
      - name: snapshot_date
        data_type: DATE
      - name: condition_group
        data_type: VARCHAR
      - name: state_normalized
        data_type: VARCHAR
      - name: phase_normalized
        data_type: VARCHAR
      - name: overall_status
        data_type: VARCHAR
      - name: sponsor_count
        data_type: BIGINT
      - name: listed_site_count
        data_type: HUGEINT
      - name: entered_recruiting_count
        data_type: BIGINT
      - name: left_recruiting_count
        data_type: BIGINT
      - name: dementia_relevant_trial_count
        data_type: BIGINT
      - name: flagged_record_count
        data_type: BIGINT

  - name: mart_recruiting_competition
    description: >
      Potential competition signal per recruiting segment. Not a
      recruitment forecast.
    contract:
      enforced: true
    columns:
      - name: recruiting_trial_count
        data_type: BIGINT
        tests: [not_null]
      - name: competition_signal_band
        data_type: VARCHAR
        tests:
          - not_null
          - accepted_values:
              values: ['low', 'moderate', 'elevated']
      - name: snapshot_date
        data_type: DATE
      - name: condition_group
        data_type: VARCHAR
      - name: state_normalized
        data_type: VARCHAR
      - name: phase_normalized
        data_type: VARCHAR
      - name: listed_site_count
        data_type: HUGEINT
      - name: entered_recruiting_count
        data_type: BIGINT
      - name: newly_posted_90d_proxy
        data_type: BIGINT
      - name: new_recruiting_30d
        data_type: HUGEINT
      - name: new_recruiting_90d
        data_type: HUGEINT
      - name: recruiting_count_90d_baseline
        data_type: BIGINT
      - name: recruiting_growth_90d
        data_type: DOUBLE
      - name: sponsor_count
        data_type: BIGINT
      - name: top_sponsor_share
        data_type: DOUBLE
      - name: sponsor_hhi
        data_type: DOUBLE
      - name: density_percentile
        data_type: DOUBLE

  - name: mart_site_overlap
    contract:
      enforced: true
    columns:
      - name: facility_normalized
        data_type: VARCHAR
        tests: [not_null]
      - name: listed_trial_count
        data_type: BIGINT
        tests: [not_null]
      - name: snapshot_date
        data_type: DATE
      - name: city_normalized
        data_type: VARCHAR
      - name: state_normalized
        data_type: VARCHAR
      - name: facility_name
        data_type: VARCHAR
      - name: city
        data_type: VARCHAR
      - name: recruiting_trial_count
        data_type: BIGINT
      - name: sponsor_count
        data_type: BIGINT
      - name: phase_mix
        data_type: VARCHAR
      - name: repeated_site_participation_flag
        data_type: BOOLEAN

  - name: mart_condition_geography_trends
    contract:
      enforced: true
    columns:
      - name: activity_month
        data_type: TIMESTAMP
        tests: [not_null]
      - name: condition_group
        data_type: VARCHAR
        tests: [not_null]
      - name: state_normalized
        data_type: VARCHAR
      - name: trial_count
        data_type: BIGINT
      - name: recruiting_trial_count
        data_type: BIGINT
      - name: newly_posted_in_month_proxy
        data_type: BIGINT
      - name: sponsor_count
        data_type: BIGINT
      - name: recruiting_trial_count_3m_avg
        data_type: DOUBLE
      - name: recruiting_count_3m_baseline
        data_type: BIGINT
      - name: recruiting_growth_3m
        data_type: DOUBLE

  - name: mart_data_reliability
    description: One row per ingestion run with reconciliation shares.
    contract:
      enforced: true
    columns:
      - name: ingestion_run_id
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: snapshot_date
        data_type: DATE
      - name: started_at_utc
        data_type: TIMESTAMP
      - name: condition
        data_type: VARCHAR
      - name: mode
        data_type: VARCHAR
      - name: status
        data_type: VARCHAR
      - name: page_count
        data_type: INTEGER
      - name: manifest_record_count
        data_type: INTEGER
      - name: total_count_reported
        data_type: INTEGER
      - name: quarantined_record_count
        data_type: INTEGER
      - name: trial_row_count
        data_type: BIGINT
      - name: distinct_trial_count
        data_type: BIGINT
      - name: manifest_reconciled_flag
        data_type: BOOLEAN
      - name: unique_nct_flag
        data_type: BOOLEAN
      - name: flagged_record_count
        data_type: BIGINT
      - name: flagged_record_share
        data_type: DOUBLE
      - name: missing_enrollment_share
        data_type: DOUBLE
      - name: missing_start_date_share
        data_type: DOUBLE
      - name: missing_lead_sponsor_share
        data_type: DOUBLE
      - name: location_row_count
        data_type: BIGINT
      - name: usable_location_count
        data_type: BIGINT
      - name: usable_location_share
        data_type: DOUBLE
      - name: condition_row_count
        data_type: BIGINT
      - name: low_confidence_condition_count
        data_type: BIGINT
      - name: low_confidence_condition_share
        data_type: DOUBLE
      - name: error
        data_type: INTEGER

  - name: mart_feasibility_priority_queue
    description: >
      Ranked segments for human feasibility review. Triage signal from
      public registry listings; not a recruitment forecast.
    contract:
      enforced: true
    columns:
      - name: priority_queue_key
        data_type: VARCHAR
        tests: [not_null, unique]
      - name: feasibility_review_priority_score
        data_type: DOUBLE
        tests: [not_null]
      - name: priority_band
        data_type: VARCHAR
        tests:
          - not_null
          - accepted_values:
              values: ['watch', 'review', 'priority_review']
      - name: priority_explanation
        data_type: VARCHAR
        tests: [not_null]
      - name: snapshot_date
        data_type: DATE
      - name: condition_group
        data_type: VARCHAR
      - name: state_normalized
        data_type: VARCHAR
      - name: phase_normalized
        data_type: VARCHAR
      - name: priority_rank
        data_type: BIGINT
      - name: recruiting_trial_count
        data_type: BIGINT
      - name: listed_site_count
        data_type: HUGEINT
      - name: new_recruiting_90d
        data_type: HUGEINT
      - name: newly_posted_90d_proxy
        data_type: BIGINT
      - name: has_multi_snapshot_history
        data_type: BOOLEAN
      - name: recent_growth_input
        data_type: HUGEINT
      - name: growth_uses_registry_proxy_flag
        data_type: BOOLEAN
      - name: sponsor_count
        data_type: BIGINT
      - name: top_sponsor_share
        data_type: DOUBLE
      - name: sponsor_hhi
        data_type: DOUBLE
      - name: competition_signal_band
        data_type: VARCHAR
      - name: site_overlap_share
        data_type: DOUBLE
      - name: record_quality_ok_share
        data_type: DOUBLE
      - name: data_confidence_share
        data_type: DOUBLE
      - name: normalized_recruiting_trial_count
        data_type: DOUBLE
      - name: normalized_recent_recruiting_growth
        data_type: DOUBLE
      - name: normalized_sponsor_concentration
        data_type: DOUBLE
      - name: normalized_site_overlap
        data_type: DOUBLE
      - name: normalized_data_confidence_adjustment
        data_type: DOUBLE
      - name: interpretation_note
        data_type: VARCHAR
```

- [ ] **Step 2: Append the contract-enforcement test**

Append to `tests/test_dbt_fixture_build.py` (add `json` to imports):

```python
def test_marts_contracts_enforced(fixture_project_root: Path) -> None:
    manifest = json.loads(
        (fixture_project_root / "dbt_target/manifest.json").read_text(encoding="utf-8")
    )
    marts = {
        node["name"]: node
        for node in manifest["nodes"].values()
        if node["resource_type"] == "model"
        and node["original_file_path"].startswith("models/marts/")
    }
    assert len(marts) == 15
    for name, node in marts.items():
        assert node["contract"]["enforced"] is True, name
        assert {c["name"] for c in node["columns"].values()}, name
```

- [ ] **Step 3: Run the module to verify**

Run: `uv run pytest tests/test_dbt_fixture_build.py -v`
Expected: 8 passed — a contract mismatch (wrong type, missing/extra column) makes dbt build itself fail loudly, so this test cycle is the real gate.

- [ ] **Step 4: Lint, type-check, full suite**

Run: `uv run ruff check src tests dashboard && uv run ruff format --check src tests dashboard && uv run mypy && uv run pytest`
Expected: clean; `74 passed, 8 skipped`.

- [ ] **Step 5: Ratchet the coverage floor if earned**

Run:

```bash
uv run pytest --cov=src --cov-report=term-missing 2>&1 | tail -3
```

If TOTAL ≥ 71.0, change `--cov-fail-under=70` to `--cov-fail-under=71` in `.github/workflows/ci.yml` and verify `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=71` passes; if TOTAL < 71.0, leave the floor at 70 and note the measured value in the commit body.

- [ ] **Step 6: Commit**

```bash
git add dbt_clinical_trials/models/marts/_marts.yml tests/test_dbt_fixture_build.py .github/workflows/ci.yml pyproject.toml
git commit -m "feat(dbt): enforce contracts on gold marts"
```

---

## Completion Checklist for Phase 2

- `uv run mypy` strict-clean on the four scoped packages; CI enforces it.
- CI runs ruff check + format check, mypy, and pytest with a `--cov-fail-under` floor; pre-commit runs the same gates locally on every commit.
- `uv run pytest` runs the fixture snapshot through the real 106-node dbt build (seeds, 30 models, 73 tests) with zero network.
- Mart grains/shapes asserted against the fixture warehouse; all 15 marts models carry enforced contracts.
- Known gap recorded per spec: `src/transform` excluded from mypy (pandas-heavy annotation churn deferred to its own pass).
