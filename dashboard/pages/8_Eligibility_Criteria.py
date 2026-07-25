"""Eligibility Criteria — structured eligibility complexity across the portfolio."""

import plotly.express as px
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Eligibility Criteria", icon=":material/checklist:")
data.require_warehouse()

overview = data.eligibility_overview()
m = overview["metrics"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Trials with criteria", f"{int(m['trials_with_criteria']):,}")
col2.metric("Avg criteria / trial", f"{m['avg_criteria_count']}")
col3.metric("High complexity", f"{int(m['high_complexity']):,}")
col4.metric(
    "Coverage",
    f"{m['trials_with_criteria'] / m['total_trials'] * 100:.0f}%"
    if m["total_trials"] > 0
    else "—",
)

st.subheader("Criterion type distribution")
type_df = overview["type_distribution"]
if not type_df.empty:
    fig = px.bar(
        type_df,
        x="criterion_type",
        y="criterion_count",
        color="direction",
        barmode="group",
        labels={
            "criterion_type": "Criterion Type",
            "criterion_count": "Count",
            "direction": "Direction",
        },
        color_discrete_map={"inclusion": "#2ecc71", "exclusion": "#e74c3c"},
    )
    fig.update_layout(xaxis_tickangle=-45, height=400)
    st.plotly_chart(fig, width="stretch")

st.subheader("Eligibility complexity by phase")
phase_df = overview["complexity_by_phase"]
if not phase_df.empty:
    st.dataframe(
        phase_df,
        hide_index=True,
        width="stretch",
        column_config={
            "avg_criteria": st.column_config.NumberColumn("Avg Criteria", format="%.1f"),
            "avg_type_diversity": st.column_config.NumberColumn(
                "Type Diversity", format="%.2f"
            ),
        },
    )

    fig2 = px.scatter(
        phase_df,
        x="avg_criteria",
        y="avg_type_diversity",
        size="trial_count",
        hover_name="phase",
        labels={
            "avg_criteria": "Avg Criteria Count",
            "avg_type_diversity": "Type Diversity Score",
            "trial_count": "Trial Count",
        },
    )
    fig2.update_layout(height=350)
    st.plotly_chart(fig2, width="stretch")

st.caption(
    "Eligibility criteria are parsed from free-text registry fields using "
    "rule-based NLP. Classification is best-effort and not clinically adjudicated."
)
guarded_footer()
