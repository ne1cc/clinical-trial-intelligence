"""Silver-entity profiling: row counts, null rates, distinct NCT IDs, and
reconciliation of trial rows against the ingestion manifest."""

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import ProjectConfig, get_config
from src.ingest.snapshot_manifest import load_manifests
from src.transform.build_silver_entities import ENTITY_NAMES
from src.utils.dates import utc_now_iso
from src.utils.logging import setup_logging
from src.utils.paths import ensure_dir


def profile_entity(path: Path) -> dict[str, Any]:
    frame = pd.read_parquet(path)
    null_rates = {} if frame.empty else (frame.isna().mean().round(4)).to_dict()
    profile = {
        "row_count": int(len(frame)),
        "column_count": int(frame.shape[1]),
        "null_rates": {k: float(v) for k, v in null_rates.items()},
    }
    if "nct_id" in frame.columns:
        profile["distinct_nct_ids"] = int(frame["nct_id"].nunique())
    return profile


def profile_run(run_id: str, config: ProjectConfig | None = None) -> dict[str, Any]:
    log = setup_logging()
    cfg = config or get_config()
    report: dict[str, Any] = {
        "ingestion_run_id": run_id,
        "profiled_at_utc": utc_now_iso(),
        "entities": {},
        "reconciliation": {},
    }
    for entity in ENTITY_NAMES:
        path = cfg.paths.silver / entity / f"run_id={run_id}.parquet"
        if path.exists():
            report["entities"][entity] = profile_entity(path)
        else:
            report["entities"][entity] = {"error": "missing_parquet"}

    manifest = next(
        (m for m in load_manifests(cfg.paths.bronze_manifests) if m.ingestion_run_id == run_id),
        None,
    )
    trials = report["entities"].get("silver_trials", {})
    if manifest and "row_count" in trials:
        report["reconciliation"] = {
            "manifest_record_count": manifest.record_count,
            "silver_trials_row_count": trials["row_count"],
            "distinct_nct_ids": trials.get("distinct_nct_ids"),
            "counts_match": manifest.record_count == trials["row_count"],
            "nct_ids_unique": trials.get("distinct_nct_ids") == trials["row_count"],
        }

    profiles_dir = ensure_dir(cfg.paths.silver / "_profiles")
    out_path = profiles_dir / f"profile_{run_id}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Profile for run {} written to {}", run_id, out_path)
    return report
