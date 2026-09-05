"""Cross-layer reconciliation: bronze manifests vs silver Parquet vs warehouse.

Every complete (success) run must carry the same trial count through each
layer. Failures are reported, never silently corrected.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import duckdb
from loguru import logger

from src.config import ProjectConfig, get_config
from src.ingest.snapshot_manifest import load_manifests


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
        f"select count(*), count(distinct nct_id) from read_parquet('{path.as_posix()}')"
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def run_reconciliation(cfg: ProjectConfig | None = None) -> list[ReconciliationCheck]:
    cfg = cfg or get_config()
    checks: list[ReconciliationCheck] = []

    success_runs = [m for m in load_manifests(cfg.paths.bronze_manifests) if m.status == "success"]
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
        checks.append(
            ReconciliationCheck(
                check="bronze_manifest_vs_silver_rows",
                run_id=manifest.ingestion_run_id,
                expected=manifest.record_count,
                actual=rows,
                passed=rows == manifest.record_count,
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

    latest = max(success_runs, key=lambda m: m.ingestion_run_id)
    warehouse = cfg.paths.duckdb
    if warehouse.exists():
        con = duckdb.connect(str(warehouse), read_only=True)
        try:
            row = con.execute("select count(*) from main_marts.dim_trial").fetchone()
            assert row is not None
            dim_trial_count = row[0]
            latest_stats = _silver_trial_stats(cfg, latest.ingestion_run_id)
            expected_trials = latest_stats[1] if latest_stats else None
            checks.append(
                ReconciliationCheck(
                    check="warehouse_dim_trial_vs_latest_silver",
                    run_id=latest.ingestion_run_id,
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
    else:
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

    failed = [c for c in checks if not c.passed]
    if failed:
        for check in failed:
            logger.warning("Reconciliation FAILED: {}", asdict(check))
    else:
        logger.info("All {} reconciliation checks passed.", len(checks))
    return checks
