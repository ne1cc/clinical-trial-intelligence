"""Ingestion orchestrator.

Note on history: the ClinicalTrials.gov API returns only each study's
*current* record. Longitudinal status history is created by this project
through repeated snapshot runs — every run saves unmodified page JSON under
a unique ingestion_run_id, and downstream models compare snapshots.
"""

from src.config import ProjectConfig, get_config, load_indication_profile
from src.ingest.ctg_client import CTGClient
from src.ingest.pagination import iter_pages
from src.ingest.snapshot_manifest import (
    IngestionManifest,
    find_reusable_run,
    new_run_id,
    write_manifest,
    write_summary,
)
from src.ingest.validate_api_payload import (
    QuarantineRecord,
    screen_studies,
    validate_page,
    write_quarantine_report,
)
from src.utils.dates import utc_now
from src.utils.hashing import sha256_json
from src.utils.logging import setup_logging
from src.utils.paths import ensure_dir


def run_ingestion(
    condition: str | None = None,
    full_refresh: bool = False,
    max_pages: int | None = None,
    profile: str = "default",
    config: ProjectConfig | None = None,
) -> IngestionManifest:
    log = setup_logging()
    if profile == "full-catalog" and condition:
        raise ValueError(
            "The full-catalog profile snapshots all conditions worldwide and "
            f"cannot be combined with a condition filter (got {condition!r}); "
            "use the default profile for condition-scoped ingestion."
        )
    cfg = config or get_config()
    manifests_dir = cfg.paths.bronze_manifests

    profile_obj = None
    if profile == "full-catalog":
        pass  # all-conditions snapshot; no indication scoping applies
    elif profile and profile != "default":
        profile_obj = load_indication_profile(profile)
        if condition is None:
            condition = profile_obj.query.condition
    elif condition is None:
        # Resolve via the configured default indication profile
        default_prof = cfg.scope.get("default_indication_profile", "adrd")
        try:
            profile_obj = load_indication_profile(default_prof)
            condition = profile_obj.query.condition
        except Exception:
            pass

    if condition is None and profile != "full-catalog":
        raise ValueError(
            "No condition query resolved: pass --condition or --profile, or ensure "
            "the default indication profile exists under config/indications/."
        )

    with CTGClient(cfg.api) as client:
        params = client.build_params(condition=condition)
        if profile_obj and profile_obj.query.advanced_filter:
            params["filter.advanced"] = profile_obj.query.advanced_filter

        query_hash = sha256_json({"endpoint": cfg.api.studies_url, "params": params})

        if not full_refresh:
            reusable = find_reusable_run(
                manifests_dir, query_hash, cfg.ingestion.reuse_window_hours
            )
            if reusable is not None:
                log.info(
                    "Incremental mode: reusing completed run {} (started {}); "
                    "use --full-refresh to force a new snapshot.",
                    reusable.ingestion_run_id,
                    reusable.started_at_utc,
                )
                return reusable

        run_id = new_run_id()
        run_dir = cfg.paths.bronze_api_responses / f"run_id={run_id}"
        ensure_dir(run_dir)

        manifest = IngestionManifest(
            ingestion_run_id=run_id,
            query_hash=query_hash,
            endpoint=cfg.api.studies_url,
            condition=params.get("query.cond"),
            indication_profile=profile_obj.indication_id if profile_obj else None,
            params=params,
            mode="full_refresh" if full_refresh else "incremental",
            profile=profile,
            status="running",
            started_at_utc=utc_now(),
        )
        write_manifest(manifests_dir, manifest)
        log.info("Starting ingestion run {} against {}", run_id, cfg.api.studies_url)

        quarantined: list[QuarantineRecord] = []
        last_next_token: str | None = None
        try:
            for page in iter_pages(client, params, max_pages=max_pages):
                page_path = run_dir / f"page={page.page_number:05d}.json"
                page_path.write_text(page.raw_text, encoding="utf-8")
                envelope = validate_page(page.payload)
                if envelope.totalCount is not None:
                    manifest.total_count_reported = envelope.totalCount
                manifest.record_count += len(envelope.studies)
                manifest.page_count += 1
                last_next_token = envelope.nextPageToken
                quarantined.extend(screen_studies(envelope.studies, page.page_number))
                log.info(
                    "Saved page {} ({} studies, {} total so far)",
                    page.page_number,
                    len(envelope.studies),
                    manifest.record_count,
                )
            manifest.status = "partial" if last_next_token else "success"
            if manifest.status == "partial":
                log.warning(
                    "Run stopped by --max-pages before the API was exhausted; "
                    "marked 'partial' and excluded from reuse and downstream metrics."
                )
        except Exception as exc:
            manifest.status = "failed"
            manifest.error = f"{type(exc).__name__}: {exc}"
            log.error("Ingestion run {} failed: {}", run_id, manifest.error)
            raise
        finally:
            manifest.ended_at_utc = utc_now()
            manifest.quarantined_record_count = len(quarantined)
            write_manifest(manifests_dir, manifest)
            write_summary(manifests_dir, manifest)
            if quarantined:
                report = write_quarantine_report(cfg.paths.quarantine, run_id, quarantined)
                log.warning("{} records quarantined; report: {}", len(quarantined), report)

    log.info(
        "Run {} finished: status={} pages={} records={} quarantined={} total_reported={}",
        manifest.ingestion_run_id,
        manifest.status,
        manifest.page_count,
        manifest.record_count,
        manifest.quarantined_record_count,
        manifest.total_count_reported,
    )
    return manifest
