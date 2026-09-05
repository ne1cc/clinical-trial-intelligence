"""Parquet export for silver entities: data/silver/<entity>/run_id=<id>.parquet."""

from pathlib import Path

import pandas as pd

from src.utils.paths import ensure_dir

ENTITY_COLUMNS: dict[str, list[str]] = {
    "silver_trials": [
        "ingestion_run_id",
        "snapshot_timestamp_utc",
        "nct_id",
        "brief_title",
        "official_title",
        "study_type",
        "overall_status",
        "why_stopped",
        "last_known_status",
        "status_verified_date",
        "expanded_access_info",
        "start_date",
        "primary_completion_date",
        "completion_date",
        "study_first_post_date",
        "results_first_post_date",
        "last_update_post_date",
        "phase_raw",
        "phase_normalized",
        "enrollment_count",
        "enrollment_type",
        "lead_sponsor_name",
        "responsible_party_type",
        "healthy_volunteers",
        "minimum_age",
        "maximum_age",
        "sex",
        "eligibility_criteria_text",
        "has_results_flag",
        "source_json_hash",
        "record_quality_flag",
        "indication_profile",
    ],
    "silver_trial_conditions": [
        "ingestion_run_id",
        "nct_id",
        "source_json_hash",
        "condition_raw",
        "condition_normalized",
        "condition_group",
        "dementia_relevance_flag",
        "mapping_confidence",
    ],
    "silver_trial_interventions": [
        "ingestion_run_id",
        "nct_id",
        "source_json_hash",
        "intervention_name",
        "intervention_type",
        "intervention_description",
        "intervention_normalized",
    ],
    "silver_trial_sponsors": [
        "ingestion_run_id",
        "nct_id",
        "source_json_hash",
        "sponsor_name",
        "sponsor_role",
        "sponsor_class",
        "sponsor_normalized",
    ],
    "silver_trial_locations": [
        "ingestion_run_id",
        "nct_id",
        "source_json_hash",
        "facility_name",
        "facility_normalized",
        "city",
        "state",
        "state_normalized",
        "zip_code",
        "country",
        "geo_scope",
        "latitude",
        "longitude",
        "location_status",
        "us_location_flag",
        "usable_geography_flag",
    ],
    "silver_trial_outcomes": [
        "ingestion_run_id",
        "nct_id",
        "source_json_hash",
        "outcome_type",
        "outcome_index",
        "outcome_measure",
        "outcome_description",
        "time_frame",
    ],
}


def export_entity(
    rows: list[dict], entity_name: str, run_id: str, silver_dir: Path
) -> tuple[Path, int]:
    entity_dir = ensure_dir(silver_dir / entity_name)
    path = entity_dir / f"run_id={run_id}.parquet"
    if rows:
        frame = pd.DataFrame(rows)
    else:
        columns = ENTITY_COLUMNS.get(entity_name, ["ingestion_run_id", "nct_id"])
        frame = pd.DataFrame(columns=columns)
    frame.to_parquet(path, index=False)
    return path, len(frame)
