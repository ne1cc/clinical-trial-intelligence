from pathlib import Path

import pandas as pd

from src.quality.profiling import profile_entity
from src.quality.schema_drift import collect_field_paths


def test_collect_field_paths():
    node = {
        "protocolSection": {"statusModule": {"overallStatus": "RECRUITING"}},
        "conditions": ["Alzheimer", "Dementia"],
    }
    paths = collect_field_paths(node)
    assert "protocolSection" in paths
    assert "protocolSection.statusModule" in paths
    assert "protocolSection.statusModule.overallStatus" in paths
    assert "conditions" in paths


def test_profile_entity(tmp_path: Path):
    parquet_path = tmp_path / "entity.parquet"
    df = pd.DataFrame(
        [{"nct_id": "NCT00000001", "val": 10}, {"nct_id": "NCT00000002", "val": None}]
    )
    df.to_parquet(parquet_path, index=False)
    prof = profile_entity(parquet_path)
    assert prof["row_count"] == 2
    assert prof["column_count"] == 2
    assert prof["distinct_nct_ids"] == 2
    assert prof["null_rates"]["val"] == 0.5


def test_profile_entity_all_null_column(tmp_path: Path):
    parquet_path = tmp_path / "entity.parquet"
    df = pd.DataFrame([{"nct_id": "NCT00000001", "val": None}])
    df.to_parquet(parquet_path, index=False)
    prof = profile_entity(parquet_path)
    assert prof["null_rates"]["val"] == 1.0
    assert prof["null_rates"]["nct_id"] == 0.0
    assert prof["distinct_nct_ids"] == 1


def test_profile_entity_empty_file(tmp_path: Path):
    parquet_path = tmp_path / "entity.parquet"
    pd.DataFrame(columns=["nct_id", "val"]).to_parquet(parquet_path, index=False)
    prof = profile_entity(parquet_path)
    assert prof["row_count"] == 0
    assert prof["column_count"] == 2
    assert prof["null_rates"] == {}
    assert prof["distinct_nct_ids"] == 0


def test_profile_entity_without_nct_id(tmp_path: Path):
    parquet_path = tmp_path / "entity.parquet"
    pd.DataFrame([{"a": 1}, {"a": None}]).to_parquet(parquet_path, index=False)
    prof = profile_entity(parquet_path)
    assert prof["row_count"] == 2
    assert prof["column_count"] == 1
    assert prof["null_rates"]["a"] == 0.5
    assert "distinct_nct_ids" not in prof
