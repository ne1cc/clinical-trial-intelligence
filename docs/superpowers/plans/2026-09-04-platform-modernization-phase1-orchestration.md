# Platform Modernization — Phase 1: Dagster Orchestration Core (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing ingest → transform → dbt pipeline as Dagster software-defined assets with blocking quality checks and a weekly schedule, runnable via `dagster dev` locally and `dagster job execute` headlessly.

**Architecture:** New `src/orchestration/` package defines assets that delegate to the existing pipeline functions (`run_ingestion`, `run_transform`, dbt CLI, `run_reconciliation`). Assets do not reimplement pipeline logic. Checks run against on-disk state and fail loudly; a blocking check failure prevents downstream materialization. Configuration flows through the existing env-driven `load_config()` (`CTI_PROJECT_ROOT` / `CTI_CONFIG_PATH`), which makes every test hermetic via a temp project root.

**Tech Stack:** Python 3.13 (floor 3.11), uv dependency groups, Dagster + dagster-dbt, dbt-core 1.12 / dbt-duckdb 1.10.1, pytest, ruff (line length 100).

**Spec:** `docs/superpowers/specs/2026-09-04-platform-modernization-design.md` (this plan implements its "Week 1 — Orchestration core" milestone; Plans 2–4 will cover CI depth/contracts, scheduling + GCS lake, and BigQuery portability, and will be written when their phase starts).

## Global Constraints

- Python floor: `requires-python = ">=3.11"` (unchanged).
- Dependency management exclusively via `uv` and dependency groups in `pyproject.toml`; never `pip install`.
- Dagster packages live in a uv group named `orchestration` — never in main `dependencies` (the Fly serving image must stay lean).
- Ruff: line length 100, rules `E,F,I,W,UP,B`; all new code must pass `uv run ruff check src tests`.
- Every new function is fully type-annotated (mypy strict lands in Phase 2; do not create debt now).
- Tests never hit the real ClinicalTrials.gov API and never read/write outside `tmp_path` (via `CTI_PROJECT_ROOT`).
- `data/` is git-ignored and must never be staged.
- Conventional Commits for every commit (`feat(orchestration): ...`).
- The existing 54 pytest tests must stay green after every task (`uv run pytest`).
- Work happens in the worktree `.worktrees/feat/platform-modernization` on branch `feat/platform-modernization`.

## File Structure (Phase 1)

| File | Responsibility |
|---|---|
| `pyproject.toml` | Add `orchestration` dependency group |
| `src/orchestration/__init__.py` | Package marker |
| `src/orchestration/assets/__init__.py` | Package marker |
| `src/orchestration/assets/bronze.py` | Asset `ctg_raw_pages` wrapping `run_ingestion` |
| `src/orchestration/assets/silver.py` | Asset `silver_entities` wrapping `run_transform` |
| `src/orchestration/assets/dbt_assets.py` | dbt models as Dagster assets via `dagster-dbt` |
| `src/orchestration/checks.py` | Blocking asset checks: manifest integrity, cross-layer reconciliation |
| `src/orchestration/definitions.py` | `Definitions` wiring assets, checks, weekly job + schedule |
| `tests/conftest.py` | Session fixture that generates the dbt `manifest.json` |
| `tests/test_orchestration_assets.py` | Asset + check behavior tests |
| `tests/test_orchestration_definitions.py` | Definitions load / job / schedule tests |

**Deliberate deviation from the spec, recorded:** the spec's `resources.py` (CTG client resource) is deferred — `run_ingestion` already encapsulates client, retries, and pagination, so a resource would be an empty wrapper. The GCS resource the spec also lists belongs to Phase 3 and will be introduced there in `src/orchestration/resources.py`.

---

### Task 1: Add the `orchestration` dependency group

**Files:**
- Modify: `pyproject.toml` (`[dependency-groups]` block, currently lines 25–31)

**Interfaces:**
- Consumes: nothing
- Produces: importable `dagster`, `dagster_webserver` CLI, `dagster_dbt` package for all later tasks

- [ ] **Step 1: Add the dependency group**

Run:

```bash
uv add --group orchestration dagster dagster-webserver dagster-dbt
```

This appends the group to `pyproject.toml` and updates `uv.lock`. Verify the resulting `pyproject.toml` block looks like:

