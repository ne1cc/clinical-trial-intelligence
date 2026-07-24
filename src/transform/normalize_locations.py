"""Config-driven U.S. geography normalization (config/geography_rules.yml).

All records are preserved; non-U.S. or unmappable geographies are flagged,
never dropped. No facility geocoding in MVP.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from src.utils.paths import project_root
from src.utils.text import normalize_text

DEFAULT_RULES_PATH = "config/geography_rules.yml"


@dataclass(frozen=True)
class LocationNormalization:
    state_normalized: str  # two-char abbreviation or UNKNOWN
    us_location_flag: bool
    usable_geography_flag: bool
    geo_scope: str  # facility | city | state | country | unknown


@dataclass(frozen=True)
class GeographyRules:
    unknown_value: str
    us_country_values: frozenset[str]
    valid_state_abbreviations: frozenset[str]
    state_name_to_abbreviation: dict[str, str]

    def normalize_state(self, state_raw: object) -> str:
        cleaned = normalize_text(state_raw)
        if cleaned is None:
            return self.unknown_value
        upper = cleaned.upper()
        if upper in self.valid_state_abbreviations:
            return upper
        return self.state_name_to_abbreviation.get(cleaned, self.unknown_value)

    def is_us_country(self, country_raw: object) -> bool:
        cleaned = normalize_text(country_raw)
        if cleaned is None:
            return False
        return cleaned in {normalize_text(v) for v in self.us_country_values}

    def normalize_location(
        self,
        facility: object,
        city: object,
        state: object,
        country: object,
    ) -> LocationNormalization:
        state_normalized = self.normalize_state(state)
        us_flag = self.is_us_country(country)
        usable = us_flag and state_normalized != self.unknown_value
        if facility:
            geo_scope = "facility"
        elif city:
            geo_scope = "city"
        elif state_normalized != self.unknown_value:
            geo_scope = "state"
        elif country:
            geo_scope = "country"
        else:
            geo_scope = "unknown"
        return LocationNormalization(
            state_normalized=state_normalized,
            us_location_flag=us_flag,
            usable_geography_flag=usable,
            geo_scope=geo_scope,
        )


def load_geography_rules(path: str | Path | None = None) -> GeographyRules:
    rules_path = Path(path) if path else project_root() / DEFAULT_RULES_PATH
    raw = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    return GeographyRules(
        unknown_value=raw["unknown_value"],
        us_country_values=frozenset(raw["us_country_values"]),
        valid_state_abbreviations=frozenset(raw["valid_state_abbreviations"]),
        state_name_to_abbreviation=dict(raw["state_name_to_abbreviation"]),
    )


@lru_cache(maxsize=1)
def get_geography_rules() -> GeographyRules:
    return load_geography_rules()
