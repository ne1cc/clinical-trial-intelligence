"""Tests for the eligibility criteria NLP parser."""

from src.transform.parse_eligibility import (
    CriterionDirection,
    CriterionType,
    EligibilityParseResult,
    StructuredCriterion,
    classify_criterion,
    parse_eligibility_criteria,
)


class TestClassifyCriterion:
    def test_age_years_old(self):
        assert classify_criterion("Aged 60 years or older") == CriterionType.AGE

    def test_age_range(self):
        assert classify_criterion("Between 18 and 55 years of age") == CriterionType.AGE

    def test_age_numeric_threshold(self):
        assert classify_criterion("At least 50 years old") == CriterionType.AGE

    def test_biomarker_mmse(self):
        assert classify_criterion("MMSE score between 20 and 26") == CriterionType.BIOMARKER

    def test_biomarker_cdr(self):
        assert classify_criterion("CDR global score of 0.5 or 1") == CriterionType.BIOMARKER

    def test_biomarker_pet(self):
        assert classify_criterion("Positive amyloid PET scan") == CriterionType.BIOMARKER

    def test_condition_diagnosis(self):
        result = classify_criterion("Diagnosis of probable Alzheimer's disease")
        assert result == CriterionType.CONDITION

    def test_condition_dementia(self):
        assert classify_criterion("Mild to moderate dementia") == CriterionType.CONDITION

    def test_condition_icd(self):
        assert classify_criterion("ICD-10: F00.1 diagnosis") == CriterionType.CONDITION

    def test_medication_stable_dose(self):
        result = classify_criterion("Stable dose of cholinesterase inhibitor")
        assert result == CriterionType.MEDICATION

    def test_medication_memantine(self):
        assert classify_criterion("Currently taking memantine") == CriterionType.MEDICATION

    def test_procedure_surgery(self):
        assert classify_criterion("History of brain surgery") == CriterionType.PROCEDURE

    def test_procedure_prior_trial(self):
        assert classify_criterion(
            "Participated in another clinical trial within 30 days"
        ) == CriterionType.PROCEDURE

    def test_demographic_sex(self):
        assert classify_criterion("Male and female patients") == CriterionType.DEMOGRAPHIC

    def test_demographic_pregnancy(self):
        result = classify_criterion("Non-pregnant, non-lactating females")
        assert result == CriterionType.DEMOGRAPHIC

    def test_consent(self):
        result = classify_criterion("Able to give informed consent in writing")
        assert result == CriterionType.CONSENT

    def test_laboratory(self):
        assert classify_criterion("Normal liver function tests") == CriterionType.LABORATORY

    def test_other_fallback(self):
        assert classify_criterion("Willing to comply with study visits") == CriterionType.OTHER


