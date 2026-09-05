"""Silver asset: flatten bronze JSON runs into normalized Parquet entities."""

from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from src.transform.build_silver_entities import run_transform


@asset(
    name="silver_entities",
    deps=["ctg_raw_pages"],
    description=(
        "Flattened, normalized silver Parquet entities for every completed bronze "
        "run not yet transformed."
    ),
)
def silver_entities(context: AssetExecutionContext) -> MaterializeResult[None]:
    processed = run_transform(run_id=None, force=False)
    context.log.info(f"Transformed {len(processed)} bronze run(s): {processed}")
    return MaterializeResult(
        metadata={
            "processed_runs": MetadataValue.json(processed),
            "processed_count": len(processed),
        }
    )
