"""Blocking asset checks that gate the publish path on data quality.

Two gates: `bronze_silver_reconciliation` blocks silver downstream (bad silver
never reaches dbt), and `warehouse_reconciliation` validates the warehouse dbt
built against the latest silver.
"""

from dagster import AssetCheckResult, MetadataValue, asset_check

from src.config import load_config
from src.ingest.snapshot_manifest import load_manifests
from src.quality.reconciliation import bronze_silver_checks, warehouse_checks


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
    # ingestion_run_id ordering is UTC-compact (src/ingest/snapshot_manifest.py
    # new_run_id), so lexicographic max is the latest run.
    latest = max(success_runs, key=lambda m: m.ingestion_run_id)
    counts_agree = (
        latest.total_count_reported is None or latest.record_count == latest.total_count_reported
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


@asset_check(asset="silver_entities", name="bronze_silver_reconciliation", blocking=True)
def bronze_silver_reconciliation() -> AssetCheckResult:
    """Pre-dbt gate: bad silver stops the build before dbt runs."""
    checks = bronze_silver_checks()
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


@asset_check(asset="dim_trial", name="warehouse_reconciliation", blocking=True)
def warehouse_reconciliation() -> AssetCheckResult:
    """Post-build validation: the warehouse dbt built must reconcile to the
    latest silver. Attached to dim_trial — an asset produced by the dbt
    multi-asset, so fct_trial_snapshot is populated by the time this runs."""
    checks = warehouse_checks()
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
