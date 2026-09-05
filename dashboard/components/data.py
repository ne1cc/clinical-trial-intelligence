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
    return _connection().execute(sql).df()


def priority_queue() -> pd.DataFrame:
    return query("select * from main_marts.mart_feasibility_priority_queue order by priority_rank")


@st.cache_data(ttl=600)
def trial_similarity(nct_id: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
            "select * from main_marts.mart_trial_similarity"
            " where nct_id_a = ? order by similarity_rank",
            [nct_id],
        )
        .df()
    )


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
