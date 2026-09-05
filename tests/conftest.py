import subprocess
from pathlib import Path

import pytest

CONFIG_YAML = """
api:
  base_url: "https://clinicaltrials.gov/api/v2"
paths:
  bronze_api_responses: "data/bronze/api_responses"
  bronze_manifests: "data/bronze/manifests"
  silver: "data/silver"
  gold: "data/gold"
  duckdb: "data/warehouse/clinical_trials.duckdb"
  quarantine: "data/quarantine"
ingestion:
  mode_default: "incremental"
  reuse_window_hours: 24
scope:
  refresh_cadence: "weekly"
"""


@pytest.fixture
def project_root_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "project_config.yml").write_text(CONFIG_YAML, encoding="utf-8")
    monkeypatch.setenv("CTI_PROJECT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_config_cache():
    from src.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


def materialize_with_checks(*, assets, asset_checks, run_config=None, raise_on_error=False):
    from dagster import Definitions

    defs = Definitions(assets=list(assets), asset_checks=list(asset_checks))
    job = defs.resolve_implicit_global_asset_job_def()
    return job.execute_in_process(run_config=run_config or {}, raise_on_error=raise_on_error)


def check_evaluation(result, check_name):
    for evaluation in result.get_asset_check_evaluations():
        if evaluation.check_name == check_name:
            return evaluation
    return None


@pytest.fixture(scope="session")
def dbt_manifest(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = Path(__file__).resolve().parents[1]
    dbt_dir = root / "dbt_clinical_trials"
    if not (dbt_dir / "profiles.yml").exists():
        subprocess.run(
            ["cp", str(dbt_dir / "profiles.yml.example"), str(dbt_dir / "profiles.yml")],
            check=True,
        )
    if (dbt_dir / "packages.yml").exists():
        subprocess.run(
            [
                "uv",
                "run",
                "dbt",
                "deps",
                "--project-dir",
                str(dbt_dir),
                "--profiles-dir",
                str(dbt_dir),
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
    subprocess.run(
        [
            "uv",
            "run",
            "dbt",
            "parse",
            "--project-dir",
            str(dbt_dir),
            "--profiles-dir",
            str(dbt_dir),
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    manifest = dbt_dir / "target" / "manifest.json"
    assert manifest.exists(), "dbt parse did not produce target/manifest.json"
    return manifest
