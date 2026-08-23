"""Smoke tests: every dashboard page must execute without exceptions.

Requires a built warehouse; skipped otherwise (e.g. in CI without data).
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse" / "clinical_trials.duckdb"

pytestmark = pytest.mark.skipif(
    not WAREHOUSE.exists(), reason="warehouse not built (run make pipeline)"
)

PAGES = [
    "dashboard/pages/0_Overview.py",
    "dashboard/pages/1_Priority_Queue.py",
    "dashboard/pages/2_Competition_Landscape.py",
    "dashboard/pages/3_Geography_Trends.py",
    "dashboard/pages/4_Site_Overlap.py",
    "dashboard/pages/5_Sponsor_Landscape.py",
    "dashboard/pages/6_Data_Reliability.py",
    "dashboard/pages/7_Trial_Explorer.py",
    "dashboard/pages/8_Eligibility_Criteria.py",
    "dashboard/pages/9_OMOP_Explorer.py",
    "dashboard/pages/10_Enrollment_Forecast.py",
]

# Overview is exercised through the router rather than standalone: it links to a
# sibling page with st.page_link, which resolves against the page graph that
# st.navigation builds. Running app.py renders the default page, which is
# Overview, so coverage is equivalent and matches how the app actually runs.
RUNNABLE = ["dashboard/app.py"] + [
    script for script in PAGES if not script.endswith("0_Overview.py")
]


@pytest.mark.parametrize("script", RUNNABLE)
def test_page_runs_without_exception(script):
    from streamlit.testing.v1 import AppTest

    if str(ROOT / "dashboard") not in sys.path:
        sys.path.insert(0, str(ROOT / "dashboard"))
    at = AppTest.from_file(str(ROOT / script), default_timeout=60)
    at.run()
    assert not at.exception, at.exception[0].value if at.exception else ""


def test_every_page_shows_disclaimer():
    sys.path.insert(0, str(ROOT / "dashboard"))
    from components.guardrails import DISCLAIMER

    assert "not" in DISCLAIMER.lower()
    for script in PAGES:
        source = (ROOT / script).read_text(encoding="utf-8")
        assert "page_setup(" in source, f"{script} must use page_setup (guardrail banner)"


COLUMN_CONFIG_KEY = re.compile(r'^\s*"([^"]+)":\s*st\.column_config\.', re.MULTILINE)


@pytest.mark.parametrize("script", RUNNABLE)
def test_column_config_keys_match_real_columns(script):
    """A column_config key that matches no column is silently ignored.

    Streamlit does not raise on an unknown key — the column just renders
    untyped — so a typo would otherwise pass every other test in this file.
    """
    from streamlit.testing.v1 import AppTest

    # app.py is the router; its rendered tables come from the Overview page.
    source_path = ROOT / (
        "dashboard/pages/0_Overview.py" if script.endswith("app.py") else script
    )
    keys = set(COLUMN_CONFIG_KEY.findall(source_path.read_text(encoding="utf-8")))
    if not keys:
        pytest.skip("page configures no dataframe columns")

    if str(ROOT / "dashboard") not in sys.path:
        sys.path.insert(0, str(ROOT / "dashboard"))
    at = AppTest.from_file(str(ROOT / script), default_timeout=60)
    at.run()

    rendered = set()
    for element in at.dataframe:
        rendered.update(str(column) for column in element.value.columns)

    unknown = sorted(keys - rendered)
    assert not unknown, (
        f"{source_path.name} configures columns that do not exist: {unknown}"
    )


def test_every_page_is_registered_in_navigation():
    """A new page must appear in the sidebar, not silently fail to ship."""
    source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    missing = [
        page.name
        for page in sorted((ROOT / "dashboard" / "pages").glob("*.py"))
        if f"pages/{page.name}" not in source
    ]
    assert not missing, f"pages missing from app.py navigation: {missing}"
