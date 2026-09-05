import duckdb
import pandas as pd
from dagster import materialize

from src.ingest.snapshot_manifest import IngestionManifest, write_manifest
from src.orchestration.assets.bronze import IngestParams, ctg_raw_pages
from src.orchestration.assets.silver import silver_entities
from src.orchestration.checks import bronze_silver_reconciliation, manifest_integrity
from src.utils.dates import utc_now
from tests.conftest import check_evaluation, materialize_with_checks


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


def test_bronze_asset_writes_manifest_and_materializes(project_root_tmp, monkeypatch) -> None:
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config

        cfg = load_config()
        write_manifest(cfg.paths.bronze_manifests, manifest)
        return manifest

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)
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

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)
    result = materialize(
        assets=[ctg_raw_pages],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
        raise_on_error=False,
    )
    assert not result.success


def test_manifest_integrity_passes_on_success_run(project_root_tmp, monkeypatch) -> None:
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config

        write_manifest(load_config().paths.bronze_manifests, manifest)
        return manifest

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)
    result = materialize_with_checks(
        assets=[ctg_raw_pages],
        asset_checks=[manifest_integrity],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    evaluation = check_evaluation(result, "manifest_integrity")
    assert evaluation is not None and evaluation.passed


def test_manifest_integrity_fails_when_counts_disagree(project_root_tmp, monkeypatch) -> None:
    manifest = _success_manifest().model_copy(
        update={"record_count": 3, "total_count_reported": 999}
    )

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        from src.config import load_config

        write_manifest(load_config().paths.bronze_manifests, manifest)
        return manifest

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)
    result = materialize_with_checks(
        assets=[ctg_raw_pages],
        asset_checks=[manifest_integrity],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
        raise_on_error=False,
    )
    evaluation = check_evaluation(result, "manifest_integrity")
    assert evaluation is not None and not evaluation.passed


def test_manifest_integrity_fails_with_no_success_runs(project_root_tmp, monkeypatch) -> None:
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        return manifest  # returns, but never writes a manifest file

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)
    result = materialize_with_checks(
        assets=[ctg_raw_pages],
        asset_checks=[manifest_integrity],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
        raise_on_error=False,
    )
    evaluation = check_evaluation(result, "manifest_integrity")
    assert evaluation is not None and not evaluation.passed


def _patch_quiet_bronze(monkeypatch) -> None:
    """Bronze runs but writes nothing: seeded state fully controls the check."""
    manifest = _success_manifest()

    def fake_run_ingestion(condition=None, full_refresh=False, max_pages=None):
        return manifest

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)


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
    con.execute("create table main_marts.dim_trial as select 'NCT00000001' as nct_id")
    con.execute("create table main_marts.fct_trial_snapshot as select false as current_record_flag")
    con.close()


def test_silver_asset_materializes_processed_runs(project_root_tmp, monkeypatch) -> None:
    _seed_reconcilable_state()
    _patch_quiet_bronze(monkeypatch)

    def fake_run_transform(run_id=None, force=False):
        return ["20260904T120000Z_abc12345"]

    monkeypatch.setattr("src.orchestration.assets.silver.run_transform", fake_run_transform)
    result = materialize(
        assets=[ctg_raw_pages, silver_entities],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    assert result.success
    assert len(result.get_asset_materialization_events()) == 2


def test_bronze_silver_check_passes_on_consistent_state(project_root_tmp, monkeypatch) -> None:
    _seed_reconcilable_state()
    _patch_quiet_bronze(monkeypatch)

    def fake_run_transform(run_id=None, force=False):
        return ["20260904T120000Z_abc12345"]

    monkeypatch.setattr("src.orchestration.assets.silver.run_transform", fake_run_transform)
    result = materialize_with_checks(
        assets=[ctg_raw_pages, silver_entities],
        asset_checks=[bronze_silver_reconciliation],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    evaluation = check_evaluation(result, "bronze_silver_reconciliation")
    assert evaluation is not None and evaluation.passed


def test_bronze_silver_check_fails_when_silver_missing(project_root_tmp, monkeypatch) -> None:
    _patch_quiet_bronze(monkeypatch)

    def fake_run_transform(run_id=None, force=False):
        return ["20260904T120000Z_abc12345"]

    monkeypatch.setattr("src.orchestration.assets.silver.run_transform", fake_run_transform)
    result = materialize_with_checks(
        assets=[ctg_raw_pages, silver_entities],
        asset_checks=[bronze_silver_reconciliation],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
        raise_on_error=False,
    )
    evaluation = check_evaluation(result, "bronze_silver_reconciliation")
    assert evaluation is not None and not evaluation.passed


def test_warehouse_checks_pass_on_consistent_state(project_root_tmp) -> None:
    """warehouse_checks is the post-build gate on dim_trial: it validates the
    dbt-built warehouse against the latest silver."""
    _seed_reconcilable_state()

    from src.quality.reconciliation import warehouse_checks

    checks = warehouse_checks()
    assert checks
    assert all(c.passed for c in checks), [c.check for c in checks if not c.passed]


def test_warehouse_checks_fail_when_warehouse_missing(project_root_tmp) -> None:
    from src.config import load_config
    from src.ingest.snapshot_manifest import write_manifest

    cfg = load_config()
    write_manifest(
        cfg.paths.bronze_manifests,
        IngestionManifest(
            ingestion_run_id="20260904T120000Z_abc12345",
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

    from src.quality.reconciliation import warehouse_checks

    checks = warehouse_checks()
    assert [c.check for c in checks if not c.passed] == ["warehouse_exists"]
