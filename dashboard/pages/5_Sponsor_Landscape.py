"""Sponsor Landscape — lead sponsors of currently recruiting trials."""

import plotly.express as px
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Sponsor Landscape")
data.require_warehouse()

sponsors = data.sponsor_landscape()

with st.container(border=True):
    col1, col2 = st.columns(2)
    col1.metric("Lead sponsors (recruiting)", f"{len(sponsors):,}")
    col2.metric(
        "Recruiting listings",
        f"{int(sponsors['recruiting_trial_count'].sum()):,}",
    )

st.subheader("Top lead sponsors by recruiting listings")
top = sponsors.head(20)
fig = px.bar(
    top,
    y="lead_sponsor",
    x="recruiting_trial_count",
    color="sponsor_class",
    orientation="h",
)
fig.update_layout(yaxis=dict(autorange="reversed"), height=560)
st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("All lead sponsors")
st.dataframe(
    sponsors,
    hide_index=True,
    width="stretch",
    column_config={
        "lead_sponsor": st.column_config.TextColumn("Lead sponsor", width="large"),
        "sponsor_class": st.column_config.TextColumn("Registry sponsor class"),
        "recruiting_trial_count": st.column_config.NumberColumn(
            "Recruiting listings", format="%d"
        ),
        "phase_mix": st.column_config.TextColumn("Phase mix", width="medium"),
    },
)

st.caption(
    "Counts of registry listings by lead sponsor — not market share, "
    "spend, or enrollment performance."
)

guarded_footer()
