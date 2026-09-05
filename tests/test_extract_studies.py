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


def test_whitespace_only_condition_rejected(monkeypatch):
    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", NoNetworkClient)
    for bad in ("   ", ""):
        with pytest.raises(ValueError, match="whitespace"):
            run_ingestion(condition=bad)


def test_whitespace_only_condition_rejected_before_profile_guard(monkeypatch):
    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", NoNetworkClient)
    with pytest.raises(ValueError, match="whitespace"):
        run_ingestion(condition="   ", profile="full-catalog")


def test_condition_is_stripped_before_use(monkeypatch):
    captured = []

    class CaptureClient:
        def __init__(self, api):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def build_params(self, condition=None):
            captured.append(condition)
            raise Sentinel("stop before any IO")

    monkeypatch.setattr("src.ingest.extract_studies.CTGClient", CaptureClient)
    with pytest.raises(Sentinel):
        run_ingestion(condition="  Alzheimer Disease  ")
    assert captured == ["Alzheimer Disease"]
