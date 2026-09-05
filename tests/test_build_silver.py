import json
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from src.config import ApiConfig, IngestionConfig, PathsConfig, ProjectConfig
from src.ingest.snapshot_manifest import IngestionManifest
from src.transform.build_silver_entities import build_silver_for_run
from src.transform.export_parquet import ENTITY_COLUMNS
from src.utils.dates import utc_now


def make_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        api=ApiConfig(base_url="https://ctg.test/api/v2"),
        paths=PathsConfig(
            bronze_api_responses=tmp_path / "bronze" / "api_responses",
            bronze_manifests=tmp_path / "bronze" / "manifests",
            silver=tmp_path / "silver",
            gold=tmp_path / "gold",
            duckdb=tmp_path / "warehouse" / "warehouse.duckdb",
            quarantine=tmp_path / "quarantine",
        ),
        ingestion=IngestionConfig(),
    )


def make_manifest(run_id: str, record_count: int) -> IngestionManifest:
    return IngestionManifest(
        ingestion_run_id=run_id,
        query_hash="abc123",
        endpoint="https://ctg.test/api/v2/studies",
        params={},
        status="success",
        started_at_utc=utc_now(),
        ended_at_utc=utc_now(),
        record_count=record_count,
    )


def write_bronze_page(run_dir: Path, page: int, studies: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"page={page:05d}.json").write_text(json.dumps({"studies": studies}))


def make_study(nct_id: str) -> dict:
    return {"protocolSection": {"identificationModule": {"nctId": nct_id}}}


def test_build_silver_dedups_across_flush_boundary(tmp_path: Path, monkeypatch):
    cfg = make_config(tmp_path)
    run_id = "r_dedup"
    run_dir = cfg.paths.bronze_api_responses / f"run_id={run_id}"
    write_bronze_page(run_dir, 1, [make_study("NCT00000001"), make_study("NCT00000002")])
    write_bronze_page(run_dir, 2, [make_study("NCT00000003")])
    write_bronze_page(run_dir, 3, [make_study("NCT00000002"), make_study("NCT00000001")])
    monkeypatch.setattr("src.transform.build_silver_entities.FLUSH_ROWS", 2)

    row_counts = build_silver_for_run(make_manifest(run_id, record_count=5), cfg)

    assert row_counts["silver_trials"] == 3
    path = cfg.paths.silver / "silver_trials" / f"run_id={run_id}.parquet"
    assert pd.read_parquet(path)["nct_id"].tolist() == [
        "NCT00000001",
        "NCT00000002",
        "NCT00000003",
    ]
    assert pq_num_row_groups(path) == 2


def test_build_silver_writes_schema_only_files_for_empty_entities(tmp_path: Path):
    cfg = make_config(tmp_path)
    run_id = "r_single"
    run_dir = cfg.paths.bronze_api_responses / f"run_id={run_id}"
    write_bronze_page(run_dir, 1, [make_study("NCT00000001")])

    row_counts = build_silver_for_run(make_manifest(run_id, record_count=1), cfg)

    assert row_counts["silver_trials"] == 1
    assert row_counts["silver_trial_conditions"] == 0
    for entity in ENTITY_COLUMNS:
        assert (cfg.paths.silver / entity / f"run_id={run_id}.parquet").exists()
    path = cfg.paths.silver / "silver_trial_conditions" / f"run_id={run_id}.parquet"
    con = duckdb.connect(":memory:")
    result = con.execute(f"select * from read_parquet('{path.as_posix()}')").fetchall()
    assert result == []
    assert [d[0] for d in con.description] == ENTITY_COLUMNS["silver_trial_conditions"]


def test_build_silver_skips_records_without_nct_id(tmp_path: Path):
    cfg = make_config(tmp_path)
    run_id = "r_skip"
    run_dir = cfg.paths.bronze_api_responses / f"run_id={run_id}"
    write_bronze_page(run_dir, 1, [make_study("NCT00000001"), {"protocolSection": {}}])

    row_counts = build_silver_for_run(make_manifest(run_id, record_count=2), cfg)

    assert row_counts["silver_trials"] == 1
    path = cfg.paths.silver / "silver_trials" / f"run_id={run_id}.parquet"
    assert pd.read_parquet(path)["nct_id"].tolist() == ["NCT00000001"]


def pq_num_row_groups(path: Path) -> int:
    return pq.ParquetFile(path).metadata.num_row_groups
