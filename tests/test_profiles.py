"""Tests for IndicationProfile, load_profile, and ProfileRegistry."""

from pathlib import Path

import pytest
import yaml

from src.profiles import (
    IndicationProfile,
    ProfileRegistry,
    SharedPaths,
    load_profile,
    load_shared_paths,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PROFILE_YAML = """\
profile:
  id: test_ind
  display_name: Test Indication
  ingest_only: true
  taxonomy: null
  score_weights: null

api:
  base_url: https://clinicaltrials.gov/api/v2
  query_params: {}
  http:
    timeout_seconds: 30
    max_retries: 5
    backoff_initial_seconds: 1
    backoff_max_seconds: 60
    retry_on_status: [429, 500, 502, 503, 504]

paths:
  bronze_api_responses: data/bronze/test_ind/api_responses
  bronze_manifests: data/bronze/test_ind/manifests
  silver: data/silver
  gold: data/gold
  duckdb: data/warehouse/x.duckdb
  quarantine: data/bronze/test_ind/manifests/quarantine

ingestion:
  mode_default: incremental
  reuse_window_hours: 24
  page_file_pattern: "run_id={run_id}/page={page:05d}.json"
  manifest_file_pattern: "manifest_{run_id}.json"

guardrails:
  disclaimer: test disclaimer
"""

SHARED_PATHS_YAML = """\
silver: data/silver
gold: data/gold
duckdb: data/warehouse/x.duckdb
"""


@pytest.fixture()
def tmp_profiles_dir(tmp_path: Path) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "test_ind.yml").write_text(MINIMAL_PROFILE_YAML)
    return profiles_dir


@pytest.fixture()
def tmp_shared_paths(tmp_path: Path) -> Path:
    p = tmp_path / "shared_paths.yml"
    p.write_text(SHARED_PATHS_YAML)
    return p


# ---------------------------------------------------------------------------
# SharedPaths
# ---------------------------------------------------------------------------


def test_load_shared_paths(tmp_shared_paths: Path) -> None:
    shared = load_shared_paths(tmp_shared_paths)
    assert isinstance(shared, SharedPaths)
    assert shared.silver.name == "silver"
    assert shared.gold.name == "gold"
    assert "x.duckdb" in str(shared.duckdb)


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------


def test_load_profile_ingest_only(tmp_profiles_dir: Path, tmp_shared_paths: Path) -> None:
    from src.profiles import load_shared_paths

    shared = load_shared_paths(tmp_shared_paths)
    profile = load_profile(tmp_profiles_dir / "test_ind.yml", shared=shared)

    assert isinstance(profile, IndicationProfile)
    assert profile.profile_id == "test_ind"
    assert profile.display_name == "Test Indication"
    assert profile.ingest_only is True
    assert profile.taxonomy is None
    assert profile.score_weights_path is None


def test_load_profile_bronze_paths_are_profile_scoped(
    tmp_profiles_dir: Path, tmp_shared_paths: Path
) -> None:
    from src.profiles import load_shared_paths

    shared = load_shared_paths(tmp_shared_paths)
    profile = load_profile(tmp_profiles_dir / "test_ind.yml", shared=shared)

    assert "test_ind" in str(profile.config.paths.bronze_api_responses)
    assert "test_ind" in str(profile.config.paths.bronze_manifests)


def test_load_profile_silver_gold_are_shared(
    tmp_profiles_dir: Path, tmp_shared_paths: Path
) -> None:
    from src.profiles import load_shared_paths

    shared = load_shared_paths(tmp_shared_paths)
    profile = load_profile(tmp_profiles_dir / "test_ind.yml", shared=shared)

    # Silver and gold come from shared_paths, not from the profile YAML.
    assert profile.config.paths.silver == shared.silver
    assert profile.config.paths.gold == shared.gold
    assert profile.config.paths.duckdb == shared.duckdb


# ---------------------------------------------------------------------------
# ProfileRegistry
# ---------------------------------------------------------------------------


def test_registry_discovers_profiles(tmp_profiles_dir: Path, tmp_shared_paths: Path) -> None:
    registry = ProfileRegistry(profiles_dir=tmp_profiles_dir, shared_paths_file=tmp_shared_paths)
    profiles = registry.all()
    assert len(profiles) == 1
    assert profiles[0].profile_id == "test_ind"


def test_registry_get_returns_correct_profile(
    tmp_profiles_dir: Path, tmp_shared_paths: Path
) -> None:
    registry = ProfileRegistry(profiles_dir=tmp_profiles_dir, shared_paths_file=tmp_shared_paths)
    profile = registry.get("test_ind")
    assert profile.profile_id == "test_ind"


