"""Cross-layer reconciliation must account for the transform's legitimate
exclusions without becoming a weaker data-loss guard."""

import json
from pathlib import Path

import pytest

from src.ingest.snapshot_manifest import write_manifest
from src.quality.reconciliation import bronze_silver_checks, run_reconciliation
from src.transform.build_silver_entities import build_silver_for_run
from src.transform.silver_stats import (
    expected_trial_rows,
    load_transform_stats,
    stats_path,
)
from tests.test_build_silver import make_config, make_manifest, make_study, write_bronze_page


def _check(cfg, name: str):
    return next(c for c in bronze_silver_checks(cfg) if c.check == name)


def _build_deduped_run(tmp_path: Path, run_id: str):
    """Three bronze records, one repeated NCT ID -> two silver trial rows."""
    cfg = make_config(tmp_path)
    run_dir = cfg.paths.bronze_api_responses / f"run_id={run_id}"
    write_bronze_page(run_dir, 1, [make_study("NCT00000001"), make_study("NCT00000002")])
    write_bronze_page(run_dir, 2, [make_study("NCT00000002")])
    cfg.paths.bronze_manifests.mkdir(parents=True, exist_ok=True)
    write_manifest(cfg.paths.bronze_manifests, make_manifest(run_id, record_count=3))
    build_silver_for_run(make_manifest(run_id, record_count=3), cfg)
    return cfg


def test_reconciliation_accounts_for_recorded_dedup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.transform.build_silver_entities.FLUSH_ROWS", 1)
    cfg = _build_deduped_run(tmp_path, "r_dedup")

    check = _check(cfg, "bronze_manifest_vs_silver_rows")
    assert check.expected == 2, "expectation must subtract the transform's dedup"
    assert check.actual == 2
    assert check.passed, "a legitimate dedup must not fail the data-loss guard"
    assert check.note == ""


def test_reconciliation_without_stats_stays_strict(tmp_path: Path, monkeypatch):
    """Deleting the sidecar must not silently downgrade the check to 'any
    shortfall is fine'."""
    monkeypatch.setattr("src.transform.build_silver_entities.FLUSH_ROWS", 1)
    cfg = _build_deduped_run(tmp_path, "r_nostats")
    stats_path(cfg, "r_nostats").unlink()

    check = _check(cfg, "bronze_manifest_vs_silver_rows")
    assert check.expected == 3
    assert check.actual == 2
    assert not check.passed
    assert "make transform --force" in check.note


def test_reconciliation_fails_on_loss_beyond_recorded_exclusions(tmp_path: Path, monkeypatch):
    """With stats claiming nothing was excluded, a shortfall is a failure even
    though it would satisfy a 'rows <= records' rule."""
    monkeypatch.setattr("src.transform.build_silver_entities.FLUSH_ROWS", 1)
    cfg = _build_deduped_run(tmp_path, "r_loss")
    path = stats_path(cfg, "r_loss")
    stats = json.loads(path.read_text(encoding="utf-8"))
    stats["duplicate_nct_ids_dropped"] = 0
    path.write_text(json.dumps(stats), encoding="utf-8")

    check = _check(cfg, "bronze_manifest_vs_silver_rows")
    assert check.expected == 3
    assert check.actual == 2
    assert not check.passed


def test_silver_nct_ids_unique_still_passes_after_dedup(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.transform.build_silver_entities.FLUSH_ROWS", 1)
    cfg = _build_deduped_run(tmp_path, "r_unique")
    assert _check(cfg, "silver_nct_ids_unique").passed


def test_stale_stats_for_a_different_record_count_are_rejected():
    """A reused run_id must not have its expectation drawn from another run's
    exclusions."""
    stats = {
        "manifest_record_count": 999,
        "duplicate_nct_ids_dropped": 997,
        "records_without_nct_id": 0,
    }
    assert expected_trial_rows(stats, record_count=3) is None


def test_missing_stats_yield_no_expectation():
    assert expected_trial_rows(None, record_count=3) is None


def test_unreadable_stats_yield_no_expectation(tmp_path: Path):
    cfg = make_config(tmp_path)
    path = stats_path(cfg, "r_bad")
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    assert load_transform_stats(cfg, "r_bad") is None
    assert expected_trial_rows(load_transform_stats(cfg, "r_bad"), record_count=3) is None


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"manifest_record_count": 3, "duplicate_nct_ids_dropped": "not-a-number"},
    ],
)
def test_malformed_stats_fields_yield_no_expectation(bad):
    assert expected_trial_rows(bad, record_count=3) is None


def test_run_reconciliation_composes_both_layers(tmp_path: Path, monkeypatch):
    """`data_quality_report` uses the composer, not the layer functions, so it
    needs to keep returning bronze→silver results even when the warehouse layer
    has nothing to check."""
    monkeypatch.setattr("src.transform.build_silver_entities.FLUSH_ROWS", 1)
    cfg = _build_deduped_run(tmp_path, "r_compose")

    names = {c.check for c in run_reconciliation(cfg)}
    assert "bronze_manifest_vs_silver_rows" in names
    assert "warehouse_exists" in names, "tmp cfg has no warehouse; that layer still reports"