```toml
[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-cov>=5.0",
    "requests-mock>=1.12",
    "ruff>=0.5",
]
orchestration = [
    "dagster>=…",          # uv fills exact floors — leave whatever uv writes
    "dagster-webserver>=…",
    "dagster-dbt>=…",
]
```

- [ ] **Step 2: Verify the sync and CLIs**

Run:

```bash
uv sync --all-groups
uv run dagster --version
uv run python -c "import dagster_dbt; print(dagster_dbt.__version__)"
```

Expected: versions print without error (dagster 1.x, dagster-dbt 0.3x+).

- [ ] **Step 3: Run the existing suite**

Run: `uv run pytest`
Expected: `54 passed, 8 skipped` (no regressions).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(orchestration): add dagster dependency group"
```

---

### Task 2: Bronze asset `ctg_raw_pages`

**Files:**
- Create: `src/orchestration/__init__.py` (empty)
- Create: `src/orchestration/assets/__init__.py` (empty)
- Create: `src/orchestration/assets/bronze.py`
- Test: `tests/test_orchestration_assets.py`
- Test: `tests/conftest.py` (create — starts with a shared config helper needed by all orchestration tests)

**Interfaces:**
- Consumes: `src.ingest.extract_studies.run_ingestion(condition: str | None, full_refresh: bool, max_pages: int | None) -> IngestionManifest`; `src.ingest.snapshot_manifest.IngestionManifest` (pydantic model: `ingestion_run_id: str, query_hash: str, endpoint: str, params: dict[str, str], status: str, started_at_utc: datetime, page_count: int, record_count: int, total_count_reported: int | None, …`); `src.ingest.snapshot_manifest.write_manifest(manifests_dir: Path, manifest) -> Path`; `src.config.load_config(config_path=None) -> ProjectConfig`; `src.utils.dates.utc_now() -> datetime`.
- Produces: Dagster asset named `ctg_raw_pages`; Dagster config schema `IngestParams` (fields `condition: str | None = None`, `full_refresh: bool = False`, `max_pages: int | None = None`); module-level import `from src.ingest.extract_studies import run_ingestion` in `src/orchestration/assets/bronze.py` (imported at module top — later tests monkeypatch `src.orchestration.assets.bronze.run_ingestion`).

- [ ] **Step 1: Create the test helper config fixture in `tests/conftest.py`**

Every orchestration test needs a temp project root with a minimal `config/project_config.yml`, because `load_config()` resolves relative paths against `project_root()` (which honors `CTI_PROJECT_ROOT`). Create `tests/conftest.py` with exactly:

```python
from pathlib import Path

import pytest

CONFIG_YAML = """
api:
  base_url: "https://clinicaltrials.gov/api/v2"
paths:
  bronze_api_responses: "data/bronze/api_responses"
  bronze_manifests: "data/bronze/manifests"
  silver: "data/silver"
  gold: "data/gold"
  duckdb: "data/warehouse/clinical_trials.duckdb"
  quarantine: "data/quarantine"
ingestion:
  mode_default: "incremental"
  reuse_window_hours: 24
scope:
  refresh_cadence: "weekly"
"""


@pytest.fixture
def project_root_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project_config.yml").write_text(CONFIG_YAML, encoding="utf-8")
    monkeypatch.setenv("CTI_PROJECT_ROOT", str(tmp_path))
    return tmp_path
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_orchestration_assets.py` with exactly:

```python
from dagster import materialize

from src.ingest.snapshot_manifest import IngestionManifest, write_manifest
from src.orchestration.assets.bronze import IngestParams, ctg_raw_pages
from src.utils.dates import utc_now


def _success_manifest() -> IngestionManifest:
    return IngestionManifest(
        ingestion_run_id="20260904T120000Z_abc12345",
        query_hash="hash123",
        endpoint="https://clinicaltrials.gov/api/v2/studies",
        params={"query.cond": "Alzheimer Disease"},
        status="success",
        started_at_utc=utc_now(),
        ended_at_utc=utc_now(),
        page_count=2,
        record_count=3,
        total_count_reported=3,
    )


