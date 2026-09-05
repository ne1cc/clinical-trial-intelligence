"""dbt models surfaced as individual Dagster assets via dagster-dbt."""

from collections.abc import Iterator, Mapping
from typing import Any

from dagster import (
    AssetCheckEvaluation,
    AssetCheckResult,
    AssetExecutionContext,
    AssetKey,
    AssetMaterialization,
    AssetObservation,
    Output,
)
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    dbt_assets,
)

from src.utils.paths import project_root

DBT_PROJECT_DIR = project_root() / "dbt_clinical_trials"
DBT_MANIFEST_PATH = DBT_PROJECT_DIR / "target" / "manifest.json"


class PlatformDagsterDbtTranslator(DagsterDbtTranslator):
    """Asset keys for the platform graph: dbt sources map onto the Dagster
    assets that produce them (silver parquet, bronze manifests), so the dbt
    models are downstream of silver_entities and its blocking checks gate the
    build. Models/seeds/tests keep bare names — the dim_/fct_/mart_ prefixes
    keep them unique.

    Several dbt sources share one producing asset (the six silver entities all
    come from silver_entities), so duplicate *source* asset keys must be
    enabled — dagster-dbt only permits that for source resources.
    """

    SOURCE_TO_ASSET_KEY = {
        "silver": AssetKey("silver_entities"),
        "bronze": AssetKey("ctg_raw_pages"),
    }

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return self.SOURCE_TO_ASSET_KEY[dbt_resource_props["source_name"]]
        return AssetKey([dbt_resource_props["name"]])


if not DBT_MANIFEST_PATH.exists():
    raise RuntimeError(
        f"dbt manifest not found at {DBT_MANIFEST_PATH}. "
        "dagster-dbt needs a parsed manifest to surface the dbt models as assets. "
        "Generate it with: uv run dbt parse --project-dir dbt_clinical_trials "
        "--profiles-dir dbt_clinical_trials "
        "(see README section 'How to run the orchestrator locally')."
    )


@dbt_assets(
    manifest=DBT_MANIFEST_PATH,
    dagster_dbt_translator=PlatformDagsterDbtTranslator(
        settings=DagsterDbtTranslatorSettings(enable_duplicate_source_asset_keys=True)
    ),
)
def clinical_trials_dbt_assets(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[
    Output[Any] | AssetMaterialization | AssetObservation | AssetCheckResult | AssetCheckEvaluation
]:
    yield from dbt.cli(["build"], context=context).stream()
