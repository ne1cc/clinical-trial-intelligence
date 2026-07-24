"""Parquet export for silver entities: data/silver/<entity>/run_id=<id>.parquet."""

from pathlib import Path

import pandas as pd

from src.utils.paths import ensure_dir


def export_entity(
    rows: list[dict], entity_name: str, run_id: str, silver_dir: Path
) -> tuple[Path, int]:
    entity_dir = ensure_dir(silver_dir / entity_name)
    path = entity_dir / f"run_id={run_id}.parquet"
    frame = pd.DataFrame(rows)
    frame.to_parquet(path, index=False)
    return path, len(frame)