def test_bronze_asset_writes_manifest_and_materializes(
    project_root_tmp, monkeypatch
) -> None:
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config

        cfg = load_config()
        write_manifest(cfg.paths.bronze_manifests, manifest)
        return manifest

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )
    result = materialize(
        assets=[ctg_raw_pages],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    assert result.success
    materializations = result.get_asset_materialization_events()
    assert len(materializations) == 1


def test_bronze_asset_raises_on_failed_run(project_root_tmp, monkeypatch) -> None:
    manifest = _success_manifest().model_copy(update={"status": "failed"})

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        return manifest

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )
    result = materialize(
        assets=[ctg_raw_pages],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
        raise_on_error=False,
    )
    assert not result.success
```

The block above is the entire test file for this task.

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_orchestration_assets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.orchestration'`.

- [ ] **Step 4: Create the package and the asset**

Create empty `src/orchestration/__init__.py` and `src/orchestration/assets/__init__.py`. Create `src/orchestration/assets/bronze.py` with exactly:

```python
"""Bronze asset: snapshot ClinicalTrials.gov studies into immutable raw pages."""

from dagster import AssetExecutionContext, Config, MaterializeResult, MetadataValue, asset

from src.ingest.extract_studies import run_ingestion


class IngestParams(Config):
    condition: str | None = None
    full_refresh: bool = False
    max_pages: int | None = None


@asset(
    name="ctg_raw_pages",
    description=(
        "Paginated snapshot of ClinicalTrials.gov API v2 studies written to bronze "
        "as raw JSON pages plus a signed ingestion manifest."
    ),
)
def ctg_raw_pages(
    context: AssetExecutionContext, params: IngestParams
) -> MaterializeResult:
    manifest = run_ingestion(
        condition=params.condition,
        full_refresh=params.full_refresh,
        max_pages=params.max_pages,
    )
    if manifest.status == "failed":
        raise RuntimeError(
            f"Ingestion run {manifest.ingestion_run_id} failed: {manifest.error}"
        )
    context.log.info(
        "Ingestion run {} status={} records={} pages={}",
        manifest.ingestion_run_id,
        manifest.status,
        manifest.record_count,
        manifest.page_count,
    )
    return MaterializeResult(
        metadata={
            "ingestion_run_id": manifest.ingestion_run_id,
            "status": manifest.status,
            "record_count": manifest.record_count,
            "page_count": manifest.page_count,
            "query_hash": manifest.query_hash,
            "params": MetadataValue.json(manifest.params),
        }
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestration_assets.py -v`
Expected: 2 passed.

- [ ] **Step 6: Lint and full suite**

Run: `uv run ruff check src tests && uv run pytest`
Expected: no lint errors; `56 passed, 8 skipped`.

- [ ] **Step 7: Commit**

```bash
git add src/orchestration tests/conftest.py tests/test_orchestration_assets.py
git commit -m "feat(orchestration): add bronze ctg_raw_pages asset wrapping run_ingestion"
```

---

### Task 3: Blocking manifest-integrity check

**Files:**
- Create: `src/orchestration/checks.py`
- Modify: `tests/test_orchestration_assets.py` (append tests)

