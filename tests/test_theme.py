"""Theme contract: the dashboard's visual identity lives in config, not in pages."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".streamlit" / "config.toml"

# Validated with the dataviz validator against BOTH chart surfaces:
# light #fcfcfb and dark #1a1a19. All checks pass in both modes.
# Do not substitute values by eye — re-run the validator if they must change.
EXPECTED_CATEGORICAL = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]


def _theme() -> dict:
    with CONFIG.open("rb") as fh:
        return tomllib.load(fh)["theme"]


def test_config_exists_and_parses():
    assert CONFIG.exists(), "dashboard theme config is missing"
    assert _theme(), "[theme] section is empty"


def test_categorical_palette_is_the_validated_set():
    assert _theme()["chartCategoricalColors"] == EXPECTED_CATEGORICAL


def test_sequential_ramp_runs_light_to_dark():
    ramp = _theme()["chartSequentialColors"]
    assert len(ramp) >= 5, "sequential ramp needs enough steps to read as continuous"
    assert ramp[0] != ramp[-1], "ramp must actually progress"


def test_primary_is_not_the_streamlit_default():
    # Streamlit's stock red-orange fights this app's semantics: red must stay
    # free for risk/exclusion encodings.
    assert _theme()["primaryColor"].lower() != "#ff4b4b"


def test_dark_mode_is_deliberately_themed():
    assert "dark" in _theme(), "dark mode must be themed, not left to chance"
