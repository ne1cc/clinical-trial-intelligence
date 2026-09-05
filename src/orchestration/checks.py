"""Blocking asset checks that gate the publish path on data quality."""

from dagster import AssetCheckResult, MetadataValue, asset_check

from src.config import load_config
from src.ingest.snapshot_manifest import load_manifests
from src.quality.reconciliation import run_reconciliation


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
