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
