"""Geography Trends — state-level listing activity (choropleth + monthly)."""

import plotly.express as px
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Geography Trends")
data.require_warehouse()

trends = data.condition_geography_trends()

condition_options = sorted(trends["condition_group"].dropna().unique())
default_index = (
    condition_options.index("alzheimers_disease")
    if "alzheimers_disease" in condition_options
    else 0
)
condition = st.sidebar.selectbox("Condition group", condition_options, index=default_index)
scoped = trends[trends["condition_group"] == condition]

latest_month = scoped["activity_month"].max()
latest = scoped[scoped["activity_month"] == latest_month]

st.subheader(f"Recruiting listings by state — {condition}")
fig = px.choropleth(
    latest,
    locations="state_normalized",
    locationmode="USA-states",
    color="recruiting_trial_count",
    scope="usa",
    labels={"recruiting_trial_count": "Recruiting listings"},
)
st.plotly_chart(fig, width="stretch")
st.caption(
    f"Month shown: {latest_month}. Counts are trial listings with at "
    "least one usable U.S. site in that state — not patient availability."
)

st.divider()
st.subheader("Top states")
st.dataframe(
    latest.sort_values("recruiting_trial_count", ascending=False)[
        [
            "state_normalized",
            "trial_count",
            "recruiting_trial_count",
            "sponsor_count",
            "newly_posted_in_month_proxy",
            "recruiting_growth_3m",
        ]
    ].head(20),
    hide_index=True,
    width="stretch",
)

months = scoped["activity_month"].nunique()
if months > 1:
    st.divider()
    st.subheader("Monthly trend")
    fig2 = px.line(
        scoped.groupby("activity_month", as_index=False)["recruiting_trial_count"].sum(),
        x="activity_month",
        y="recruiting_trial_count",
        markers=True,
    )
    st.plotly_chart(fig2, width="stretch")
else:
    st.info(
        "Trend lines need multiple monthly snapshots; this project has "
        f"accrued {months} snapshot month so far. Re-run `make pipeline` "
        "over time to build the series."
    )

guarded_footer()
