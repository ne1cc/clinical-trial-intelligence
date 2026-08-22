"""OMOP Explorer — condition and intervention concept mappings."""

import plotly.express as px
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("OMOP Explorer", icon=":material/hub:")
data.require_warehouse()

conditions = data.omop_condition_summary()
drugs = data.omop_drug_summary()

st.subheader("Condition concept mapping (SNOMED CT)")
col1, col2 = st.columns(2)
col1.metric("Mapped conditions", f"{len(conditions):,}")
col2.metric(
    "Total occurrences", f"{int(conditions['occurrence_count'].sum()):,}"
)

if not conditions.empty:
    fig = px.bar(
        conditions.head(10),
        x="occurrence_count",
        y="condition_concept_name",
        orientation="h",
        color="dementia_relevant_pct",
        labels={
            "occurrence_count": "Occurrences",
            "condition_concept_name": "OMOP Concept",
            "dementia_relevant_pct": "% Dementia-Relevant",
        },
    )
    fig.update_layout(height=350, yaxis_categoryorder="total ascending")
    st.plotly_chart(fig, width="stretch")

st.dataframe(
    conditions,
    hide_index=True,
    width="stretch",
    column_config={
        "dementia_relevant_pct": st.column_config.NumberColumn(
            "Dementia %", format="%.1f"
        ),
    },
)

st.divider()
st.subheader("Intervention concept mapping (RxNorm / SNOMED)")
col3, col4 = st.columns(2)
col3.metric("Mapped interventions", f"{len(drugs):,}")
col4.metric(
    "Total exposures", f"{int(drugs['exposure_count'].sum()):,}"
)

if not drugs.empty:
    st.dataframe(
        drugs,
        hide_index=True,
        width="stretch",
        column_config={
            "mapped_count": st.column_config.NumberColumn("Mapped"),
        },
    )

st.caption(
    "Concept mappings use a curated seed of ADRD-relevant SNOMED CT and "
    "RxNorm codes. Unmapped entries reflect novel or non-standard interventions."
)
guarded_footer()
