"""Enrollment Forecast — trial lifecycle and enrollment velocity analytics."""

import plotly.express as px
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Enrollment Forecast", icon=":material/trending_up:")
data.require_warehouse()

forecast = data.enrollment_forecast()

if forecast.empty:
    st.warning("No enrollment forecast data available.")
    st.stop()

st.subheader("Portfolio overview")
total_trials = int(forecast["trial_count"].sum())
active = int(
    forecast.loc[forecast["enrollment_stage"] == "active_recruiting", "trial_count"].sum()
)
pending = int(
    forecast.loc[forecast["enrollment_stage"] == "pending", "trial_count"].sum()
)
attrited = int(forecast["attrited_trial_count"].sum())

with st.container(border=True):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total trials", f"{total_trials:,}")
    col2.metric("Active recruiting", f"{active:,}")
    col3.metric("Pending", f"{pending:,}")
    col4.metric("Attrited", f"{attrited:,}")

st.divider()
st.subheader("Enrollment stage by condition group")
stage_pivot = forecast.pivot_table(
    index="condition_group",
    columns="enrollment_stage",
    values="trial_count",
    fill_value=0,
    aggfunc="sum",
).reset_index()

if not stage_pivot.empty:
    stage_cols = [c for c in stage_pivot.columns if c != "condition_group"]
    fig = px.bar(
        stage_pivot,
        x="condition_group",
        y=stage_cols,
        barmode="stack",
        labels={"value": "Trial Count", "variable": "Enrollment Stage"},
    )
    fig.update_layout(height=400, xaxis_tickangle=-30)
    st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Enrollment velocity signals")
velocity_df = forecast[
    ["condition_group", "enrollment_stage", "trial_count",
     "avg_target_enrollment", "avg_planned_duration_days",
     "avg_planned_rate_per_day", "attrition_rate", "stale_listing_pct"]
].copy()

st.dataframe(
    velocity_df,
    hide_index=True,
    width="stretch",
    column_config={
        "avg_target_enrollment": st.column_config.NumberColumn(
            "Avg Target", format="%.0f"
        ),
        "avg_planned_duration_days": st.column_config.NumberColumn(
            "Avg Duration (days)", format="%.0f"
        ),
        "avg_planned_rate_per_day": st.column_config.NumberColumn(
            "Planned Rate/Day", format="%.2f"
        ),
        "attrition_rate": st.column_config.NumberColumn(
            "Attrition Rate", format="%.1%%"
        ),
        "stale_listing_pct": st.column_config.NumberColumn(
            "Stale %", format="%.1f"
        ),
    },
)

st.caption(
    "Enrollment rates are derived from public registry date fields and target "
    "enrollment counts. They are planning proxies, not measured enrollment "
    "velocity. Attrition requires multiple snapshots to compute via status "
    "transitions."
)
guarded_footer()
