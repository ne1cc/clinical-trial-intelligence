"""Rule-based structuring of free-text eligibility criteria.

Parses the eligibilityCriteria field from ClinicalTrials.gov API v2 into
structured inclusion/exclusion criterion entities with type classification.
No external NLP dependencies — uses regex section splitting and keyword
matching tuned to clinical trial registry language.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum


class CriterionType(StrEnum):
    AGE = "age"
    BIOMARKER = "biomarker"
    CONDITION = "condition"
    MEDICATION = "medication"
    PROCEDURE = "procedure"
    DEMOGRAPHIC = "demographic"
    CONSENT = "consent"
    LABORATORY = "laboratory"
    OTHER = "other"


class CriterionDirection(StrEnum):
    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"


@dataclass(frozen=True)
class StructuredCriterion:
    direction: CriterionDirection
    criterion_type: CriterionType
    text: str
    section_label: str = ""


@dataclass
class EligibilityParseResult:
    nct_id: str
    criteria: list[StructuredCriterion] = field(default_factory=list)
    parse_quality: str = "ok"

    @property
    def inclusion_count(self) -> int:
        return sum(1 for c in self.criteria if c.direction == CriterionDirection.INCLUSION)

    @property
    def exclusion_count(self) -> int:
        return sum(1 for c in self.criteria if c.direction == CriterionDirection.EXCLUSION)


_INCLUSION_HEADERS = re.compile(
    r"^(?:main\s+)?inclusion\s+criteria", re.IGNORECASE
)
_EXCLUSION_HEADERS = re.compile(
    r"^(?:main\s+)?exclusion\s+criteria", re.IGNORECASE
)
_SECTION_HEADER = re.compile(
    r"^(?:main\s+)?(inclusion|exclusion)\s+criteria\b[^\n]*:?\s*$", re.IGNORECASE
)
_SUBSECTION_HEADER = re.compile(
    r"^[A-Z][A-Za-z\s/'-]+(?:inclusion|exclusion)\s+criteria[^\n]*:?\s*$", re.IGNORECASE
)
_BULLET = re.compile(r"^\s*[*•\-]\s+")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")

_TYPE_PATTERNS: list[tuple[CriterionType, re.Pattern]] = [
    (CriterionType.BIOMARKER, re.compile(
        r"\b(?:MMSE|MoCA|CDR|ADAS-?Cog|NPI|GDS|Hachinski|PET\s*scan?"
        r"|amyloid|tau|CSF|cerebrospinal|biomarker|neuroimaging"
        r"|MRI|fMRI|CT\s*scan|EEG|score\s+(?:of|between|greater|less)"
        r"|Mini-?Mental|clinical\s+dementia\s+rating)\b",
        re.IGNORECASE,
    )),
    (CriterionType.LABORATORY, re.compile(
        r"\b(?:blood|serum|plasma|hematolog|liver\s+function|renal\s+function"
        r"|creatinine|ALT|AST|bilirubin|platelet|WBC|hemoglobin"
        r"|lab(?:oratory)?\s+(?:test|value|result)|urinalysis)\b",
        re.IGNORECASE,
    )),
    (CriterionType.AGE, re.compile(
        r"\b(?:aged?|years?\s*(?:old|of\s+age)|\d+\s*(?:to|and|[-–])\s*\d+\s*years?"
        r"|older\s+than|younger\s+than|at\s+least\s+\d+\s*years?"
        r"|between\s+\d+\s+and\s+\d+\s*(?:years?|inclusive)"
        r"|over\s+\d+|under\s+\d+|≥\s*\d+\s*years?"
        r"|\d+\s*(?:or\s+)?(?:above|below)|inclusive)\b",
        re.IGNORECASE,
    )),
    (CriterionType.DEMOGRAPHIC, re.compile(
        r"\b(?:male|female|sex|gender|pregnan\w*|lactat\w*|non-?pregnan\w*"
        r"|men\s+and\s+women|postmenopausal|premenopausal)\b",
        re.IGNORECASE,
    )),
    (CriterionType.CONSENT, re.compile(
        r"\b(?:informed\s+consent|voluntary|consent\s+(?:form|in\s+writing)"
        r"|capable\s+of\s+giving|able\s+to\s+give|willing\s+to\s+sign)\b",
        re.IGNORECASE,
    )),
    (CriterionType.MEDICATION, re.compile(
        r"\b(?:drug|medication|medicinal|treatment\s+(?:with|by)"
        r"|cholinesterase\s+inhibitor|memantine|donepezil|rivastigmine"
        r"|galantamine|anticoagulan|immunosuppress|steroid|antibiotic"
        r"|chemotherapy|vaccine|stable\s+dose|current(?:ly)?\s+(?:taking|using|on)"
        r"|received\s+(?:treatment|therapy)|washout)\b",
        re.IGNORECASE,
    )),
    (CriterionType.PROCEDURE, re.compile(
        r"\b(?:surgery|surgical|implant|biopsy|endoscop|catheter"
        r"|device|pacemaker|prosthesis|transplant|dialysis"
        r"|participated\s+in\s+(?:a|another)\s+(?:clinical\s+)?(?:study|trial|research))\b",
        re.IGNORECASE,
    )),
    (CriterionType.CONDITION, re.compile(
        r"\b(?:diagnos[ei]s|disease|dementia|Alzheimer|Parkinson"
        r"|cognitive\s+impairment|MCI|mild\s+cognitive|neurolog"
        r"|psychiatr|epilepsy|stroke|tumou?r|cancer|autoimmune"
        r"|infection|inflammation|trauma|disorder|syndrome"
        r"|ICD-?\d+|DSM-?[IV]+|NINCDS|ADRDA)\b",
        re.IGNORECASE,
    )),
]


def classify_criterion(text: str) -> CriterionType:
    for criterion_type, pattern in _TYPE_PATTERNS:
        if pattern.search(text):
            return criterion_type
    return CriterionType.OTHER


def _split_into_criteria(section_text: str) -> list[str]:
    lines = section_text.split("\n")
    criteria: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                criteria.append(" ".join(current))
                current = []
            continue

        is_bullet = _BULLET.match(line)
        is_numbered = _NUMBERED.match(line)

        if is_bullet or is_numbered:
            if current:
                criteria.append(" ".join(current))
            current = [_BULLET.sub("", _NUMBERED.sub("", line)).strip()]
        elif _SUBSECTION_HEADER.match(stripped):
            if current:
                criteria.append(" ".join(current))
                current = []
        elif current and not is_bullet and not is_numbered:
            current.append(stripped)
        else:
            current = [stripped]

    if current:
        criteria.append(" ".join(current))

    return [c for c in criteria if len(c) > 3]


def parse_eligibility_criteria(nct_id: str, text: str | None) -> EligibilityParseResult:
    if not text or not text.strip():
        return EligibilityParseResult(nct_id=nct_id, parse_quality="empty")

    result = EligibilityParseResult(nct_id=nct_id)
    lines = text.split("\n")

    current_direction: CriterionDirection | None = None
    current_section_label = ""
    section_lines: list[str] = []

    def flush_section():
        if current_direction and section_lines:
            section_text = "\n".join(section_lines)
            for criterion_text in _split_into_criteria(section_text):
                result.criteria.append(
                    StructuredCriterion(
                        direction=current_direction,
                        criterion_type=classify_criterion(criterion_text),
                        text=criterion_text,
                        section_label=current_section_label,
                    )
                )

    for line in lines:
        stripped = line.strip()
        header_match = _SECTION_HEADER.match(stripped)

        if header_match:
            flush_section()
            section_lines = []
            direction_word = header_match.group(1).lower()
            current_direction = (
                CriterionDirection.INCLUSION
                if direction_word == "inclusion"
                else CriterionDirection.EXCLUSION
            )
            current_section_label = stripped.rstrip(":").strip()
        else:
            section_lines.append(line)

    flush_section()

    if not result.criteria:
        fallback_direction = CriterionDirection.INCLUSION
        for criterion_text in _split_into_criteria(text):
            result.criteria.append(
                StructuredCriterion(
                    direction=fallback_direction,
                    criterion_type=classify_criterion(criterion_text),
                    text=criterion_text,
                    section_label="unstructured",
                )
            )
        result.parse_quality = "no_sections_detected"

    return result
