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
