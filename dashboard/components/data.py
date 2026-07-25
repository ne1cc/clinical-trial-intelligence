"""Read-only DuckDB access for the dashboard (never writes to the warehouse)."""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from src.config import get_config


def warehouse_path():
    return get_config().paths.duckdb


@st.cache_resource
def _connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(warehouse_path()), read_only=True)


def require_warehouse() -> None:
    if not warehouse_path().exists():
        st.error(
            "Warehouse not found. Build it first:\n\n"
            "```\nmake ingest && make transform && make dbt-run\n```"
        )
        st.stop()


@st.cache_data(ttl=600)
def query(sql: str) -> pd.DataFrame:
    df = _connection().execute(sql).df()
    for col in df.select_dtypes(include=["string"]).columns:
        df[col] = df[col].astype("object")
    for col in df.select_dtypes(include=["Int32", "Int64"]).columns:
        df[col] = df[col].astype("float64")
    return df


def priority_queue() -> pd.DataFrame:
    return query("select * from main_marts.mart_feasibility_priority_queue order by priority_rank")


def recruiting_competition() -> pd.DataFrame:
    return query(
        "select * from main_marts.mart_recruiting_competition "
        "where snapshot_date = (select max(snapshot_date) "
        "from main_marts.mart_recruiting_competition)"
    )


def condition_geography_trends() -> pd.DataFrame:
    return query("select * from main_marts.mart_condition_geography_trends order by activity_month")


def site_overlap() -> pd.DataFrame:
    return query(
        "select * from main_marts.mart_site_overlap "
        "where snapshot_date = (select max(snapshot_date) from main_marts.mart_site_overlap) "
        "order by recruiting_trial_count desc, listed_trial_count desc"
    )


def sponsor_landscape() -> pd.DataFrame:
    return query(
        """
        select
            d.current_lead_sponsor as lead_sponsor,
            any_value(s.sponsor_class) as sponsor_class,
            count(distinct d.nct_id) as recruiting_trial_count,
            string_agg(distinct d.current_phase, ' | ' order by d.current_phase) as phase_mix
        from main_marts.dim_trial d
        left join main_marts.bridge_trial_sponsor s
            on d.trial_key = s.trial_key and s.lead_sponsor_flag
        where d.current_overall_status = 'RECRUITING'
        group by 1
        order by recruiting_trial_count desc, lead_sponsor
        """
    )


def trial_explorer() -> pd.DataFrame:
    return query(
        """
        select
            d.nct_id,
            d.registry_url,
            d.current_brief_title as brief_title,
            d.current_overall_status as overall_status,
            d.current_phase as phase,
            d.current_lead_sponsor as lead_sponsor,
            d.study_first_post_date,
            d.enrollment_count,
            string_agg(distinct s.state_normalized, ', ' order by s.state_normalized)
                as us_states
        from main_marts.dim_trial d
        left join main_marts.fct_trial_site s
            on d.nct_id = s.nct_id
            and s.snapshot_date = (select max(snapshot_date) from main_marts.fct_trial_site)
            and regexp_matches(s.state_normalized, '^[A-Z]{2}$')
        group by all
        order by d.study_first_post_date desc nulls last, d.nct_id
        """
    )


def data_reliability() -> pd.DataFrame:
    return query(
        "select * from main_marts.mart_data_reliability "
        "order by snapshot_date desc, ingestion_run_id desc"
    )


def overview_metrics() -> dict:
    row = query(
        """
        select
            (select count(*) from main_marts.dim_trial) as total_trials,
            (select count(*) from main_marts.dim_trial
             where current_overall_status = 'RECRUITING') as recruiting_trials,
            (select count(*) from main_marts.dim_geography) as states_with_sites,
            (select count(*) from main_marts.mart_site_overlap) as listed_facilities,
            (select max(snapshot_date) from main_marts.fct_trial_snapshot) as latest_snapshot,
            (select count(distinct snapshot_date)
             from main_marts.fct_trial_snapshot) as snapshot_count
        """
    ).iloc[0]
    return row.to_dict()


def eligibility_overview() -> dict:
    metrics = query(
        """
        select
            count(*) as total_trials,
            count(*) filter (eligibility_criteria_count > 0) as trials_with_criteria,
            round(avg(eligibility_criteria_count) filter (eligibility_criteria_count > 0), 1)
                as avg_criteria_count,
            count(*) filter (eligibility_complexity_band = 'high') as high_complexity,
            count(*) filter (eligibility_complexity_band = 'moderate') as moderate_complexity,
            count(*) filter (eligibility_complexity_band = 'low') as low_complexity
        from main_marts.dim_trial
        """
    ).iloc[0].to_dict()

    type_dist = query(
        """
        select criterion_type, direction, count(*) as criterion_count
        from main_staging.stg_trial_eligibility_criteria
        group by 1, 2
        order by criterion_count desc
        """
    )

    complexity_by_phase = query(
        """
        select
            current_phase as phase,
            count(*) as trial_count,
            round(avg(eligibility_criteria_count), 1) as avg_criteria,
            round(avg(eligibility_type_diversity), 2) as avg_type_diversity,
            count(*) filter (eligibility_complexity_band = 'high') as high_complexity_count
        from main_marts.dim_trial
        where eligibility_criteria_count > 0
        group by 1
        order by avg_criteria desc
        """
    )

    return {
        "metrics": metrics,
        "type_distribution": type_dist,
        "complexity_by_phase": complexity_by_phase,
    }


def omop_condition_summary() -> pd.DataFrame:
    return query(
        """
        select
            condition_concept_name,
            condition_vocabulary,
            count(*) as occurrence_count,
            count(distinct person_source_value) as trial_count,
            round(100.0 * count(*) filter (dementia_relevance_flag) / count(*), 1)
                as dementia_relevant_pct
        from main_marts.mart_omop_condition_occurrence
        group by 1, 2
        order by occurrence_count desc
        """
    )


def omop_drug_summary() -> pd.DataFrame:
    return query(
        """
        select
            drug_concept_name,
            drug_domain,
            drug_vocabulary,
            count(*) as exposure_count,
            count(distinct person_source_value) as trial_count,
            count(*) filter (concept_mapped_flag) as mapped_count
        from main_marts.mart_omop_drug_exposure
        group by 1, 2, 3
        order by exposure_count desc
        """
    )


def enrollment_forecast() -> pd.DataFrame:
    return query(
        """
        select * from main_marts.mart_enrollment_forecast
        order by condition_group, trial_count desc
        """
    )
