"""Site Overlap — facilities listed by multiple recruiting trials."""

import plotly.express as px
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Site Overlap")
data.require_warehouse()

overlap = data.site_overlap()

st.sidebar.header("Filters")
states = sorted(overlap["state_normalized"].dropna().unique())
selected_states = st.sidebar.multiselect("State", states)
only_repeated = st.sidebar.checkbox("Only multi-trial facilities", value=True)

filtered = overlap
if selected_states:
    filtered = filtered[filtered["state_normalized"].isin(selected_states)]
if only_repeated:
    filtered = filtered[filtered["repeated_site_participation_flag"]]

col1, col2 = st.columns(2)
col1.metric("Facilities shown", f"{len(filtered):,}")
col2.metric(
    "Multi-trial facilities (all states)",
    f"{int(overlap['repeated_site_participation_flag'].sum()):,}",
)

st.subheader("Facilities by recruiting-trial listings")
st.dataframe(
    filtered[
        [
            "facility_name",
            "city",
            "state_normalized",
            "recruiting_trial_count",
            "listed_trial_count",
            "sponsor_count",
            "phase_mix",
        ]
    ].head(200),
    hide_index=True,
    width="stretch",
    column_config={
        "facility_name": st.column_config.TextColumn("Facility", width="large"),
        "city": st.column_config.TextColumn("City"),
        "state_normalized": st.column_config.TextColumn("State"),
        "recruiting_trial_count": st.column_config.NumberColumn(
            "Recruiting listings", format="%d"
        ),
        "listed_trial_count": st.column_config.NumberColumn(
            "Listed trials", format="%d"
        ),
        "sponsor_count": st.column_config.NumberColumn("Sponsors", format="%d"),
        "phase_mix": st.column_config.TextColumn("Phase mix", width="medium"),
    },
)

st.divider()
st.subheader("States with the most multi-trial facilities")
by_state = (
    overlap[overlap["repeated_site_participation_flag"]]
    .groupby("state_normalized", as_index=False)
    .size()
    .rename(columns={"size": "multi_trial_facilities"})
    .sort_values("multi_trial_facilities", ascending=False)
    .head(15)
)
fig = px.bar(by_state, x="state_normalized", y="multi_trial_facilities")
st.plotly_chart(fig, width="stretch")

st.caption(
    "Facility identity is best-effort matching of public listing text "
    "(name + city + state). Overlap indicates shared listings only — it "
    "is not a claim about site workload or performance."
)

guarded_footer()
