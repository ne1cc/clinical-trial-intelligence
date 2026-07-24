"""Reusable sidebar filters over segment dataframes."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def segment_filters(
    frame: pd.DataFrame,
    condition_col: str = "condition_group",
    state_col: str = "state_normalized",
    phase_col: str = "phase_normalized",
) -> pd.DataFrame:
    """Sidebar multiselects for condition group / state / phase."""
    st.sidebar.header("Filters")
    filtered = frame

    if condition_col in frame.columns:
        options = sorted(frame[condition_col].dropna().unique())
        selected = st.sidebar.multiselect("Condition group", options)
        if selected:
            filtered = filtered[filtered[condition_col].isin(selected)]

    if state_col in frame.columns:
        options = sorted(frame[state_col].dropna().unique())
        selected = st.sidebar.multiselect("State", options)
        if selected:
            filtered = filtered[filtered[state_col].isin(selected)]

    if phase_col in frame.columns:
        options = sorted(frame[phase_col].dropna().unique())
        selected = st.sidebar.multiselect("Phase", options)
        if selected:
            filtered = filtered[filtered[phase_col].isin(selected)]

    st.sidebar.caption(f"{len(filtered):,} of {len(frame):,} rows shown")
    return filtered
