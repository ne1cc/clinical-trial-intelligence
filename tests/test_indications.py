from src.config import list_indication_profiles, load_indication_profile
from src.transform.flatten_studies import flatten_study
from src.transform.normalize_conditions import get_taxonomy, load_taxonomy
from src.transform.normalize_locations import get_geography_rules


def test_list_indication_profiles():
    profiles = list_indication_profiles()
    assert "adrd" in profiles
    assert "oncology_nsclc" in profiles


def test_load_adrd_profile():
    profile = load_indication_profile("adrd")
    assert profile.indication_id == "adrd"
    assert profile.query.condition == "Alzheimer Disease"
    assert "INTERVENTIONAL" in (profile.query.advanced_filter or "")


def test_load_oncology_nsclc_profile():
    profile = load_indication_profile("oncology_nsclc")
    assert profile.indication_id == "oncology_nsclc"
    assert "Non-Small Cell Lung Cancer" in profile.query.condition
    assert "INTERVENTIONAL" in (profile.query.advanced_filter or "")


def test_nsclc_taxonomy_mapping():
    taxonomy = load_taxonomy("oncology_nsclc")

    # Adenocarcinoma
    m_adeno = taxonomy.map_condition("Lung Adenocarcinoma")
    assert m_adeno.condition_group == "nsclc_adenocarcinoma"
    assert m_adeno.relevance_flag is True
    assert m_adeno.mapping_confidence == "high"

    # Squamous
    m_squam = taxonomy.map_condition("Squamous Cell Lung Carcinoma")
    assert m_squam.condition_group == "nsclc_squamous"
    assert m_squam.relevance_flag is True
    assert m_squam.mapping_confidence == "high"

    # Biomarker targeted (EGFR, ALK, KRAS)
    m_egfr = taxonomy.map_condition("EGFR Exon 20 Insertion NSCLC")
    assert m_egfr.condition_group == "nsclc_biomarker_targeted"
    assert m_egfr.relevance_flag is True

    m_kras = taxonomy.map_condition("KRAS G12C Mutant Non-Small Cell Lung Cancer")
    assert m_kras.condition_group == "nsclc_biomarker_targeted"
    assert m_kras.relevance_flag is True

    # Metastatic
    m_meta = taxonomy.map_condition("Metastatic Non-Small Cell Lung Cancer")
    assert m_meta.condition_group == "nsclc_metastatic_advanced"
    assert m_meta.relevance_flag is True

    # General / Unspecified NSCLC
    m_gen = taxonomy.map_condition("Non-Small Cell Lung Cancer")
    assert m_gen.condition_group == "nsclc_unspecified"
    assert m_gen.relevance_flag is True

    # Unrelated
    m_unrelated = taxonomy.map_condition("Alzheimer Disease")
    assert m_unrelated.condition_group == "other_thoracic_oncology"
    assert m_unrelated.relevance_flag is False


def test_flatten_study_extracts_why_stopped():
    taxonomy = get_taxonomy("adrd")
    geography = get_geography_rules()

    sample_terminated = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999", "briefTitle": "Terminated Trial"},
            "statusModule": {
                "overallStatus": "TERMINATED",
                "whyStopped": "Terminated early due to slow accrual and low patient enrollment.",
            },
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE3"]},
            "conditionsModule": {"conditions": ["Alzheimer's Disease"]},
        }
    }

    rows = flatten_study(
        sample_terminated,
        ingestion_run_id="run_test",
        snapshot_timestamp_utc="2026-09-04T00:00:00Z",
        taxonomy=taxonomy,
        geography=geography,
    )
    trial_row = rows["silver_trials"][0]
    assert trial_row["overall_status"] == "TERMINATED"
    assert (
        trial_row["why_stopped"]
        == "Terminated early due to slow accrual and low patient enrollment."
    )


def test_relevance_flag_alias():
    taxonomy = get_taxonomy("adrd")
    m = taxonomy.map_condition("Alzheimer's Disease")
    assert m.relevance_flag is True
    assert m.dementia_relevance_flag is True


def test_cli_module_alias():
    from src.cli import build_parser

    parser = build_parser()
    args_ingest = parser.parse_args(["ingest", "--module", "oncology_nsclc"])
    assert args_ingest.profile == "oncology_nsclc"

    args_transform = parser.parse_args(["transform", "--module", "oncology_nsclc"])
    assert args_transform.profile == "oncology_nsclc"
