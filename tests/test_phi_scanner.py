"""Tests for the PHI/PII scanner."""

from src.quality.phi_scanner import (
    PhiEntityType,
    scan_silver_entity,
    scan_study_fields,
    scan_text,
)


class TestScanText:
    def test_email_detected(self):
        text = "Contact the coordinator at john.smith@hospital.org for details."
        findings = scan_text(text, "eligibility_criteria_text", "NCT00000001")
        assert len(findings) == 1
        assert findings[0].entity_type == PhiEntityType.EMAIL
        assert "john.smith" not in findings[0].masked_value

    def test_phone_detected(self):
        text = "Call (555) 123-4567 to schedule screening."
        findings = scan_text(text, "description", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.PHONE for f in findings)

    def test_phone_with_country_code(self):
        text = "Reach us at +1-800-555-0199 for enrollment."
        findings = scan_text(text, "description", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.PHONE for f in findings)

    def test_ssn_detected(self):
        text = "Verify identity with SSN 123-45-6789."
        findings = scan_text(text, "description", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.SSN for f in findings)

    def test_mrn_detected(self):
        text = "Patients with MRN: 12345678 are eligible."
        findings = scan_text(text, "eligibility_criteria_text", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.MRN for f in findings)

    def test_street_address_detected(self):
        text = "Visit our clinic at 123 Main Street, Suite 400."
        findings = scan_text(text, "description", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.STREET_ADDRESS for f in findings)

    def test_url_with_params_detected(self):
        text = "Register at https://example.com/enroll?patient=12345&name=John"
        findings = scan_text(text, "description", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.URL_WITH_PARAMS for f in findings)

    def test_person_name_in_contact_context(self):
        text = "Contact: Dr. Sarah Johnson for screening visits."
        findings = scan_text(text, "description", "NCT00000001")
        assert any(f.entity_type == PhiEntityType.PERSON_NAME for f in findings)

    def test_clean_clinical_text_passes(self):
        text = (
            "Inclusion Criteria:\n"
            "* Aged 60 years or older\n"
            "* MMSE score between 20 and 26\n"
            "* Diagnosis of probable Alzheimer's disease per NINCDS-ADRDA criteria\n"
        )
        findings = scan_text(text, "eligibility_criteria_text", "NCT00000001")
        assert findings == []

    def test_empty_text(self):
        assert scan_text("", "field", "NCT00000001") == []
        assert scan_text(None, "field", "NCT00000001") == []

    def test_masking_preserves_length_hint(self):
        text = "Email: abcdefgh@example.com"
        findings = scan_text(text, "field", "NCT00000001")
        assert len(findings) == 1
        masked = findings[0].masked_value
        assert masked.startswith("ab")
        assert masked.endswith("om")
        assert "*" in masked

    def test_phone_not_triggered_by_enrollment_count(self):
        text = "Target enrollment of 555-123-4567 participants is not a phone."
        findings = scan_text(text, "description", "NCT00000001")
        phone_findings = [f for f in findings if f.entity_type == PhiEntityType.PHONE]
        assert phone_findings == []


class TestScanStudyFields:
    def test_multiple_fields_scanned(self):
        fields = {
            "brief_title": "Study of Drug X",
            "eligibility_criteria_text": "Contact: Jane Smith for info.",
            "official_title": None,
        }
        findings = scan_study_fields("NCT00000001", fields)
        assert len(findings) >= 1
        assert all(f.nct_id == "NCT00000001" for f in findings)

    def test_none_fields_skipped(self):
        fields = {"brief_title": None, "description": None}
        findings = scan_study_fields("NCT00000001", fields)
        assert findings == []


class TestScanSilverEntity:
    def test_clean_batch(self):
        records = [
            {"nct_id": "NCT001", "brief_title": "Clean study", "description": "Aged 60+"},
            {"nct_id": "NCT002", "brief_title": "Another clean", "description": "MMSE > 20"},
        ]
        summary = scan_silver_entity(records, ["brief_title", "description"])
        assert summary.is_clean
        assert summary.status == "CLEAN"
        assert summary.total_records_scanned == 2

    def test_findings_detected(self):
        records = [
            {"nct_id": "NCT001", "description": "Call 555-123-4567"},
            {"nct_id": "NCT002", "description": "Email test@site.org"},
            {"nct_id": "NCT003", "description": "Clean text here"},
        ]
        summary = scan_silver_entity(records, ["description"])
        assert not summary.is_clean
        assert summary.status == "FINDINGS_DETECTED"
        assert summary.total_findings >= 2
        assert len(summary.affected_nct_ids) == 2

    def test_findings_by_type_populated(self):
        records = [
            {"nct_id": "NCT001", "text": "SSN 123-45-6789 and email a@b.com"},
        ]
        summary = scan_silver_entity(records, ["text"])
        assert "ssn" in summary.findings_by_type
        assert "email" in summary.findings_by_type
