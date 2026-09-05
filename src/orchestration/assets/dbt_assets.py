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
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets

from src.utils.paths import project_root

DBT_PROJECT_DIR = project_root() / "dbt_clinical_trials"
DBT_MANIFEST_PATH = DBT_PROJECT_DIR / "target" / "manifest.json"


class BareModelNameDagsterDbtTranslator(DagsterDbtTranslator):
    """Bare-name asset keys: dbt schema dirs must not leak into Dagster asset keys; the
    project's dim_/fct_/mart_ prefixes keep names unique.
    """

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        return AssetKey([dbt_resource_props["name"]])


@dbt_assets(
    manifest=DBT_MANIFEST_PATH,
    dagster_dbt_translator=BareModelNameDagsterDbtTranslator(),
)
def clinical_trials_dbt_assets(
    context: AssetExecutionContext,
    dbt: DbtCliResource,
) -> Iterator[
    Output | AssetMaterialization | AssetObservation | AssetCheckResult | AssetCheckEvaluation
]:
    yield from dbt.cli(["build"], context=context).stream()