**Interfaces:**
- Consumes: `src.config.load_config() -> ProjectConfig` (env-driven); `src.ingest.snapshot_manifest.load_manifests(manifests_dir: Path) -> list[IngestionManifest]`; asset name `"ctg_raw_pages"` (Task 2).
- Produces: Dagster asset check `manifest_integrity` on asset `ctg_raw_pages`, `blocking=True` — later tasks rely on it being blocking so a failed bronze check stops silver. Check passes iff the latest `success` manifest exists with `record_count > 0`, `page_count > 0`, and (`total_count_reported is None` or `record_count == total_count_reported`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_orchestration_assets.py` (add only one new import line, shown here; `materialize`, `write_manifest`, `_success_manifest`, `ctg_raw_pages`, and `IngestParams` already exist in the file from Task 2):

```python
from src.orchestration.checks import manifest_integrity


def test_manifest_integrity_passes_on_success_run(project_root_tmp, monkeypatch) -> None:
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config

        write_manifest(load_config().paths.bronze_manifests, manifest)
        return manifest

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )
    result = materialize(
        assets=[ctg_raw_pages],
        asset_checks=[manifest_integrity],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    check = result.get_check_result("manifest_integrity")
    assert check is not None and check.passed


def test_manifest_integrity_fails_when_counts_disagree(
    project_root_tmp, monkeypatch
) -> None:
    manifest = _success_manifest().model_copy(
        update={"record_count": 3, "total_count_reported": 999}
    )

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config

        write_manifest(load_config().paths.bronze_manifests, manifest)
        return manifest

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )
    result = materialize(
        assets=[ctg_raw_pages],
        asset_checks=[manifest_integrity],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    check = result.get_check_result("manifest_integrity")
    assert check is not None and not check.passed


def test_manifest_integrity_fails_with_no_success_runs(
    project_root_tmp, monkeypatch
) -> None:
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        return manifest  # returns, but never writes a manifest file

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )
    result = materialize(
        assets=[ctg_raw_pages],
        asset_checks=[manifest_integrity],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    check = result.get_check_result("manifest_integrity")
    assert check is not None and not check.passed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_orchestration_assets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.orchestration.checks'`.

- [ ] **Step 3: Implement the check**

Create `src/orchestration/checks.py` with exactly:

```python
"""Blocking asset checks that gate the publish path on data quality."""

from dagster import AssetCheckResult, MetadataValue, asset_check

from src.config import load_config
from src.ingest.snapshot_manifest import load_manifests


@asset_check(asset="ctg_raw_pages", name="manifest_integrity", blocking=True)
def manifest_integrity() -> AssetCheckResult:
    cfg = load_config()
    manifests = load_manifests(cfg.paths.bronze_manifests)
    success_runs = [m for m in manifests if m.status == "success"]
    if not success_runs:
        return AssetCheckResult(
            passed=False,
            metadata={
                "reason": "no_success_runs",
                "manifests_seen": len(manifests),
            },
        )
    latest = max(success_runs, key=lambda m: m.ingestion_run_id)
    counts_agree = (
        latest.total_count_reported is None
        or latest.record_count == latest.total_count_reported
    )
    passed = latest.record_count > 0 and latest.page_count > 0 and counts_agree
    return AssetCheckResult(
        passed=passed,
        metadata={
            "ingestion_run_id": latest.ingestion_run_id,
            "record_count": latest.record_count,
            "total_count_reported": latest.total_count_reported,
            "page_count": latest.page_count,
            "details": MetadataValue.json(
                {
                    "record_count_positive": latest.record_count > 0,
                    "page_count_positive": latest.page_count > 0,
                    "counts_agree": counts_agree,
                }
            ),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestration_assets.py -v`
Expected: 5 passed.

- [ ] **Step 5: Lint and full suite**

Run: `uv run ruff check src tests && uv run pytest`
Expected: clean; `59 passed, 8 skipped`.

- [ ] **Step 6: Commit**

```bash
git add src/orchestration/checks.py tests/test_orchestration_assets.py
git commit -m "feat(orchestration): add blocking manifest integrity asset check"
```

---

### Task 4: Silver asset `silver_entities` with reconciliation check

**Files:**
- Create: `src/orchestration/assets/silver.py`
- Modify: `tests/test_orchestration_assets.py` (append tests)

**Interfaces:**
- Consumes: `src.transform.build_silver_entities.run_transform(run_id: str | None, force: bool) -> list[str]` (returns processed run IDs); `src.quality.reconciliation.run_reconciliation(cfg: ProjectConfig | None) -> list[ReconciliationCheck]` where `ReconciliationCheck` is a dataclass with fields `check: str, run_id: str | None, expected: Any, actual: Any, passed: bool, note: str`; asset `ctg_raw_pages` (dependency target); check `manifest_integrity` (already blocking upstream).
- Produces: Dagster asset `silver_entities` with `deps=["ctg_raw_pages"]`; blocking asset check `cross_layer_reconciliation` on `silver_entities` — Plan 2/3 rely on both names when wiring the publish-on-green job.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_orchestration_assets.py` (new imports only — `materialize`, `ctg_raw_pages`, `IngestParams`, `IngestionManifest`, `write_manifest`, `_success_manifest`, and `utc_now` already exist in the file from Tasks 2–3):

```python
import duckdb
import pandas as pd

from src.orchestration.assets.silver import silver_entities
from src.orchestration.checks import cross_layer_reconciliation


def _patch_quiet_bronze(monkeypatch) -> None:
    """Bronze runs but writes nothing: seeded state fully controls the check."""
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        return manifest

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )


