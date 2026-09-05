import pytest

import src.ingest.extract_studies as extract_studies
from src.config import load_config
from src.ingest.extract_studies import run_ingestion


class Sentinel(Exception):
    pass


class NoNetworkClient:
    """Stands in for CTGClient; entering it means the guard did not fire."""

    def __init__(self, api):
        pass

    def __enter__(self):
        raise Sentinel("CTGClient entered")

    def __exit__(self, *args):
        return False


def test_full_catalog_profile_rejects_condition(monkeypatch):
    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", NoNetworkClient)
    with pytest.raises(ValueError, match="full-catalog"):
        run_ingestion(condition="Cancer", profile="full-catalog")


def test_default_profile_still_accepts_condition(monkeypatch):
    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", NoNetworkClient)
    with pytest.raises(Sentinel):
        run_ingestion(condition="Alzheimer Disease")


def test_run_ingestion_requires_resolvable_condition(monkeypatch):
    monkeypatch.setattr(
        extract_studies,
        "load_indication_profile",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no profile")),
    )
    with pytest.raises(ValueError, match="No condition query resolved"):
        run_ingestion(config=load_config())
