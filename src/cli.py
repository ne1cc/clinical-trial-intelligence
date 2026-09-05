"""Command-line entry point: python -m src.cli <command>."""

import argparse

from src.utils.logging import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description=(
            "Clinical Trial Access & Recruitment Competition Intelligence pipeline. "
            "Public-registry-based planning signals only — not a recruitment forecast."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "ingest", help="Snapshot studies from ClinicalTrials.gov API v2 into bronze."
    )
    ingest.add_argument(
        "--profile",
        "--module",
        dest="profile",
        default="default",
        help="Ingestion profile: 'full-catalog' fetches all conditions worldwide "
        "into a separate bronze tree (config/full_catalog_config.yml); any other "
        "value selects an indication profile/module (e.g. 'adrd', 'oncology_nsclc'); "
        "'default' uses the configured default indication profile.",
    )
    ingest.add_argument(
        "--condition",
        default=None,
        help='Condition query (default: query.cond from profile/config, e.g. "Alzheimer Disease").',
    )
    ingest.add_argument(
        "--full-refresh",
        action="store_true",
        help="Force a new snapshot even if a recent completed run exists for this query.",
    )
    ingest.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page cap for smoke tests (partial runs stay marked incomplete-by-cap).",
    )

    transform = subparsers.add_parser(
        "transform", help="Flatten bronze JSON runs into normalized silver Parquet entities."
    )
    transform.add_argument(
        "--profile",
        "--module",
        dest="profile",
        default=None,
        help="Indication profile/module for taxonomy mapping (e.g. 'adrd', 'oncology_nsclc').",
    )
    transform.add_argument(
        "--run-id",
        default=None,
        help="Transform one specific run (default: all completed runs not yet transformed).",
    )
    transform.add_argument(
        "--force",
        action="store_true",
        help="Rebuild silver outputs even if they already exist.",
    )

    quality = subparsers.add_parser(
        "quality-report",
        help="Build the Markdown data-quality report (reliability, reconciliation, drift).",
    )
    quality.add_argument(
        "--update-schema-baseline",
        action="store_true",
        help="Accept the latest run's structure as the new schema baseline.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log = setup_logging()

    if args.command == "ingest":
        from src.config import load_config
        from src.ingest.extract_studies import run_ingestion

        try:
            config = (
                load_config("config/full_catalog_config.yml")
                if args.profile == "full-catalog"
                else None
            )
            manifest = run_ingestion(
                condition=args.condition,
                profile=args.profile,
                full_refresh=args.full_refresh,
                max_pages=args.max_pages,
                config=config,
            )
        except Exception as exc:
            log.error("Ingestion failed: {}", exc)
            return 1
        return 0 if manifest.status in ("success", "partial") else 1

    if args.command == "transform":
        from src.quality.profiling import profile_run
        from src.transform.build_silver_entities import run_transform

        try:
            processed = run_transform(
                run_id=args.run_id,
                force=args.force,
                profile=args.profile,
            )
            for run_id in processed:
                profile_run(run_id)
        except Exception as exc:
            log.error("Transform failed: {}", exc)
            return 1
        return 0

    if args.command == "quality-report":
        from src.config import get_config
        from src.ingest.snapshot_manifest import load_manifests
        from src.quality.data_quality_report import build_report
        from src.quality.schema_drift import check_drift

        try:
            if args.update_schema_baseline:
                cfg = get_config()
                success = [
                    m for m in load_manifests(cfg.paths.bronze_manifests) if m.status == "success"
                ]
                if success:
                    latest = max(success, key=lambda m: m.ingestion_run_id)
                    check_drift(latest.ingestion_run_id, update_baseline=True, cfg=cfg)
            build_report()
        except Exception as exc:
            log.error("Quality report failed: {}", exc)
            return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
