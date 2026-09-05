"""Smoke tests: every dashboard page must execute without exceptions.

Requires a built warehouse; skipped otherwise (e.g. in CI without data).
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse" / "clinical_trials.duckdb"

PAGES = [
    "dashboard/app.py",
    "dashboard/pages/1_Priority_Queue.py",
    "dashboard/pages/2_Competition_Landscape.py",
    "dashboard/pages/3_Geography_Trends.py",
    "dashboard/pages/4_Site_Overlap.py",
    "dashboard/pages/5_Sponsor_Landscape.py",
    "dashboard/pages/6_Data_Reliability.py",
    "dashboard/pages/7_Trial_Explorer.py",
    "dashboard/pages/8_Trial_Similarity.py",
]


def warehouse_has_marts() -> bool:
    if not WAREHOUSE.exists():
        return False
    try:
        import duckdb

        con = duckdb.connect(str(WAREHOUSE), read_only=True)
        tables = con.execute("SHOW ALL TABLES").fetchall()
        schemas = {t[1] for t in tables}
        return "main_marts" in schemas
    except Exception:
        return False


@pytest.mark.skipif(
    not warehouse_has_marts(), reason="marts not built in warehouse (run make pipeline)"
)
@pytest.mark.parametrize("script", PAGES)
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
