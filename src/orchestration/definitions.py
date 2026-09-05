"""Dagster Definitions: the single import surface for dagster dev and CI."""

from dagster import AssetSelection, Definitions, ScheduleDefinition, define_asset_job
from dagster_dbt import DbtCliResource

from src.orchestration.assets.bronze import ctg_raw_pages
from src.orchestration.assets.dbt_assets import clinical_trials_dbt_assets
from src.orchestration.assets.silver import silver_entities
from src.orchestration.checks import cross_layer_reconciliation, manifest_integrity

weekly_refresh = define_asset_job(
    name="weekly_refresh",
    selection=AssetSelection.all(),
)

weekly_refresh_schedule = ScheduleDefinition(
    job=weekly_refresh,
    cron_schedule="0 13 * * 1",  # every Monday 13:00 UTC
    name="weekly_refresh_schedule",
)

defs = Definitions(
    assets=[ctg_raw_pages, silver_entities, clinical_trials_dbt_assets],
    asset_checks=[manifest_integrity, cross_layer_reconciliation],
    resources={
        "dbt": DbtCliResource(project_dir="dbt_clinical_trials"),
    },
    jobs=[weekly_refresh],
    schedules=[weekly_refresh_schedule],
)
