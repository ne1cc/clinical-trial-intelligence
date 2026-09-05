"""Hermetic end-to-end test: fixture bronze snapshot through the full dbt graph.

The session fixture in tests/conftest.py builds one warehouse from
tests/fixtures/bronze_snapshot; every test in this module asserts against it.
No network, no real API, everything under tmp_path_factory.
"""

from pathlib import Path

FIXTURE_RUN_ID = "20260901T120000Z_fixture01"


def test_dbt_build_passes_on_fixture_snapshot(fixture_project_root: Path) -> None:
    # The session fixture asserts dbt's exit code before returning; this pins
    # the artifacts the later assertions read.
    assert (fixture_project_root / "data/warehouse/clinical_trials.duckdb").exists()
    assert (fixture_project_root / "dbt_target/manifest.json").exists()