class TestParseEligibilityCriteria:
    def test_empty_text(self):
        result = parse_eligibility_criteria("NCT00000000", None)
        assert result.parse_quality == "empty"
        assert result.criteria == []

    def test_whitespace_only(self):
        result = parse_eligibility_criteria("NCT00000000", "   \n  ")
        assert result.parse_quality == "empty"

    def test_standard_inclusion_exclusion(self):
        text = (
            "Inclusion Criteria:\n\n"
            "* Aged 60 years or older\n"
            "* MMSE score >= 20\n\n"
            "Exclusion Criteria:\n\n"
            "* History of stroke\n"
            "* Current pregnancy\n"
        )
        result = parse_eligibility_criteria("NCT00000001", text)
        assert result.inclusion_count == 2
        assert result.exclusion_count == 2
        assert result.parse_quality == "ok"

        inclusion = [c for c in result.criteria if c.direction == CriterionDirection.INCLUSION]
        assert inclusion[0].criterion_type == CriterionType.AGE
        assert inclusion[1].criterion_type == CriterionType.BIOMARKER

        exclusion = [c for c in result.criteria if c.direction == CriterionDirection.EXCLUSION]
        assert exclusion[0].criterion_type == CriterionType.CONDITION
        assert exclusion[1].criterion_type == CriterionType.DEMOGRAPHIC

    def test_main_prefix_headers(self):
        text = (
            "Main Inclusion Criteria:\n\n"
            "* Healthy males aged 18 to 55\n\n"
            "Main Exclusion Criteria:\n\n"
            "* History of fainting\n"
        )
        result = parse_eligibility_criteria("NCT00000002", text)
        assert result.inclusion_count == 1
        assert result.exclusion_count == 1

    def test_uppercase_headers(self):
        text = (
            "INCLUSION CRITERIA:\n\n"
            "* Diagnosis of mild AD\n\n"
            "EXCLUSION CRITERIA:\n\n"
            "* Other causes of dementia\n"
        )
        result = parse_eligibility_criteria("NCT00000003", text)
        assert result.inclusion_count == 1
        assert result.exclusion_count == 1

    def test_subsection_headers_within_inclusion(self):
        text = (
            "Inclusion Criteria:\n\n"
            "General inclusion criteria:\n"
            "* 60 years and older\n\n"
            "Alzheimer's disease inclusion criteria:\n"
            "* MMSE >= 20\n\n"
            "Exclusion Criteria:\n\n"
            "* Neurological pathologies\n"
        )
        result = parse_eligibility_criteria("NCT00000004", text)
        assert result.inclusion_count == 2
        assert result.exclusion_count == 1

    def test_numbered_list(self):
        text = (
            "Inclusion Criteria:\n\n"
            "1. Aged 50 or above\n"
            "2. Diagnosis of Parkinson's disease\n\n"
            "Exclusion Criteria:\n\n"
            "1. Prior brain surgery\n"
        )
        result = parse_eligibility_criteria("NCT00000005", text)
        assert result.inclusion_count == 2
        assert result.exclusion_count == 1

    def test_no_sections_fallback(self):
        text = "Patients must be over 65 with confirmed dementia diagnosis."
        result = parse_eligibility_criteria("NCT00000006", text)
        assert result.parse_quality == "no_sections_detected"
        assert len(result.criteria) >= 1
        assert result.criteria[0].direction == CriterionDirection.INCLUSION

    def test_multiline_criterion_continuation(self):
        text = (
            "Inclusion Criteria:\n\n"
            "* Patients with a confirmed diagnosis of\n"
            "  Alzheimer's disease per NINCDS-ADRDA criteria\n"
            "* Aged 55 to 85 years\n"
        )
        result = parse_eligibility_criteria("NCT00000007", text)
        assert result.inclusion_count == 2
        assert "NINCDS-ADRDA" in result.criteria[0].text

    def test_real_world_sample(self):
        text = (
            "Inclusion Criteria:\n\n"
            "* Being 60 years old and over\n"
            "* The participants enrolled in the control group must have a score of "
            "the Mini-Mental State Exam test greater than or equal to 28.\n"
            "* The participants enrolled in the intervention group must have a "
            "diagnosis of Alzheimer's disease, and the score of the Mini-Mental "
            "State Exam test should be between 20 and 27\n\n"
            "Exclusion Criteria:\n\n"
            "* Presenting an unstable, acute or current psychiatric or physical "
            "condition that is severe enough to prevent the participant from "
            "participating in the study, as determined by the investigator.\n"
            "* Having an uncorrected major visual or hearing impairment or "
            "anosmia (total olfaction loss).\n"
        )
        result = parse_eligibility_criteria("NCT03698760", text)
        assert result.inclusion_count == 3
        assert result.exclusion_count == 2
        assert result.parse_quality == "ok"

    def test_section_label_preserved(self):
        text = (
            "Inclusion Criteria:\n\n"
            "* Aged 18+\n\n"
            "Exclusion Criteria:\n\n"
            "* Pregnant\n"
        )
        result = parse_eligibility_criteria("NCT00000008", text)
        assert result.criteria[0].section_label == "Inclusion Criteria"
        assert result.criteria[1].section_label == "Exclusion Criteria"

    def test_dash_bullets(self):
        text = (
            "Inclusion Criteria:\n\n"
            "- Aged 65 or above\n"
            "- Confirmed dementia diagnosis\n"
        )
        result = parse_eligibility_criteria("NCT00000009", text)
        assert result.inclusion_count == 2


class TestEligibilityParseResult:
    def test_counts(self):
        result = EligibilityParseResult(
            nct_id="NCT00000001",
            criteria=[
                StructuredCriterion(
                    direction=CriterionDirection.INCLUSION,
                    criterion_type=CriterionType.AGE,
                    text="Aged 60+",
                ),
                StructuredCriterion(
                    direction=CriterionDirection.EXCLUSION,
                    criterion_type=CriterionType.CONDITION,
                    text="History of stroke",
                ),
                StructuredCriterion(
                    direction=CriterionDirection.EXCLUSION,
                    criterion_type=CriterionType.MEDICATION,
                    text="Current anticoagulant use",
                ),
            ],
        )
        assert result.inclusion_count == 1
        assert result.exclusion_count == 2
