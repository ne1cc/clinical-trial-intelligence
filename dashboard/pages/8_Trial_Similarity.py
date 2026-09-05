"""Trial Similarity Explorer — deterministic protocol comparability."""

import pandas as pd
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

FACTOR_LABELS = {
    "same_condition": "Same condition",
    "same_phase": "Same phase",
    "geography_overlap": "Geography overlap",
    "intervention_type_overlap": "Intervention type overlap",
    "study_design_match": "Study design match",
    "eligibility_compatible": "Eligibility compatible",
    "enrollment_band_match": "Enrollment band match",
}

page_setup("Trial Similarity Explorer")
data.require_warehouse()

st.info(
    "This page scores **structural trial-design comparability** — "
    "shared phase, geography, intervention type, study design, and "
    "eligibility criteria. It is not a claim of clinical equivalence, "
    "and unlike the Competition Landscape and Priority Queue pages, it "
    "is not itself a competition or recruitment signal."
)

trials = data.trial_explorer()
search = st.text_input("Search for an index trial by NCT ID or title")

candidates = trials
if search:
    needle = search.strip().lower()
    mask = candidates["brief_title"].str.lower().str.contains(needle, na=False) | candidates[
        "nct_id"
    ].str.lower().str.contains(needle, na=False)
    candidates = candidates[mask]

if candidates.empty:
    st.warning("No trials match that search.")
    st.stop()

options = {
    f"{row.nct_id} — {row.brief_title}": row.nct_id for row in candidates.head(50).itertuples()
}
selected_label = st.selectbox("Select the index trial", list(options))
selected_nct_id = options[selected_label]

matches = (
    data.trial_similarity(selected_nct_id)
    .merge(
        trials[["nct_id", "brief_title", "registry_url"]],
        left_on="nct_id_b",
        right_on="nct_id",
        how="left",
    )
    .drop(columns="nct_id")
)

if matches.empty:
    st.info("No comparable trials found in the current warehouse for this trial.")
    guarded_footer()
    st.stop()

st.subheader(f"Top comparable trials for {selected_nct_id}")
st.caption("Click a row to see its full factor breakdown below.")
match_columns = [
    "similarity_rank",
    "nct_id_b",
    "brief_title",
    "registry_url",
    "similarity_score",
    "similarity_explanation",
]
match_event = st.dataframe(
    matches[match_columns],
    hide_index=True,
    width="stretch",
    column_config={
        "nct_id_b": st.column_config.TextColumn("NCT ID"),
        "brief_title": st.column_config.TextColumn("Brief title", width="large"),
        "registry_url": st.column_config.LinkColumn(
            "Registry record",
            help="Opens the public ClinicalTrials.gov record",
            display_text="View on ClinicalTrials.gov",
        ),
        "similarity_score": st.column_config.NumberColumn(format="%.4f"),
    },
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = match_event.selection.rows if match_event.selection else []
if selected_rows:
    m = matches.iloc[selected_rows[0]]
    st.subheader(f"Factor breakdown — {selected_nct_id} vs {m['nct_id_b']}")
    breakdown = pd.DataFrame(
        [
            {
                "Factor": label,
                "Match (1=yes)": m[factor],
                "Weight": m[f"weight_{factor}"],
                "Weighted contribution": m[f"weighted_{factor}"],
            }
            for factor, label in FACTOR_LABELS.items()
        ]
    )
    st.dataframe(breakdown, hide_index=True, width="stretch")
    st.metric(
        "Weighted total",
        f"{m['similarity_score']:.4f}",
        help=(
            "similarity_score for this pair — the weighted sum of all seven "
            "factors, rounded to 4 decimals. Individual contributions are "
            "rounded first, so their displayed sum can differ in the last decimal."
        ),
    )
    st.caption(m["similarity_explanation"])

guarded_footer()