def _seed_reconcilable_state() -> None:
    """Fabricate one consistent bronze→silver→warehouse chain under the temp root."""
    from src.config import load_config
    from src.ingest.snapshot_manifest import write_manifest

    cfg = load_config()
    run_id = "20260904T120000Z_abc12345"
    write_manifest(
        cfg.paths.bronze_manifests,
        IngestionManifest(
            ingestion_run_id=run_id,
            query_hash="hash123",
            endpoint="https://clinicaltrials.gov/api/v2/studies",
            params={"query.cond": "Alzheimer Disease"},
            status="success",
            started_at_utc=utc_now(),
            ended_at_utc=utc_now(),
            page_count=1,
            record_count=1,
            total_count_reported=1,
        ),
    )
    silver_dir = cfg.paths.silver / "silver_trials"
    silver_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"nct_id": "NCT00000001", "brief_title": "T"}]).to_parquet(
        silver_dir / f"run_id={run_id}.parquet", index=False
    )
    cfg.paths.duckdb.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(cfg.paths.duckdb))
    con.execute("create schema main_marts")
    con.execute(
        "create table main_marts.dim_trial as select 'NCT00000001' as nct_id"
    )
    con.execute(
        "create table main_marts.fct_trial_snapshot as select false as current_record_flag"
    )
    con.close()


