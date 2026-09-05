import pytest

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
