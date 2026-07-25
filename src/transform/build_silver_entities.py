"""Bronze → Silver orchestration.

Processes completed (status=success) ingestion runs by default; partial and
failed runs are excluded from silver so no downstream metric can include an
incomplete snapshot. Duplicate NCT IDs within a run are deduplicated (first
occurrence kept) and reported, never silently ignored.
"""

from src.config import ProjectConfig, get_config
from src.ingest.snapshot_manifest import IngestionManifest, load_manifests
from src.transform.export_parquet import export_entity
from src.transform.flatten_studies import flatten_study, iter_bronze_studies
from src.transform.normalize_conditions import get_taxonomy
from src.transform.normalize_locations import get_geography_rules
from src.utils.logging import setup_logging

ENTITY_NAMES = (
    "silver_trials",
    "silver_trial_conditions",
    "silver_trial_interventions",
    "silver_trial_sponsors",
    "silver_trial_locations",
    "silver_trial_outcomes",
    "silver_trial_eligibility_criteria",
)


def _already_transformed(cfg: ProjectConfig, run_id: str) -> bool:
    return all(
        (cfg.paths.silver / entity / f"run_id={run_id}.parquet").exists() for entity in ENTITY_NAMES
    )


def build_silver_for_run(manifest: IngestionManifest, cfg: ProjectConfig) -> dict[str, int]:
    log = setup_logging()
    run_id = manifest.ingestion_run_id
    run_dir = cfg.paths.bronze_api_responses / f"run_id={run_id}"
    if not run_dir.exists():
        raise FileNotFoundError(f"Bronze pages missing for run {run_id}: {run_dir}")

    taxonomy = get_taxonomy()
    geography = get_geography_rules()
    snapshot_ts = manifest.started_at_utc.isoformat()

    collected: dict[str, list[dict]] = {name: [] for name in ENTITY_NAMES}
    seen_nct_ids: set[str] = set()
    duplicate_count = 0
    skipped_no_nct = 0

    for study in iter_bronze_studies(run_dir):
        rows = flatten_study(study, run_id, snapshot_ts, taxonomy, geography)
        nct_id = rows["silver_trials"][0]["nct_id"]
        if not nct_id:
            skipped_no_nct += 1  # already quarantined at ingestion
            continue
        if nct_id in seen_nct_ids:
            duplicate_count += 1
            continue
        seen_nct_ids.add(nct_id)
        for entity, entity_rows in rows.items():
            collected[entity].extend(entity_rows)

    if duplicate_count:
        log.warning(
            "Run {}: deduplicated {} repeated NCT IDs (kept first).", run_id, duplicate_count
        )
    if skipped_no_nct:
        log.warning(
            "Run {}: skipped {} records without NCT ID (quarantined).", run_id, skipped_no_nct
        )

    row_counts: dict[str, int] = {}
    for entity in ENTITY_NAMES:
        path, count = export_entity(collected[entity], entity, run_id, cfg.paths.silver)
        row_counts[entity] = count
        log.info("Run {}: wrote {} rows -> {}", run_id, count, path)

    expected = manifest.record_count - duplicate_count - skipped_no_nct
    if row_counts["silver_trials"] != expected:
        log.warning(
            "Run {}: silver_trials rows ({}) != manifest records minus exclusions ({}).",
            run_id,
            row_counts["silver_trials"],
            expected,
        )
    return row_counts


def run_transform(
    run_id: str | None = None,
    force: bool = False,
    config: ProjectConfig | None = None,
) -> list[str]:
    """Transform bronze runs into silver. Returns processed run IDs."""
    log = setup_logging()
    cfg = config or get_config()
    manifests = load_manifests(cfg.paths.bronze_manifests)

    if run_id:
        selected = [m for m in manifests if m.ingestion_run_id == run_id]
        if not selected:
            raise ValueError(f"No manifest found for run {run_id}")
        if selected[0].status != "success":
            log.warning(
                "Run {} has status '{}' (not 'success'); transforming because it was "
                "explicitly requested. It remains excluded from complete-snapshot metrics.",
                run_id,
                selected[0].status,
            )
    else:
        selected = [m for m in manifests if m.status == "success"]

    processed: list[str] = []
    for manifest in selected:
        if not force and _already_transformed(cfg, manifest.ingestion_run_id):
            log.info(
                "Run {} already transformed; skipping (use --force to rebuild).",
                manifest.ingestion_run_id,
            )
            continue
        build_silver_for_run(manifest, cfg)
        processed.append(manifest.ingestion_run_id)

    if not processed:
        log.info("No runs to transform ({} manifests inspected).", len(manifests))
    return processed
