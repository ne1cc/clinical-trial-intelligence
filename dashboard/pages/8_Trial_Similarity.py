"""Trial Similarity Explorer — deterministic protocol comparability."""

import pandas as pd
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

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
    mask = candidates["brief_title"].str.lower().str.contains(
        needle, na=False
    ) | candidates["nct_id"].str.lower().str.contains(needle, na=False)
    candidates = candidates[mask]

if candidates.empty:
    st.warning("No trials match that search.")
    st.stop()

options = {
    f"{row.nct_id} — {row.brief_title}": row.nct_id
    for row in candidates.head(50).itertuples()
}
selected_label = st.selectbox("Select the index trial", list(options))
selected_nct_id = options[selected_label]

matches = data.trial_similarity(selected_nct_id)

if matches.empty:
    st.info("No comparable trials found in the current warehouse for this trial.")
    guarded_footer()
    st.stop()

st.subheader(f"Top comparable trials for {selected_nct_id}")
st.caption("Click a row to see its full factor breakdown below.")
match_columns = [
    "similarity_rank",
    "nct_id_b",
    "similarity_score",
    "similarity_explanation",
]
match_event = st.dataframe(
    matches[match_columns],
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = match_event.selection.rows if match_event.selection else []
if selected_rows:
    m = matches.iloc[selected_rows[0]]
    st.subheader(f"Factor breakdown — {selected_nct_id} vs {m['nct_id_b']}")
    factor_rows = [
        (
            "Same condition",
            m["same_condition"],
            m["weight_same_condition"],
            m["weighted_same_condition"],
        ),
        ("Same phase", m["same_phase"], m["weight_same_phase"], m["weighted_same_phase"]),
        (
            "Geography overlap",
            m["geography_overlap"],
            m["weight_geography_overlap"],
            m["weighted_geography_overlap"],
        ),
        (
            "Intervention type overlap",
            m["intervention_type_overlap"],
            m["weight_intervention_type_overlap"],
            m["weighted_intervention_type_overlap"],
        ),
        (
            "Study design match",
            m["study_design_match"],
            m["weight_study_design_match"],
            m["weighted_study_design_match"],
        ),
        (
            "Eligibility compatible",
            m["eligibility_compatible"],
            m["weight_eligibility_compatible"],
            m["weighted_eligibility_compatible"],
        ),
        (
            "Enrollment band match",
            m["enrollment_band_match"],
            m["weight_enrollment_band_match"],
            m["weighted_enrollment_band_match"],
        ),
    ]
    breakdown = pd.DataFrame(
        factor_rows,
        columns=["Factor", "Match (1=yes)", "Weight", "Weighted contribution"],
    )
    st.dataframe(breakdown, hide_index=True, width="stretch")
    weighted_total = sum(row[3] for row in factor_rows)
    st.metric(
        "Weighted total (sum of weighted contributions)",
        f"{weighted_total:.4f}",
        help="Matches similarity_score for this pair.",
    )
    st.caption(m["similarity_explanation"])

guarded_footer()