def test_registry_get_unknown_raises(tmp_profiles_dir: Path, tmp_shared_paths: Path) -> None:
    registry = ProfileRegistry(profiles_dir=tmp_profiles_dir, shared_paths_file=tmp_shared_paths)
    with pytest.raises(KeyError, match="No profile 'nonexistent'"):
        registry.get("nonexistent")


def test_registry_multiple_profiles(tmp_profiles_dir: Path, tmp_shared_paths: Path) -> None:
    # Add a second profile
    second = dict(yaml.safe_load(MINIMAL_PROFILE_YAML))
    second["profile"] = dict(second["profile"])
    second["profile"]["id"] = "parkinsons"
    second["profile"]["display_name"] = "Parkinson's Disease"
    (tmp_profiles_dir / "parkinsons.yml").write_text(yaml.dump(second))

    registry = ProfileRegistry(profiles_dir=tmp_profiles_dir, shared_paths_file=tmp_shared_paths)
    ids = {p.profile_id for p in registry.all()}
    assert ids == {"test_ind", "parkinsons"}


def test_registry_active_includes_ingest_only(
    tmp_profiles_dir: Path, tmp_shared_paths: Path
) -> None:
    registry = ProfileRegistry(profiles_dir=tmp_profiles_dir, shared_paths_file=tmp_shared_paths)
    # ingest_only profiles appear in active() — orchestrator decides what to skip
    active = registry.active()
    assert any(p.ingest_only for p in active)


# ---------------------------------------------------------------------------
# indication_profile_id propagation through flatten_study
# ---------------------------------------------------------------------------


def test_flatten_study_stamps_profile_id() -> None:
    from src.transform.flatten_studies import flatten_study
    from src.transform.normalize_conditions import get_taxonomy
    from src.transform.normalize_locations import get_geography_rules

    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999"},
        }
    }
    rows = flatten_study(
        study,
        "run_test",
        "2026-01-01T00:00:00Z",
        get_taxonomy(),
        get_geography_rules(),
        indication_profile_id="parkinsons",
    )
    # Every entity row should carry the profile id
    assert rows["silver_trials"][0]["indication_profile_id"] == "parkinsons"
    # base dict propagates to child entities (conditions, interventions, etc.)
    for entity_name, entity_rows in rows.items():
        for row in entity_rows:
            assert row.get("indication_profile_id") == "parkinsons", (
                f"Missing indication_profile_id on {entity_name} row"
            )


def test_flatten_study_default_profile_id() -> None:
    """Callers that don't pass indication_profile_id get 'adrd' by default."""
    from src.transform.flatten_studies import flatten_study
    from src.transform.normalize_conditions import get_taxonomy
    from src.transform.normalize_locations import get_geography_rules

    study = {"protocolSection": {"identificationModule": {"nctId": "NCT11111111"}}}
    rows = flatten_study(
        study, "run1", "2026-01-01T00:00:00Z", get_taxonomy(), get_geography_rules()
    )
    assert rows["silver_trials"][0]["indication_profile_id"] == "adrd"


# ---------------------------------------------------------------------------
# Dedup key uses (nct_id, indication_profile_id)
# ---------------------------------------------------------------------------


def test_build_silver_dedup_key_uses_profile_id(tmp_path: Path) -> None:
    """The same NCT ID in two profiles is NOT deduplicated."""
    from src.transform.flatten_studies import flatten_study
    from src.transform.normalize_conditions import get_taxonomy
    from src.transform.normalize_locations import get_geography_rules

    # Verify that calling flatten_study with two different profile IDs produces
    # two different dedup keys (property test on the key logic itself).
    study = {"protocolSection": {"identificationModule": {"nctId": "NCT00000042"}}}
    rows_adrd = flatten_study(
        study,
        "r1",
        "2026-01-01T00:00:00Z",
        get_taxonomy(),
        get_geography_rules(),
        indication_profile_id="adrd",
    )
    rows_pk = flatten_study(
        study,
        "r1",
        "2026-01-01T00:00:00Z",
        get_taxonomy(),
        get_geography_rules(),
        indication_profile_id="parkinsons",
    )
    key_adrd = (
        rows_adrd["silver_trials"][0]["nct_id"],
        rows_adrd["silver_trials"][0]["indication_profile_id"],
    )
    key_pk = (
        rows_pk["silver_trials"][0]["nct_id"],
        rows_pk["silver_trials"][0]["indication_profile_id"],
    )
    assert key_adrd != key_pk
