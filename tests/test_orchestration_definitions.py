from tests.conftest import check_evaluation, materialize_with_checks


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


def test_failed_bronze_check_blocks_silver(project_root_tmp, monkeypatch) -> None:
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

    monkeypatch.setattr("src.orchestration.assets.bronze.run_ingestion", fake_run_ingestion)
    monkeypatch.setattr("src.orchestration.assets.silver.run_transform", fake_run_transform)
    result = materialize_with_checks(
        assets=[ctg_raw_pages, silver_entities],
        asset_checks=[manifest_integrity, cross_layer_reconciliation],
        run_config={"ops": {"ctg_raw_pages": {"config": IngestParams().model_dump()}}},
    )
    evaluation = check_evaluation(result, "manifest_integrity")
    assert evaluation is not None and not evaluation.passed
    silver_materialized = any(
        e.asset_key is not None and e.asset_key.to_user_string() == "silver_entities"
        for e in result.get_asset_materialization_events()
    )
    assert not silver_materialized
