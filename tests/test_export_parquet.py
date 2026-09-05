from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.transform.build_silver_entities import ENTITY_NAMES
from src.transform.export_parquet import (
    ENTITY_ARROW_SCHEMAS,
    ENTITY_COLUMNS,
    SilverRunWriter,
    export_entity,
)


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


def test_entity_arrow_schemas_match_entity_columns():
    for entity, columns in ENTITY_COLUMNS.items():
        assert ENTITY_ARROW_SCHEMAS[entity].names == columns


def test_entity_names_cover_every_exported_entity():
    # build_silver_for_run logs and returns counts[entity] for each ENTITY_NAMES
    # entry, so an entity in one list but not the other surfaces only as a
    # KeyError at the end of a multi-hour full-catalog run.
    assert set(ENTITY_NAMES) == set(ENTITY_COLUMNS)


def test_writer_rejects_a_number_in_a_string_column(tmp_path: Path):
    # Columns absent from _NON_STRING_ARROW_TYPES are pinned to string, and
    # PyArrow refuses to coerce an int into one rather than silently widening
    # the schema. The whole fixed-schema design rests on that failing loudly.
    writer = SilverRunWriter("r1", tmp_path, flush_rows=1)
    with pytest.raises(pa.ArrowTypeError):
        writer.add_rows({"silver_trial_locations": [{"zip_code": 2114}]})
    writer.discard()
    assert list((tmp_path / "silver_trial_locations").glob("*.parquet*")) == []


def test_writer_flushes_one_row_group_per_threshold(tmp_path: Path):
    def batch(i: int) -> list[dict]:
        return [{"ingestion_run_id": "r1", "nct_id": f"NCT{i:08d}"} for _ in range(50)]

    with SilverRunWriter("r1", tmp_path, flush_rows=50) as writer:
        for i in range(3):
            writer.add_rows({"silver_trials": batch(i)})

    pf = pq.ParquetFile(tmp_path / "silver_trials" / "run_id=r1.parquet")
    assert pf.metadata.num_row_groups == 3
    assert pf.metadata.num_rows == 150


def test_writer_schema_stable_across_mixed_chunks(tmp_path: Path):
    chunk_a = [
        {
            "ingestion_run_id": "r1",
            "nct_id": f"NCT{i:08d}",
            "enrollment_count": 100 + i,
            "has_results_flag": i % 2 == 0,
            "last_known_status": None,
        }
        for i in range(3)
    ]
    chunk_b = [
        {
            "ingestion_run_id": "r1",
            "nct_id": "NCT00000009",
            "enrollment_count": None,
            "has_results_flag": None,
            "last_known_status": None,
        }
    ]
    with SilverRunWriter("r1", tmp_path, flush_rows=2) as writer:
        writer.add_rows({"silver_trials": chunk_a})
        writer.add_rows({"silver_trials": chunk_b})

    path = tmp_path / "silver_trials" / "run_id=r1.parquet"
    schema = pq.read_schema(path)
    assert schema.field("enrollment_count").type == pa.float64()
    assert schema.field("has_results_flag").type == pa.bool_()
    assert schema.field("last_known_status").type == pa.string()
    df = pd.read_parquet(path)
    # float64 nulls round-trip as NaN (not None) through pandas/PyArrow
    enrollment = df["enrollment_count"].tolist()
    assert enrollment[:3] == [100.0, 101.0, 102.0]
    assert pd.isna(enrollment[3])
    # bool nullable column: None round-trips as None (pandas BooleanDtype)
    has_results = df["has_results_flag"].tolist()
    assert has_results[:3] == [True, False, True]
    assert has_results[3] is None or pd.isna(has_results[3])


def test_writer_drops_extra_keys_and_pins_column_order(tmp_path: Path):
    row = {"ingestion_run_id": "r1", "nct_id": "NCT00000001", "bogus": "x"}
    with SilverRunWriter("r1", tmp_path) as writer:
        writer.add_rows({"silver_trials": [row]})

    schema = pq.read_schema(tmp_path / "silver_trials" / "run_id=r1.parquet")
    assert schema.names == ENTITY_COLUMNS["silver_trials"]


def test_writer_close_writes_schema_only_files_for_unused_entities(tmp_path: Path):
    writer = SilverRunWriter("r1", tmp_path)
    writer.add_rows({"silver_trials": [{"ingestion_run_id": "r1", "nct_id": "NCT00000001"}]})
    counts = writer.close()

    assert counts["silver_trials"] == 1
    assert counts["silver_trial_conditions"] == 0
    path = tmp_path / "silver_trial_conditions" / "run_id=r1.parquet"
    con = duckdb.connect(":memory:")
    result = con.execute(f"select * from read_parquet('{path.as_posix()}')").fetchall()
    assert result == []
    assert [d[0] for d in con.description] == ENTITY_COLUMNS["silver_trial_conditions"]


def test_writer_discard_removes_partial_files(tmp_path: Path):
    writer = SilverRunWriter("r1", tmp_path, flush_rows=1)
    writer.add_rows({"silver_trials": [{"ingestion_run_id": "r1", "nct_id": "NCT00000001"}]})
    writer.discard()

    entity_dir = tmp_path / "silver_trials"
    assert not (entity_dir / "run_id=r1.parquet").exists()
    assert list(entity_dir.glob("*.tmp")) == []
