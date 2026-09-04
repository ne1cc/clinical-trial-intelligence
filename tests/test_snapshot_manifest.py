import re
from datetime import timedelta

import pandas as pd

from src.ingest.snapshot_manifest import (
    IngestionManifest,
    find_reusable_run,
    load_manifests,
    new_run_id,
    write_manifest,
    write_summary,
)
from src.utils.dates import utc_now

RUN_ID_SHAPE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{8}$")


def make_manifest(**overrides) -> IngestionManifest:
    defaults = dict(
        ingestion_run_id=new_run_id(),
        query_hash="abc123",
        endpoint="https://ctg.test/api/v2/studies",
        condition="Alzheimer Disease",
        params={"query.cond": "Alzheimer Disease", "pageSize": "100"},
        status="success",
        started_at_utc=utc_now(),
        ended_at_utc=utc_now(),
        page_count=3,
        record_count=250,
        total_count_reported=250,
    )
    defaults.update(overrides)
    return IngestionManifest(**defaults)


def test_new_run_id_shape_and_uniqueness():
    ids = {new_run_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(RUN_ID_SHAPE.match(run_id) for run_id in ids)


def test_write_and_load_manifest_roundtrip(tmp_path):
    manifest = make_manifest()
    path = write_manifest(tmp_path, manifest)
    assert path.name == f"manifest_{manifest.ingestion_run_id}.json"
    loaded = load_manifests(tmp_path)
    assert len(loaded) == 1
    assert loaded[0] == manifest


def test_find_reusable_run_matches_recent_success(tmp_path):
    manifest = make_manifest()
    write_manifest(tmp_path, manifest)
    found = find_reusable_run(tmp_path, "abc123", reuse_window_hours=24)
    assert found is not None
    assert found.ingestion_run_id == manifest.ingestion_run_id


def test_find_reusable_run_ignores_other_hash_failed_and_stale(tmp_path):
    write_manifest(tmp_path, make_manifest(query_hash="other"))
    write_manifest(tmp_path, make_manifest(status="failed"))
    write_manifest(tmp_path, make_manifest(status="partial"))
    write_manifest(tmp_path, make_manifest(started_at_utc=utc_now() - timedelta(hours=48)))
    assert find_reusable_run(tmp_path, "abc123", reuse_window_hours=24) is None


def test_find_reusable_run_returns_most_recent(tmp_path):
    older = make_manifest(started_at_utc=utc_now() - timedelta(hours=2))
    newer = make_manifest()
    write_manifest(tmp_path, older)
    write_manifest(tmp_path, newer)
    found = find_reusable_run(tmp_path, "abc123", reuse_window_hours=24)
    assert found.ingestion_run_id == newer.ingestion_run_id


def test_write_summary_parquet_and_csv(tmp_path):
    manifest = make_manifest()
    parquet_path, csv_path = write_summary(tmp_path, manifest)
    assert parquet_path.exists() and csv_path.exists()
    frame = pd.read_parquet(parquet_path)
    assert frame.loc[0, "ingestion_run_id"] == manifest.ingestion_run_id
    assert int(frame.loc[0, "record_count"]) == 250
