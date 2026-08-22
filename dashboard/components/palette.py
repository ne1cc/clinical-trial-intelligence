"""Chart color roles Streamlit's global theme cannot express.

Streamlit themes categorical and sequential chart colors globally, but two
encodings here are neither. The competition signal band is *ordinal*, and
inclusion/exclusion is *semantic*. Both live here so no page hardcodes a hex.
"""

from __future__ import annotations

import streamlit as st

# Ordinal blue ramp, low -> elevated. Validated with the dataviz validator in
# both modes: monotone lightness, adjacent dL >= 0.06, single hue, ends clear
# the surface. Blue rather than a red "danger" ramp is deliberate: the bands
# are relative percentile cuts, and clinical_interpretation_guardrails.md
# forbids presenting them as verdicts.
SIGNAL_BAND_SCALE: dict[str, str] = {
    "low": "#86b6ef",
    "moderate": "#3987e5",
    "elevated": "#184f95",
}

SIGNAL_BAND_ORDER: list[str] = list(SIGNAL_BAND_SCALE)


def semantic(role: str) -> str:
    """Return a themed semantic color, e.g. semantic("green")."""
    return st.get_option(f"theme.{role}Color")
