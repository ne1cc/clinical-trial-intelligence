"""Envelope validation and record screening for API pages.

Malformed records are never silently dropped — they become quarantine
records with reason codes, written alongside the run manifest.
"""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from src.utils.paths import ensure_dir

NCT_ID_PATTERN = re.compile(r"^NCT\d{8}$")


class PayloadValidationError(Exception):
    pass


class StudiesPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    studies: list[Any]
    nextPageToken: str | None = None
    totalCount: int | None = None


class QuarantineRecord(BaseModel):
    page_number: int
    study_index: int
    reason_code: str
    nct_id_raw: str | None = None


def validate_page(payload: Any) -> StudiesPage:
    try:
        return StudiesPage.model_validate(payload)
    except ValidationError as exc:
        raise PayloadValidationError(f"API page failed envelope validation: {exc}") from exc


def screen_studies(studies: list[Any], page_number: int) -> list[QuarantineRecord]:
    quarantined: list[QuarantineRecord] = []
    for index, study in enumerate(studies):
        if not isinstance(study, dict):
            quarantined.append(
                QuarantineRecord(
                    page_number=page_number, study_index=index, reason_code="NOT_AN_OBJECT"
                )
            )
            continue
        nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
        if not nct_id:
            quarantined.append(
                QuarantineRecord(
                    page_number=page_number, study_index=index, reason_code="MISSING_NCT_ID"
                )
            )
        elif not NCT_ID_PATTERN.match(str(nct_id)):
            quarantined.append(
                QuarantineRecord(
                    page_number=page_number,
                    study_index=index,
                    reason_code="INVALID_NCT_ID_FORMAT",
                    nct_id_raw=str(nct_id),
                )
            )
    return quarantined


def write_quarantine_report(
    quarantine_dir: Path, run_id: str, records: list[QuarantineRecord]
) -> Path:
    ensure_dir(quarantine_dir)
    path = quarantine_dir / f"quarantine_{run_id}.json"
    path.write_text(
        json.dumps([record.model_dump() for record in records], indent=2), encoding="utf-8"
    )
    return path
