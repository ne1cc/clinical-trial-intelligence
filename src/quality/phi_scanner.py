"""PHI/PII detection scanner for free-text clinical trial fields.

Regex-based detection of potential protected health information that may
leak into registry free-text fields (eligibility criteria, descriptions,
facility names). Designed as a compliance gate — flags findings for review
rather than auto-redacting, since ClinicalTrials.gov data is public.
"""

import re
from dataclasses import dataclass
from enum import StrEnum


class PhiEntityType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    MRN = "mrn"
    PERSON_NAME = "person_name"
    STREET_ADDRESS = "street_address"
    URL_WITH_PARAMS = "url_with_params"


@dataclass(frozen=True)
class PhiFinding:
    entity_type: PhiEntityType
    field_name: str
    nct_id: str
    masked_value: str
    context_snippet: str


_PATTERNS: list[tuple[PhiEntityType, re.Pattern]] = [
    (PhiEntityType.EMAIL, re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )),
    (PhiEntityType.SSN, re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    )),
    (PhiEntityType.PHONE, re.compile(
        r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
    )),
    (PhiEntityType.MRN, re.compile(
        r"\b(?:MRN|medical\s+record\s*(?:number|no|#|num))\s*[:#]?\s*\d{4,}\b",
        re.IGNORECASE,
    )),
    (PhiEntityType.STREET_ADDRESS, re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:St|Street|Ave|Avenue|Blvd|Boulevard"
        r"|Dr|Drive|Rd|Road|Ln|Lane|Way|Ct|Court|Pl|Place|Cir|Circle)\b"
        r"(?:\s*[,.]?\s*(?:Suite|Ste|Apt|Unit)\s*\d+)?\b",
        re.IGNORECASE,
    )),
    (PhiEntityType.URL_WITH_PARAMS, re.compile(
        r"https?://\S+[?&](?:patient|subject|participant|name|email|phone)=\S+",
        re.IGNORECASE,
    )),
]

_NAME_CONTEXT = re.compile(
    r"\b(?i:contact|call|reach|email|phone|fax|attention|attn|c/o)\s*[:\-]?\s*"
    r"(?:(?:Dr|Prof|Mr|Mrs|Ms)\.?\s+)?"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b"
)

_SAFE_PHONE_CONTEXTS = re.compile(
    r"\b(?:enrollment|sample|score|count|size|dose|mg|ml|kg|cm|mm"
    r"|NCT\d+|N=\d+|n\s*=\s*\d+)\b",
    re.IGNORECASE,
)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "***"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _extract_context(text: str, match_start: int, match_end: int, window: int = 40) -> str:
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    snippet = text[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def scan_text(text: str, field_name: str, nct_id: str) -> list[PhiFinding]:
    if not text or not isinstance(text, str):
        return []

    findings: list[PhiFinding] = []

    for entity_type, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            matched = match.group(0)

            if entity_type == PhiEntityType.PHONE:
                preceding = text[max(0, match.start() - 30):match.start()]
                if _SAFE_PHONE_CONTEXTS.search(preceding):
                    continue
                digits = re.sub(r"\D", "", matched)
                if len(digits) < 10:
                    continue

            findings.append(
                PhiFinding(
                    entity_type=entity_type,
                    field_name=field_name,
                    nct_id=nct_id,
                    masked_value=_mask(matched),
                    context_snippet=_extract_context(text, match.start(), match.end()),
                )
            )

    for match in _NAME_CONTEXT.finditer(text):
        name = match.group(1)
        if name.lower() in ("inclusion criteria", "exclusion criteria", "main inclusion"):
            continue
        findings.append(
            PhiFinding(
                entity_type=PhiEntityType.PERSON_NAME,
                field_name=field_name,
                nct_id=nct_id,
                masked_value=_mask(name),
                context_snippet=_extract_context(text, match.start(), match.end()),
            )
        )

    return findings


def scan_study_fields(
    nct_id: str, fields: dict[str, str | None]
) -> list[PhiFinding]:
    findings: list[PhiFinding] = []
    for field_name, value in fields.items():
        if value:
            findings.extend(scan_text(value, field_name, nct_id))
    return findings


@dataclass
class PhiScanSummary:
    total_records_scanned: int
    total_findings: int
    findings_by_type: dict[str, int]
    affected_nct_ids: list[str]
    status: str

    @property
    def is_clean(self) -> bool:
        return self.total_findings == 0


def scan_silver_entity(
    records: list[dict],
    text_fields: list[str],
    nct_id_field: str = "nct_id",
) -> PhiScanSummary:
    all_findings: list[PhiFinding] = []
    affected: set[str] = set()

    for record in records:
        nct_id = record.get(nct_id_field, "unknown")
        fields = {f: record.get(f) for f in text_fields if record.get(f)}
        record_findings = scan_study_fields(nct_id, fields)
        if record_findings:
            all_findings.extend(record_findings)
            affected.add(nct_id)

    by_type: dict[str, int] = {}
    for f in all_findings:
        by_type[f.entity_type.value] = by_type.get(f.entity_type.value, 0) + 1

    return PhiScanSummary(
        total_records_scanned=len(records),
        total_findings=len(all_findings),
        findings_by_type=by_type,
        affected_nct_ids=sorted(affected),
        status="CLEAN" if not all_findings else "FINDINGS_DETECTED",
    )
