import pytest

import src.ingest.extract_studies as extract_studies
from src.config import load_config


def test_run_ingestion_requires_resolvable_condition(monkeypatch):
    monkeypatch.setattr(
        extract_studies,
        "load_indication_profile",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no profile")),
    )
    with pytest.raises(ValueError, match="No condition query resolved"):
        extract_studies.run_ingestion(config=load_config())
