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
