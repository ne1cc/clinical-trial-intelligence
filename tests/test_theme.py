"""Theme contract: the dashboard's visual identity lives in config, not in pages."""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".streamlit" / "config.toml"
PAGES_DIR = ROOT / "dashboard" / "pages"
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")

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


def test_pages_never_hardcode_colors():
    """Color belongs in config.toml or components/palette.py — never in a page.

    Hardcoded hex in a page silently overrides the theme, which is how a
    dashboard drifts back into looking unthemed one chart at a time.
    """
    offenders = []
    for page in sorted(PAGES_DIR.glob("*.py")):
        for lineno, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if HEX.search(line):
                offenders.append(f"{page.name}:{lineno}: {line.strip()}")
    assert not offenders, "hardcoded colors found:\n" + "\n".join(offenders)


def test_signal_band_scale_is_ordinal_and_complete():
    sys.path.insert(0, str(ROOT / "dashboard"))
    from components.palette import SIGNAL_BAND_SCALE

    assert list(SIGNAL_BAND_SCALE) == ["low", "moderate", "elevated"]
    assert len(set(SIGNAL_BAND_SCALE.values())) == 3, "each band needs its own step"
