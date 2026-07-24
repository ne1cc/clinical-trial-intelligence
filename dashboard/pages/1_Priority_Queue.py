"""Feasibility Review Priority Queue — ranked segments for human review."""

import plotly.express as px
import streamlit as st
from components import data
from components.filters import segment_filters
from components.guardrails import guarded_footer, page_setup

page_setup("Feasibility Review Priority Queue")
data.require_warehouse()

queue = data.priority_queue()
filtered = segment_filters(queue)

band_counts = filtered["priority_band"].value_counts()
col1, col2, col3 = st.columns(3)
col1.metric("Priority review", int(band_counts.get("priority_review", 0)))
col2.metric("Review", int(band_counts.get("review", 0)))
col3.metric("Watch", int(band_counts.get("watch", 0)))

if bool(filtered["growth_uses_registry_proxy_flag"].any()):
    st.warning(
        "Growth component currently uses the registry first-post-date proxy "
        "because multi-snapshot history has not accrued yet."
    )

st.subheader("Ranked queue")
st.dataframe(
    filtered[
        [
            "priority_rank",
            "condition_group",
            "state_normalized",
            "phase_normalized",
            "feasibility_review_priority_score",
            "priority_band",
            "recruiting_trial_count",
            "sponsor_hhi",
            "site_overlap_share",
            "data_confidence_share",
            "priority_explanation",
        ]
    ],
    hide_index=True,
    width="stretch",
)

st.subheader("Score composition (top 15 shown)")
top = filtered.head(15).copy()
top["segment"] = (
    top["condition_group"]
    + " · "
    + top["state_normalized"]
    + " · "
    + top["phase_normalized"]
)
components = {
    "normalized_recruiting_trial_count": "Recruiting density",
    "normalized_recent_recruiting_growth": "Recent growth",
    "normalized_sponsor_concentration": "Sponsor concentration",
    "normalized_site_overlap": "Site overlap",
    "normalized_data_confidence_adjustment": "Data confidence",
}
melted = top.melt(
    id_vars="segment",
    value_vars=list(components),
    var_name="component",
    value_name="normalized value",
)
melted["component"] = melted["component"].map(components)
fig = px.bar(
    melted,
    y="segment",
    x="normalized value",
    color="component",
    orientation="h",
    title="Normalized (unweighted) component values per segment",
)
fig.update_layout(yaxis=dict(autorange="reversed"), height=520)
st.plotly_chart(fig, width="stretch")
st.caption(
    "Bars show normalized component inputs before weighting; the score "
    "applies the weights in config/score_weights.yml."
)

if not filtered.empty:
    st.info(filtered.iloc[0]["interpretation_note"])

guarded_footer()
