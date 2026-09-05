"""Silver-entity profiling: row counts, null rates, distinct NCT IDs, and
reconciliation of trial rows against the ingestion manifest."""

import json
from pathlib import Path

import duckdb

from src.config import ProjectConfig, get_config
from src.ingest.snapshot_manifest import load_manifests
from src.transform.build_silver_entities import ENTITY_NAMES
from src.utils.dates import utc_now_iso
from src.utils.logging import setup_logging
from src.utils.paths import ensure_dir


def profile_entity(path: Path) -> dict:
    # Single streaming aggregate over the parquet file: profiling must not
    # materialize full-catalog entity tables (hundreds of millions of rows
    # for locations/outcomes) in memory.
    table = f"read_parquet('{path.as_posix()}')"
    con = duckdb.connect(":memory:")
    try:
        columns = [
            row[0] for row in con.execute(f"describe select * from {table}").fetchall()
        ]
        aggregates = ["count(*)"] + [f'count("{col}")' for col in columns]
        if "nct_id" in columns:
            aggregates.append('count(distinct "nct_id")')
        stats = con.execute(f"select {', '.join(aggregates)} from {table}").fetchone()
    finally:
        con.close()

    row_count = int(stats[0])
    profile: dict = {
        "row_count": row_count,
        "column_count": len(columns),
        "null_rates": {},
    }
    if row_count:
        profile["null_rates"] = {
            col: round(1.0 - non_null / row_count, 4)
            for col, non_null in zip(columns, stats[1 : 1 + len(columns)], strict=True)
        }
    if "nct_id" in columns:
        profile["distinct_nct_ids"] = int(stats[-1])
    return profile


def profile_run(run_id: str, config: ProjectConfig | None = None) -> dict:
    log = setup_logging()
    cfg = config or get_config()
    report: dict = {
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
