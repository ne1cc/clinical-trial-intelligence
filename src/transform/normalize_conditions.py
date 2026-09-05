"""Config-driven condition taxonomy mapping.

Deterministic, version-controlled YAML rules from indication profiles
(config/indications/*.yml). No runtime LLM classification. Groups are
evaluated in order; first match wins.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from src.utils.paths import project_root
from src.utils.text import normalize_text


@dataclass(frozen=True)
class ConditionMapping:
    condition_normalized: str | None
    condition_group: str
    relevance_flag: bool
    mapping_confidence: str  # high | medium | low

    @property
    def dementia_relevance_flag(self) -> bool:
        # Legacy silver column name; renaming requires a dbt downstream migration.
        return self.relevance_flag


@dataclass(frozen=True)
class TaxonomyGroup:
    condition_group: str
    relevance: bool
    exact: tuple[str, ...]
    substrings: tuple[str, ...]


@dataclass(frozen=True)
class ConditionTaxonomy:
    groups: tuple[TaxonomyGroup, ...]
    default_group: str
    default_relevance: bool

    def map_condition(self, condition_raw: object) -> ConditionMapping:
        cleaned = normalize_text(condition_raw)
        if cleaned is None:
            return ConditionMapping(
                None, self.default_group, self.default_relevance, "low"
            )
        for group in self.groups:
            if cleaned in group.exact:
                return ConditionMapping(
                    cleaned, group.condition_group, group.relevance, "high"
                )
        for group in self.groups:
            if any(term in cleaned for term in group.substrings):
                return ConditionMapping(
                    cleaned, group.condition_group, group.relevance, "medium"
                )
        return ConditionMapping(cleaned, self.default_group, self.default_relevance, "low")


def load_taxonomy(path_or_profile: str | Path | None = None) -> ConditionTaxonomy:
    """Load a condition taxonomy from an indication profile name or YAML path.

    Supports:
      - Profile name: e.g. "adrd", "oncology_nsclc" (config/indications/<name>.yml)
      - Direct path to a profile YAML containing a `taxonomy` block
    Defaults to the adrd profile when no argument is given.
    """
    if path_or_profile is None:
        path = project_root() / "config/indications/adrd.yml"
    else:
        path = Path(path_or_profile)
        if not path.is_absolute() and not path.exists():
            candidate = project_root() / f"config/indications/{path_or_profile}.yml"
            path = candidate if candidate.exists() else project_root() / path
    if not path.exists():
        raise FileNotFoundError(f"Indication profile not found at {path}")

    raw_dict = yaml.safe_load(path.read_text(encoding="utf-8"))

    # If the YAML is an IndicationProfile with a 'taxonomy' block:
    taxonomy_data = raw_dict.get("taxonomy", raw_dict)
    default_data = taxonomy_data.get("default", {})
    default_group = default_data.get("condition_group", "other")
    default_relevance = bool(default_data.get("relevance_flag", False))

    groups = tuple(
        TaxonomyGroup(
            condition_group=entry["condition_group"],
            relevance=bool(entry.get("relevance_flag", True)),
            exact=tuple(entry.get("exact") or []),
            substrings=tuple(entry.get("substrings") or []),
        )
        for entry in taxonomy_data.get("groups", [])
    )
    return ConditionTaxonomy(
        groups=groups,
        default_group=default_group,
        default_relevance=default_relevance,
    )


@lru_cache(maxsize=16)
def get_taxonomy(profile_or_path: str | None = None) -> ConditionTaxonomy:
    return load_taxonomy(profile_or_path)
