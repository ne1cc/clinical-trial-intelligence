"""Trial Explorer — individual registry records with links to ClinicalTrials.gov."""

import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Trial Explorer")
data.require_warehouse()

trials = data.trial_explorer()

col1, col2 = st.columns(3)[:2]
col1.metric("Trials in warehouse", f"{len(trials):,}")
col2.metric(
    "Currently recruiting",
    f"{int((trials['overall_status'] == 'RECRUITING').sum()):,}",
)

statuses = sorted(trials["overall_status"].dropna().unique())
phases = sorted(trials["phase"].dropna().unique())
profiles = sorted(trials["indication_profile"].dropna().unique())

fcol1, fcol2, fcol3, fcol4 = st.columns(4)
profile_sel = fcol1.multiselect("Indication profile", profiles, default=[])
status_sel = fcol2.multiselect("Overall status", statuses, default=[])
phase_sel = fcol3.multiselect("Phase", phases, default=[])
search = fcol4.text_input("Search title / sponsor / NCT ID")

filtered = trials
if profile_sel:
    filtered = filtered[filtered["indication_profile"].isin(profile_sel)]
if status_sel:
    filtered = filtered[filtered["overall_status"].isin(status_sel)]
if phase_sel:
    filtered = filtered[filtered["phase"].isin(phase_sel)]
if search:
    needle = search.strip().lower()
    mask = (
        filtered["brief_title"].str.lower().str.contains(needle, na=False)
        | filtered["lead_sponsor"].str.lower().str.contains(needle, na=False)
        | filtered["nct_id"].str.lower().str.contains(needle, na=False)
        | (
            filtered["why_stopped"].str.lower().str.contains(needle, na=False)
            if "why_stopped" in filtered.columns
            else False
        )
    )
    filtered = filtered[mask]

st.caption(f"{len(filtered):,} of {len(trials):,} trials shown.")

st.dataframe(
    filtered,
    hide_index=True,
    width="stretch",
    column_config={
        "registry_url": st.column_config.LinkColumn(
            "Registry record",
            help="Opens the public ClinicalTrials.gov record",
            display_text="View on ClinicalTrials.gov",
        ),
        "nct_id": st.column_config.TextColumn("NCT ID"),
        "brief_title": st.column_config.TextColumn("Brief title", width="large"),
        "overall_status": st.column_config.TextColumn("Status"),
        "indication_profile": st.column_config.TextColumn("Indication profile"),
        "why_stopped": st.column_config.TextColumn("Why Stopped / Reason", width="medium"),
        "study_first_post_date": st.column_config.DateColumn("First posted"),
        "enrollment_count": st.column_config.NumberColumn("Planned enrollment"),
        "us_states": st.column_config.TextColumn("Listed U.S. states"),
    },
)

st.caption(
    "Each row is a public registry record as of this project's latest snapshot; "
    "the link opens the authoritative current record on ClinicalTrials.gov. "
    "Listed enrollment is the sponsor-reported plan, not actual accrual."
)

guarded_footer()
