"""Typed access to config/project_config.yml with .env overrides.

All API query parameters live in YAML — never hard-coded in ingestion code.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from src.utils.paths import project_root, resolve_path


class HttpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timeout_seconds: float = 30.0
    max_retries: int = 5
    backoff_initial_seconds: float = 1.0
    backoff_max_seconds: float = 60.0
    retry_on_status: list[int] = [429, 500, 502, 503, 504]


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str
    studies_endpoint: str = "/studies"
    format: str = "json"
    page_size: int = 100
    count_total: bool = True
    query_params: dict[str, Any] = {}
    http: HttpConfig = HttpConfig()

    @property
    def studies_url(self) -> str:
        return self.base_url.rstrip("/") + self.studies_endpoint


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bronze_api_responses: Path
    bronze_manifests: Path
    silver: Path
    gold: Path
    duckdb: Path
    quarantine: Path


class IngestionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode_default: str = "incremental"
    reuse_window_hours: int = 24
    page_file_pattern: str = "run_id={run_id}/page={page:05d}.json"
    manifest_file_pattern: str = "manifest_{run_id}.json"


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api: ApiConfig
    paths: PathsConfig
    ingestion: IngestionConfig
    scope: dict[str, Any] = {}
    guardrails: dict[str, Any] = {}


class IndicationQueryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    condition: str
    advanced_filter: str | None = None


class IndicationProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    indication_id: str
    display_name: str
    description: str = ""
    query: IndicationQueryConfig
    taxonomy: dict[str, Any] = {}


def load_indication_profile(
    profile_name: str | None = None,
    profiles_dir: str | Path = "config/indications",
) -> IndicationProfile:
    """Load an indication profile by name (e.g. 'adrd', 'oncology_nsclc').

    If profile_name is None, falls back to CTI_INDICATION_PROFILE env var,
    scope.default_indication_profile in project config, or 'adrd'.
    """
    if profile_name is None:
        profile_name = os.getenv("CTI_INDICATION_PROFILE")
        if not profile_name:
            try:
                cfg = get_config()
                profile_name = cfg.scope.get("default_indication_profile", "adrd")
            except Exception:
                profile_name = "adrd"

    # Allow direct path or profile id
    path = Path(profile_name)
    if not path.exists():
        dir_path = project_root() / profiles_dir
        path = dir_path / f"{profile_name}.yml"
        if not path.exists():
            path = dir_path / f"{profile_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Indication profile '{profile_name}' not found at {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return IndicationProfile(**raw)


def list_indication_profiles(profiles_dir: str | Path = "config/indications") -> list[str]:
    """List available indication profile identifiers."""
    p_dir = project_root() / profiles_dir
    if not p_dir.exists():
        return []
    stems = {f.stem for f in p_dir.glob("*.yml")} | {f.stem for f in p_dir.glob("*.yaml")}
    return sorted(stems)


def load_config(config_path: str | Path | None = None) -> ProjectConfig:
    load_dotenv(project_root() / ".env")
    path = Path(config_path or os.getenv("CTI_CONFIG_PATH", "config/project_config.yml"))
    if not path.is_absolute():
        path = project_root() / path
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    api_raw = dict(raw["api"])
    http_raw = dict(api_raw.get("http", {}))
    if os.getenv("CTI_HTTP_TIMEOUT_SECONDS"):
        http_raw["timeout_seconds"] = float(os.environ["CTI_HTTP_TIMEOUT_SECONDS"])
    if os.getenv("CTI_MAX_RETRIES"):
        http_raw["max_retries"] = int(os.environ["CTI_MAX_RETRIES"])
    api_raw["http"] = http_raw

    paths_raw = {key: resolve_path(value) for key, value in raw["paths"].items()}

    return ProjectConfig(
        api=ApiConfig(**api_raw),
        paths=PathsConfig(**paths_raw),
        ingestion=IngestionConfig(**raw.get("ingestion", {})),
        scope=raw.get("scope", {}),
        guardrails=raw.get("guardrails", {}),
    )


@lru_cache(maxsize=1)
def get_config() -> ProjectConfig:
    return load_config()
