"""Cross-layer reconciliation: bronze manifests vs silver Parquet vs warehouse.

Every complete (success) run must carry its trial count through each layer.
Bronze→silver allows only the drop the transform recorded on file — repeated
or NCT-less records — and treats an unrecorded shortfall as a failure.
Failures are reported, never silently corrected.

The checks are split by layer dependency: `bronze_silver_checks` needs only
bronze manifests and silver Parquet (usable before dbt builds the warehouse),
while `warehouse_checks` needs the DuckDB warehouse dbt produces. The public
composer `run_reconciliation` returns both.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import duckdb
from loguru import logger

from src.config import ProjectConfig, get_config
from src.ingest.snapshot_manifest import IngestionManifest, load_manifests
from src.transform.silver_stats import expected_trial_rows, load_transform_stats


@dataclass
class ReconciliationCheck:
    check: str
    run_id: str | None
    expected: Any
    actual: Any
    passed: bool
    note: str = ""


def _silver_trial_stats(cfg: ProjectConfig, run_id: str) -> tuple[int, int] | None:
    path = cfg.paths.silver / "silver_trials" / f"run_id={run_id}.parquet"
    if not path.exists():
        return None
    row = duckdb.sql(
        "select count(*), count(distinct nct_id) from read_parquet(?)",
        params=[path.as_posix()],
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def _success_runs(cfg: ProjectConfig) -> list[IngestionManifest]:
    return [m for m in load_manifests(cfg.paths.bronze_manifests) if m.status == "success"]


def bronze_silver_checks(cfg: ProjectConfig | None = None) -> list[ReconciliationCheck]:
    """Bronze manifests vs silver Parquet. No warehouse dependency — safe to run
    as the pre-dbt gate on silver_entities.

    The row expectation is the manifest count minus the exclusions the transform
    recorded for this run: it keeps the first occurrence of a repeated NCT ID and
    quarantines NCT-less records, so a shortfall against the raw manifest count is
    normal, and gating on the raw count blocks every legitimate dedup.

    This is not a weaker loss guard. The expectation can only account for drops the
    transform itself reported, so any loss beyond those still fails, and stats that
    are missing, unreadable, or carry a disagreeing manifest count fall back to the
    full record count. Every branch stays exact — `rows <= record_count` would pass
    a silently truncated table, which is the failure this gate exists to catch.
    """
    cfg = cfg or get_config()
    checks: list[ReconciliationCheck] = []

    success_runs = _success_runs(cfg)
    if not success_runs:
        checks.append(
            ReconciliationCheck(
                check="success_runs_exist",
                run_id=None,
                expected=">= 1",
                actual=0,
                passed=False,
                note="No complete ingestion runs found.",
            )
        )
        _log_failures("Bronze→silver", checks)
        return checks

    for manifest in success_runs:
        stats = _silver_trial_stats(cfg, manifest.ingestion_run_id)
        if stats is None:
            checks.append(
                ReconciliationCheck(
                    check="silver_exists_for_success_run",
                    run_id=manifest.ingestion_run_id,
                    expected="silver_trials parquet present",
                    actual="missing",
                    passed=False,
                    note="Run `make transform`.",
                )
            )
            continue
        rows, distinct_ncts = stats
        expected = expected_trial_rows(
            load_transform_stats(cfg, manifest.ingestion_run_id), manifest.record_count
        )
        note = ""
        if expected is None:
            # No recorded exclusions, so expect every bronze record to survive.
            expected, note = (
                manifest.record_count,
                (
                    "No transform stats on file, so legitimate dedup cannot be "
                    "accounted for; rebuild with `make transform --force`."
                ),
            )
        checks.append(
            ReconciliationCheck(
                check="bronze_manifest_vs_silver_rows",
                run_id=manifest.ingestion_run_id,
                expected=expected,
                actual=rows,
                passed=rows == expected,
                note=note,
            )
        )
        checks.append(
            ReconciliationCheck(
                check="silver_nct_ids_unique",
                run_id=manifest.ingestion_run_id,
                expected=rows,
                actual=distinct_ncts,
                passed=distinct_ncts == rows,
            )
        )

    _log_failures("Bronze→silver", checks)
    return checks


def warehouse_checks(cfg: ProjectConfig | None = None) -> list[ReconciliationCheck]:
    """DuckDB warehouse vs latest silver. Requires the warehouse dbt builds —
    run as post-build validation on dim_trial, not before dbt."""
    cfg = cfg or get_config()
    checks: list[ReconciliationCheck] = []

    warehouse = cfg.paths.duckdb
    if not warehouse.exists():
        checks.append(
            ReconciliationCheck(
                check="warehouse_exists",
                run_id=None,
                expected=str(warehouse),
                actual="missing",
                passed=False,
                note="Run `make dbt-run`.",
            )
        )
        _log_failures("Warehouse", checks)
        return checks

    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        row = con.execute("select count(*) from main_marts.dim_trial").fetchone()
        assert row is not None
        dim_trial_count = row[0]
        success_runs = _success_runs(cfg)
        latest = max(success_runs, key=lambda m: m.ingestion_run_id) if success_runs else None
        latest_stats = _silver_trial_stats(cfg, latest.ingestion_run_id) if latest else None
        expected_trials = latest_stats[1] if latest_stats else None
        checks.append(
            ReconciliationCheck(
                check="warehouse_dim_trial_vs_latest_silver",
                run_id=latest.ingestion_run_id if latest else None,
                expected=expected_trials,
                actual=dim_trial_count,
                passed=expected_trials == dim_trial_count,
                note="dim_trial holds one row per NCT ID seen in any snapshot;"
                " equality holds while snapshots share one query scope.",
            )
        )
        flag_row = con.execute(
            "select count(*) from main_marts.fct_trial_snapshot where current_record_flag"
        ).fetchone()
        assert flag_row is not None
        current_flags = flag_row[0]
        checks.append(
            ReconciliationCheck(
                check="warehouse_one_current_record_per_trial",
                run_id=None,
                expected=dim_trial_count,
                actual=current_flags,
                passed=current_flags <= dim_trial_count,
                note="Current records cannot exceed known trials.",
            )
        )
    finally:
        con.close()

    _log_failures("Warehouse", checks)
    return checks


def _log_failures(layer: str, checks: list[ReconciliationCheck]) -> None:
    for check in (c for c in checks if not c.passed):
        logger.warning("{} reconciliation FAILED: {}", layer, asdict(check))


def run_reconciliation(cfg: ProjectConfig | None = None) -> list[ReconciliationCheck]:
    """All cross-layer checks: bronze→silver plus warehouse (public API)."""
    checks = bronze_silver_checks(cfg) + warehouse_checks(cfg)
    failed = [c for c in checks if not c.passed]
    if failed:
        logger.warning("Reconciliation: {} of {} checks FAILED.", len(failed), len(checks))
    else:
        logger.info("All {} reconciliation checks passed.", len(checks))
    return checks
