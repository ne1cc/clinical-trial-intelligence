from pathlib import Path

import duckdb
import pandas as pd

from src.transform.export_parquet import ENTITY_COLUMNS, export_entity


def test_export_entity_with_rows(tmp_path: Path):
    rows = [{"ingestion_run_id": "r1", "nct_id": "NCT00000001", "brief_title": "Trial 1"}]
    path, count = export_entity(rows, "silver_trials", "r1", tmp_path)
    assert path.exists()
    assert count == 1
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert df["nct_id"].iloc[0] == "NCT00000001"


def test_export_entity_empty_rows_creates_valid_parquet_for_duckdb(tmp_path: Path):
    for entity, expected_cols in ENTITY_COLUMNS.items():
        path, count = export_entity([], entity, "r_empty", tmp_path)
        assert path.exists()
        assert count == 0
        con = duckdb.connect(":memory:")
        result = con.execute(f"select * from read_parquet('{path.as_posix()}')").fetchall()
        assert result == []
        cols = [d[0] for d in con.description]
        assert cols == expected_cols
