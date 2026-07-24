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
