"""Trial similarity weight-configuration tests: config/seed consistency."""

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SIMILARITY_WEIGHTS_YML = ROOT / "config" / "similarity_weights.yml"
SEED_CSV = ROOT / "dbt_clinical_trials" / "seeds" / "similarity_score_weights.csv"


def load_similarity_config() -> dict:
    return yaml.safe_load(SIMILARITY_WEIGHTS_YML.read_text(encoding="utf-8"))


def load_seed_weights() -> dict[str, float]:
    with open(SEED_CSV, encoding="utf-8") as handle:
        return {row["component"]: float(row["weight"]) for row in csv.DictReader(handle)}


def test_similarity_weights_sum_to_one():
    weights = load_similarity_config()["similarity"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_yaml_weights_match_dbt_seed():
    yaml_weights = load_similarity_config()["similarity"]["weights"]
    assert yaml_weights == load_seed_weights()
