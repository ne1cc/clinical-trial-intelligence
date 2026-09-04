import json
from pathlib import Path

import pytest

from src.ingest.validate_api_payload import (
    PayloadValidationError,
    QuarantineRecord,
    screen_studies,
    validate_page,
    write_quarantine_report,
)


def test_validate_page_success():
    payload = {"studies": [{"protocolSection": {}}], "totalCount": 1, "nextPageToken": "token123"}
    page = validate_page(payload)
    assert len(page.studies) == 1
    assert page.totalCount == 1
    assert page.nextPageToken == "token123"


def test_validate_page_invalid():
    with pytest.raises(PayloadValidationError):
        validate_page("not a dict")


def test_screen_studies_detects_non_object_and_missing_or_invalid_nct():
    studies = [
        "invalid_string_not_dict",
        {"protocolSection": {"identificationModule": {}}},
        {"protocolSection": {"identificationModule": {"nctId": "INVALID123"}}},
        {"protocolSection": {"identificationModule": {"nctId": "NCT12345678"}}},
    ]
    quarantined = screen_studies(studies, page_number=1)
    assert len(quarantined) == 3
    assert quarantined[0].reason_code == "NOT_AN_OBJECT"
    assert quarantined[1].reason_code == "MISSING_NCT_ID"
    assert quarantined[2].reason_code == "INVALID_NCT_ID_FORMAT"
    assert quarantined[2].nct_id_raw == "INVALID123"


def test_write_quarantine_report(tmp_path: Path):
    records = [QuarantineRecord(page_number=1, study_index=0, reason_code="MISSING_NCT_ID")]
    report_path = write_quarantine_report(tmp_path, "run_123", records)
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["reason_code"] == "MISSING_NCT_ID"