def test_silver_asset_materializes_processed_runs(
    project_root_tmp, monkeypatch
) -> None:
    _seed_reconcilable_state()
    _patch_quiet_bronze(monkeypatch)

    def fake_run_transform(run_id=None, force=False):
        return ["20260904T120000Z_abc12345"]

    monkeypatch.setattr(
        "src.orchestration.assets.silver.run_transform", fake_run_transform
    )
    result = materialize(
        assets=[ctg_raw_pages, silver_entities],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    assert result.success
    assert len(result.get_asset_materialization_events()) == 2


def test_reconciliation_check_passes_on_consistent_state(
    project_root_tmp, monkeypatch
) -> None:
    _seed_reconcilable_state()
    _patch_quiet_bronze(monkeypatch)
    result = materialize(
        assets=[ctg_raw_pages, silver_entities],
        asset_checks=[cross_layer_reconciliation],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    check = result.get_check_result("cross_layer_reconciliation")
    assert check is not None and check.passed


def test_reconciliation_check_fails_when_silver_missing(
    project_root_tmp, monkeypatch
) -> None:
    _patch_quiet_bronze(monkeypatch)
    result = materialize(
        assets=[ctg_raw_pages, silver_entities],
        asset_checks=[cross_layer_reconciliation],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    check = result.get_check_result("cross_layer_reconciliation")
    assert check is not None and not check.passed
```

Rationale for the quiet-bronze helper: every test materializes both assets so the `deps=["ctg_raw_pages"]` edge is always satisfied, and bronze never touches the network or the filesystem — the seeded state alone determines what the reconciliation check sees. `test_reconciliation_check_fails_when_silver_missing` writes no manifest and no silver parquet, so the check must fail on `success_runs_exist`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_orchestration_assets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.orchestration.assets.silver'`.

- [ ] **Step 3: Implement the asset and the check**

Create `src/orchestration/assets/silver.py` with exactly:

```python
"""Silver asset: flatten bronze JSON runs into normalized Parquet entities."""

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from src.transform.build_silver_entities import run_transform


@asset(
    name="silver_entities",
    deps=["ctg_raw_pages"],
    description=(
        "Flattened, normalized silver Parquet entities for every completed bronze "
        "run not yet transformed."
    ),
)
def silver_entities(context: AssetExecutionContext) -> MaterializeResult:
    processed = run_transform(run_id=None, force=False)
    context.log.info("Transformed {} bronze run(s): {}", len(processed), processed)
    return MaterializeResult(
        metadata={
            "processed_runs": MetadataValue.json(processed),
            "processed_count": len(processed),
        }
    )
```

Append the reconciliation check to `src/orchestration/checks.py` (add to the
existing file; merge imports):

```python
from src.quality.reconciliation import run_reconciliation


@asset_check(asset="silver_entities", name="cross_layer_reconciliation", blocking=True)
def cross_layer_reconciliation() -> AssetCheckResult:
    checks = run_reconciliation()
    failed = [c for c in checks if not c.passed]
    return AssetCheckResult(
        passed=not failed,
        metadata={
            "total_checks": len(checks),
            "failed_checks": MetadataValue.json(
                [
                    {
                        "check": c.check,
                        "run_id": c.run_id,
                        "expected": str(c.expected),
                        "actual": str(c.actual),
                        "note": c.note,
                    }
                    for c in failed
                ]
            ),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestration_assets.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint and full suite**

Run: `uv run ruff check src tests && uv run pytest`
Expected: clean; `62 passed, 8 skipped`.

- [ ] **Step 6: Commit**

```bash
git add src/orchestration tests/test_orchestration_assets.py
git commit -m "feat(orchestration): add silver asset and blocking reconciliation check"
```

---

### Task 5: dbt models as Dagster assets

**Files:**
- Create: `src/orchestration/assets/dbt_assets.py`
- Modify: `tests/conftest.py` (append the session-scoped `dbt_manifest` fixture)

**Interfaces:**
- Consumes: dbt project `dbt_clinical_trials` (name `clinical_trials`, profile `clinical_trials`, duckdb target at `data/warehouse/clinical_trials.duckdb`); `dagster_dbt.DbtCliResource`, `dagster_dbt.dbt_assets`; dbt `target/manifest.json` generated by `dbt parse`.
- Produces: `@dbt_assets` collection `clinical_trials_dbt_assets` (one Dagster asset per dbt model — 30 models); Definitions resource key `dbt` of type `DbtCliResource` with `project_dir="dbt_clinical_trials"` — Task 6 wires these into `Definitions` by exact name.
- Constraint: `src/orchestration/assets/dbt_assets.py` reads `target/manifest.json` at import time, so it must only be imported after `dbt parse` has run (tests enforce this via the session fixture and lazy imports).

- [ ] **Step 1: Append the dbt manifest fixture to `tests/conftest.py`**

```python
import subprocess


@pytest.fixture(scope="session")
def dbt_manifest(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(__file__).resolve().parents[1]
    dbt_dir = root / "dbt_clinical_trials"
    if not (dbt_dir / "profiles.yml").exists():
        subprocess.run(
            ["cp", str(dbt_dir / "profiles.yml.example"), str(dbt_dir / "profiles.yml")],
            check=True,
        )
    if (dbt_dir / "packages.yml").exists():
        subprocess.run(
            ["uv", "run", "dbt", "deps", "--project-dir", str(dbt_dir), "--profiles-dir", str(dbt_dir)],
            cwd=root,
            check=True,
            capture_output=True,
        )
    subprocess.run(
        ["uv", "run", "dbt", "parse", "--project-dir", str(dbt_dir), "--profiles-dir", str(dbt_dir)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    manifest = dbt_dir / "target" / "manifest.json"
    assert manifest.exists(), "dbt parse did not produce target/manifest.json"
    return manifest
```

(`Path`, `pytest`, and `subprocess` merge into the import block at the top of
`conftest.py`; `Path` is already imported there from Task 2.)

- [ ] **Step 2: Write the failing test**

Create `tests/test_orchestration_definitions.py` with exactly:

```python
def test_dbt_assets_load_from_manifest(dbt_manifest) -> None:
    from src.orchestration.assets.dbt_assets import clinical_trials_dbt_assets

    specs = list(clinical_trials_dbt_assets.specs)
    assert len(specs) >= 25, f"expected ~30 dbt models, found {len(specs)}"


def test_dbt_asset_keys_use_model_names(dbt_manifest) -> None:
    from src.orchestration.assets.dbt_assets import clinical_trials_dbt_assets

    keys = {spec.key.to_user_string() for spec in clinical_trials_dbt_assets.specs}
    assert "dim_trial" in keys
    assert "fct_trial_snapshot" in keys
    assert "mart_feasibility_priority_queue" in keys
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_orchestration_definitions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.orchestration.assets.dbt_assets'`.

- [ ] **Step 4: Implement the dbt assets module**

Create `src/orchestration/assets/dbt_assets.py` with exactly:

```python
"""dbt models surfaced as individual Dagster assets via dagster-dbt."""

from dagster_dbt import DbtCliResource, dbt_assets

from src.utils.paths import project_root

DBT_PROJECT_DIR = project_root() / "dbt_clinical_trials"
DBT_MANIFEST_PATH = DBT_PROJECT_DIR / "target" / "manifest.json"


@dbt_assets(manifest=DBT_MANIFEST_PATH)
def clinical_trials_dbt_assets(context, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestration_definitions.py -v`
Expected: 2 passed (the session fixture runs `dbt deps` + `dbt parse` first; first run may take ~30s).

- [ ] **Step 6: Lint and full suite**

Run: `uv run ruff check src tests && uv run pytest`
Expected: clean; `64 passed, 8 skipped`.

- [ ] **Step 7: Commit**

```bash
git add src/orchestration/assets/dbt_assets.py tests/conftest.py tests/test_orchestration_definitions.py
git commit -m "feat(orchestration): surface dbt models as dagster assets via dagster-dbt"
```

---

### Task 6: Definitions — weekly job, schedule, resources

**Files:**
- Create: `src/orchestration/definitions.py`
- Modify: `tests/test_orchestration_definitions.py` (append tests)

**Interfaces:**
- Consumes: `ctg_raw_pages`, `IngestParams` (Task 2); `silver_entities` (Task 4); `clinical_trials_dbt_assets` (Task 5); `manifest_integrity`, `cross_layer_reconciliation` (Tasks 3–4); `DbtCliResource(project_dir="dbt_clinical_trials")`.
- Produces: `defs: Definitions` (the module-level object every consumer imports); job `weekly_refresh` selecting all assets; schedule `weekly_refresh_schedule` with cron `"0 13 * * 1"` (every Monday 13:00 UTC); resource key `dbt`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_orchestration_definitions.py`:

```python
def test_definitions_load_with_job_and_schedule(dbt_manifest) -> None:
    from src.orchestration.definitions import defs

    job = defs.get_job_def("weekly_refresh")
    assert job is not None
    selected = sorted(node.name for node in job.nodes)
    assert "ctg_raw_pages" in selected
    assert "silver_entities" in selected
    # The dbt collection is a multi-asset: ONE op node named after the function.
    assert "clinical_trials_dbt_assets" in selected


def test_schedule_targets_weekly_job(dbt_manifest) -> None:
    from src.orchestration.definitions import defs

    schedule = defs.get_schedule_def("weekly_refresh_schedule")
    assert schedule.cron_schedule == "0 13 * * 1"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_orchestration_definitions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.orchestration.definitions'`.

- [ ] **Step 3: Implement `definitions.py`**

Create `src/orchestration/definitions.py` with exactly:

```python
"""Dagster Definitions: the single import surface for dagster dev and CI."""

from dagster import AssetSelection, Definitions, ScheduleDefinition, define_asset_job
from dagster_dbt import DbtCliResource

from src.orchestration.assets.bronze import ctg_raw_pages
from src.orchestration.assets.dbt_assets import clinical_trials_dbt_assets
from src.orchestration.assets.silver import silver_entities
from src.orchestration.checks import cross_layer_reconciliation, manifest_integrity

weekly_refresh = define_asset_job(
    name="weekly_refresh",
    selection=AssetSelection.all(),
)

weekly_refresh_schedule = ScheduleDefinition(
    job=weekly_refresh,
    cron_schedule="0 13 * * 1",  # every Monday 13:00 UTC
    name="weekly_refresh_schedule",
)

defs = Definitions(
    assets=[ctg_raw_pages, silver_entities, clinical_trials_dbt_assets],
    asset_checks=[manifest_integrity, cross_layer_reconciliation],
    resources={
        "dbt": DbtCliResource(project_dir="dbt_clinical_trials"),
    },
    jobs=[weekly_refresh],
    schedules=[weekly_refresh_schedule],
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestration_definitions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Validate definitions through the Dagster CLI**

Run:

```bash
uv run dagster definitions validate -m src.orchestration.definitions
```

Expected: definitions validate successfully (exit 0). If the subcommand does not exist in the installed Dagster version, substitute:

```bash
uv run python -c "from src.orchestration.definitions import defs; print(defs.get_repository_def())"
```

and require a `RepositoryDefinition` to print.

- [ ] **Step 6: Lint and full suite**

Run: `uv run ruff check src tests && uv run pytest`
Expected: clean; `66 passed, 8 skipped`.

- [ ] **Step 7: Commit**

```bash
git add src/orchestration/definitions.py tests/test_orchestration_definitions.py
git commit -m "feat(orchestration): wire definitions with weekly refresh job and schedule"
```

---

### Task 7: End-to-end orchestration test and local-run docs

**Files:**
- Modify: `tests/test_orchestration_definitions.py` (append the integration test)
- Modify: `README.md` (add a "Run the orchestrator locally" subsection in the existing "How to run" area, after the "How to build the data-quality report" section)

**Interfaces:**
- Consumes: everything from Tasks 2–6; `materialize()` with the full asset+check set; `IngestionManifest`/`write_manifest` fakes.
- Produces: one integration test proving failure propagation (a failing bronze check blocks silver materialization); README instructions for `dagster dev` and `dagster job execute`.

- [ ] **Step 1: Write the failing propagation test**

Append to `tests/test_orchestration_definitions.py`:

```python
def test_failed_bronze_check_blocks_silver(project_root_tmp, monkeypatch) -> None:
    from dagster import materialize

    from src.ingest.snapshot_manifest import IngestionManifest
    from src.orchestration.assets.bronze import IngestParams, ctg_raw_pages
    from src.orchestration.assets.silver import silver_entities
    from src.orchestration.checks import cross_layer_reconciliation, manifest_integrity
    from src.utils.dates import utc_now

    bad = IngestionManifest(
        ingestion_run_id="20260904T120000Z_abc12345",
        query_hash="hash123",
        endpoint="https://clinicaltrials.gov/api/v2/studies",
        params={"query.cond": "Alzheimer Disease"},
        status="success",
        started_at_utc=utc_now(),
        ended_at_utc=utc_now(),
        page_count=1,
        record_count=5,
        total_count_reported=999,
    )

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config
        from src.ingest.snapshot_manifest import write_manifest

        write_manifest(load_config().paths.bronze_manifests, bad)
        return bad

    def fake_run_transform(run_id=None, force=False):
        raise AssertionError("silver must not run when the bronze check fails")

    monkeypatch.setattr(
        "src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion
    )
    monkeypatch.setattr(
        "src.orchestration.assets.silver.run_transform", fake_run_transform
    )
    result = materialize(
        assets=[ctg_raw_pages, silver_entities],
        asset_checks=[manifest_integrity, cross_layer_reconciliation],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    check = result.get_check_result("manifest_integrity")
    assert check is not None and not check.passed
    silver_materialized = any(
        e.asset_key is not None and e.asset_key.to_user_string() == "silver_entities"
        for e in result.get_asset_materialization_events()
    )
    assert not silver_materialized
```

- [ ] **Step 2: Run the test to verify it passes for the right reason**

Run: `uv run pytest tests/test_orchestration_definitions.py::test_failed_bronze_check_blocks_silver -v`
Expected: PASS. If it fails because `fake_run_transform` raised, the blocking semantics are not active — verify `blocking=True` on `manifest_integrity` before debugging anything else.

- [ ] **Step 3: Update the README**

In `README.md`, immediately after the section `## 14. How to build the data-quality report` (its code block ends with `make quality-report`), insert:

```markdown
## 14a. How to run the orchestrator locally

```bash
make dbt-deps                     # one-time: dbt packages
uv run dbt parse --project-dir dbt_clinical_trials --profiles-dir dbt_clinical_trials
uv run dagster dev -m src.orchestration.definitions
```

`dagster dev` opens the web UI at http://localhost:3000 showing the bronze→silver→gold
asset graph. Materialize assets manually from the UI, or execute the weekly job
headlessly:

```bash
uv run dagster job execute -m src.orchestration.definitions -j weekly_refresh
```

Headless execution hits the real ClinicalTrials.gov API; local `dagster dev` is for
inspection, manual materializations, and backfills.
```

(If the README's section numbering differs at edit time, anchor on the
`make quality-report` code block and insert after it, keeping the same style.)

- [ ] **Step 4: Full suite and lint**

Run: `uv run ruff check src tests dashboard && uv run pytest`
Expected: clean; `67 passed, 8 skipped`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_orchestration_definitions.py README.md
git commit -m "feat(orchestration): prove check blocking and document dagster dev workflow"
```

---

## Completion Checklist for Phase 1

- `uv run dagster dev -m src.orchestration.definitions` shows the asset graph with `ctg_raw_pages` → `silver_entities` → 30 dbt model assets.
- Both blocking checks appear in the UI and fail correctly on the hermetic negative tests.
- `weekly_refresh` job + Monday 13:00 UTC schedule exist and validate.
- All 67 pytest tests pass; ruff clean; nothing in `data/` staged.
- Manual smoke (optional, user-run): `uv run dagster job execute -m src.orchestration.definitions -j weekly_refresh` against the real API.
