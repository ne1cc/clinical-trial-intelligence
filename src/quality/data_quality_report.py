"""Assemble the human-readable data-quality report (Markdown).

Pulls run reliability from the warehouse, cross-layer reconciliation, and
the latest schema-drift result into `reports/data_quality_report.md`.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import duckdb
from loguru import logger

from src.config import ProjectConfig, get_config
from src.ingest.snapshot_manifest import load_manifests
from src.quality.phi_scanner import scan_silver_entity
from src.quality.reconciliation import run_reconciliation
from src.quality.schema_drift import check_drift
from src.utils.dates import utc_now_iso

REPORT_PATH = Path("reports/data_quality_report.md")


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _reliability_rows(cfg: ProjectConfig) -> list[dict]:
    if not cfg.paths.duckdb.exists():
        return []
    con = duckdb.connect(str(cfg.paths.duckdb), read_only=True)
    try:
        cursor = con.execute(
            """
            select ingestion_run_id, snapshot_date, status, page_count,
                   manifest_record_count, trial_row_count,
                   manifest_reconciled_flag, unique_nct_flag,
                   quarantined_record_count, flagged_record_share,
                   usable_location_share, low_confidence_condition_share
            from main_marts.mart_data_reliability
            order by snapshot_date desc, ingestion_run_id desc
            """
        )
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()


def _run_phi_scan(cfg: ProjectConfig) -> dict | None:
    import pandas as pd

    trials_dir = cfg.paths.silver / "silver_trials"
    if not trials_dir.exists():
        return None
    parquet_files = list(trials_dir.glob("*.parquet"))
    if not parquet_files:
        return None

    df = pd.read_parquet(trials_dir)
    text_fields = ["brief_title", "official_title", "eligibility_criteria_text"]
    cols = ["nct_id"] + [f for f in text_fields if f in df.columns]
    records = df[cols].where(df[cols].notna(), None).to_dict("records")
    summary = scan_silver_entity(records, text_fields)
    return {
        "total_records_scanned": summary.total_records_scanned,
        "total_findings": summary.total_findings,
        "findings_by_type": summary.findings_by_type,
        "affected_nct_ids": summary.affected_nct_ids[:20],
        "status": summary.status,
    }


def build_report(cfg: ProjectConfig | None = None, output_path: Path | None = None) -> Path:
    cfg = cfg or get_config()
    output = output_path or REPORT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# Data Quality Report",
        "",
        f"Generated: {utc_now_iso()} (UTC)",
        "",
        "Scope: public ClinicalTrials.gov registry snapshots taken by this",
        "project. Quality findings describe registry listings, not trial",
        "conduct or outcomes.",
        "",
        "## Ingestion run reliability",
        "",
    ]

    reliability = _reliability_rows(cfg)
    if reliability:
        headers = [
            "run", "snapshot date", "status", "pages", "manifest records",
            "silver rows", "reconciled", "unique NCT", "quarantined",
            "flagged share", "usable location share", "low-confidence cond. share",
        ]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + " --- |" * len(headers))
        for row in reliability:
            lines.append(
                "| "
                + " | ".join(
                    _fmt(row[key])
                    for key in (
                        "ingestion_run_id", "snapshot_date", "status", "page_count",
                        "manifest_record_count", "trial_row_count",
                        "manifest_reconciled_flag", "unique_nct_flag",
                        "quarantined_record_count", "flagged_record_share",
                        "usable_location_share", "low_confidence_condition_share",
                    )
                )
                + " |"
            )
    else:
        lines.append("_Warehouse not built yet — run `make dbt-run` first._")

    lines += ["", "## Cross-layer reconciliation", ""]
    checks = run_reconciliation(cfg)
    lines.append("| check | run | expected | actual | passed | note |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for check in checks:
        c = asdict(check)
        lines.append(
            f"| {c['check']} | {_fmt(c['run_id'])} | {_fmt(c['expected'])}"
            f" | {_fmt(c['actual'])} | {_fmt(c['passed'])} | {c['note']} |"
        )
    failed = sum(1 for c in checks if not c.passed)
    lines.append("")
    lines.append(
        f"**{len(checks) - failed}/{len(checks)} reconciliation checks passed.**"
    )

    lines += ["", "## Schema drift", ""]
    success_runs = [
        m for m in load_manifests(cfg.paths.bronze_manifests) if m.status == "success"
    ]
    if success_runs:
        latest = max(success_runs, key=lambda m: m.ingestion_run_id)
        drift = check_drift(latest.ingestion_run_id, cfg=cfg)
        lines.append(f"- Run checked: `{drift['run_id']}`")
        lines.append(f"- Status: **{drift['status']}**")
        lines.append(f"- Observed field paths: {drift['observed_path_count']}")
        if drift.get("added_paths") or drift.get("removed_paths"):
            lines.append(f"- Added: {json.dumps(drift['added_paths'])}")
            lines.append(f"- Removed: {json.dumps(drift['removed_paths'])}")
    else:
        lines.append("_No complete ingestion runs to check._")

    lines += ["", "## PHI/PII compliance scan", ""]
    phi_summary = _run_phi_scan(cfg)
    if phi_summary:
        lines.append(f"- Records scanned: {phi_summary['total_records_scanned']}")
        lines.append(f"- Status: **{phi_summary['status']}**")
        if phi_summary["total_findings"] > 0:
            lines.append(f"- Findings: {phi_summary['total_findings']}")
            lines.append(f"- Affected studies: {len(phi_summary['affected_nct_ids'])}")
            lines.append("- By type:")
            for etype, count in sorted(
                phi_summary["findings_by_type"].items(), key=lambda x: -x[1]
            ):
                lines.append(f"  - {etype}: {count}")
        else:
            lines.append("- No PHI/PII patterns detected in scanned free-text fields.")
    else:
        lines.append("_Silver data not available for PHI scan._")

    lines += [
        "",
        "## Interpretation guardrails",
        "",
        "- Counts are registry listings, not patient availability.",
        "- Snapshot-transition metrics stay at zero until this project has",
        "  accrued multiple snapshots; registry-date proxies are labeled.",
        "- Facility identity is best-effort text matching; no site-capacity",
        "  or performance claims are made.",
        "",
    ]

    output.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Data quality report written to {}", output)
    return output
