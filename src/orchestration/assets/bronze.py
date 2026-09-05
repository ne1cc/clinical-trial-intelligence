"""Bronze asset: snapshot ClinicalTrials.gov studies into immutable raw pages."""

from dagster import AssetExecutionContext, Config, MaterializeResult, MetadataValue, asset

from src.ingest.extract_studies import run_ingestion


class IngestParams(Config):
    condition: str | None = None
    full_refresh: bool = False
    max_pages: int | None = None


@asset(
    name="ctg_raw_pages",
    description=(
        "Paginated snapshot of ClinicalTrials.gov API v2 studies written to bronze "
        "as raw JSON pages plus a signed ingestion manifest."
    ),
)
def ctg_raw_pages(
    context: AssetExecutionContext, config: IngestParams
) -> MaterializeResult:
    manifest = run_ingestion(
        condition=config.condition,
        full_refresh=config.full_refresh,
        max_pages=config.max_pages,
    )
    if manifest.status == "failed":
        raise RuntimeError(
            f"Ingestion run {manifest.ingestion_run_id} failed: {manifest.error}"
        )
    context.log.info(
        f"Ingestion run {manifest.ingestion_run_id} status={manifest.status} "
        f"records={manifest.record_count} pages={manifest.page_count}"
    )
    return MaterializeResult(
        metadata={
            "ingestion_run_id": manifest.ingestion_run_id,
            "status": manifest.status,
            "record_count": manifest.record_count,
            "page_count": manifest.page_count,
            "query_hash": manifest.query_hash,
            "params": MetadataValue.json(manifest.params),
        }
    )
