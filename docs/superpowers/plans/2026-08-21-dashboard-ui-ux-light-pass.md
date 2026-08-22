# Dashboard UI/UX Light Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Streamlit dashboard a deliberate visual identity and grouped navigation, without changing any metric, model, or data contract.

**Architecture:** Config-first. Streamlit 1.59 natively themes chart palettes, borders, dataframes, metrics, and typography via `.streamlit/config.toml`, so nearly all visual work is configuration rather than CSS. Navigation moves from flat auto-discovery to explicit `st.navigation` sections, which turns `app.py` into a router and relocates the Overview page. Custom CSS is a residual, added only where a browser check proves config cannot reach.

**Tech Stack:** Python 3.13, Streamlit 1.59.1, Plotly Express, DuckDB (read-only), pytest, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-08-21-dashboard-ui-ux-light-pass-design.md`

## Global Constraints

- Streamlit floor stays `>=1.36` in `pyproject.toml`; installed version is **1.59.1**. Do not bump the floor.
- **No new metrics, pages, data sources, or dbt changes.** Presentation only.
- **No third-party Streamlit component packages.** Native primitives only.
- Every page must call `page_setup()` so the guardrail disclaimer renders — this is test-enforced and must not weaken.
- Existing page filenames and numeric prefixes are **kept**; `st.navigation` controls order and labels.
- The warehouse is opened `read_only=True`. Never write to it.
- Baseline test suite is **95 passed**. It must return to green after every task.
- Color belongs in `.streamlit/config.toml` or `dashboard/components/palette.py`. **Never hardcode a hex value in a page.**
- Run tests with `.venv/bin/python -m pytest` (or `make test`). Lint with `make lint`.

---

## File Structure

| File | Responsibility |
|---|---|
| `.streamlit/config.toml` (new) | The entire visual identity: palette, typography, surfaces, chart colors |
| `dashboard/components/palette.py` (new) | The two chart encodings Streamlit's global theme cannot express: the ordinal signal-band ramp and semantic role lookup |
| `dashboard/app.py` (rewrite) | Router only — `st.navigation` section registration |
| `dashboard/pages/0_Overview.py` (new) | Overview page content, moved out of `app.py` |
| `dashboard/pages/*.py` (modify) | Remove local color overrides; KPI containers; `column_config` |
| `dashboard/components/theme.py` (conditional) | Residual CSS, only if a browser check finds a gap config cannot close |
| `tests/test_theme.py` (new) | Theme contract: palette values, no hardcoded page colors |
| `tests/test_dashboard_smoke.py` (modify) | Extend to all 11 pages; assert nav registration |

---

## Palette — computed, not chosen

These values were produced by running the `dataviz` skill's validator
(`scripts/validate_palette.js`) and are **not** to be substituted by eye.

Streamlit exposes chart colors **globally only** — there is no
`theme.light.chartCategoricalColors` / `theme.dark.…` variant (verified against
the installed config template). One palette therefore has to serve both
surfaces. The reference palette's *light* column fails on the dark surface
(4 slots outside the lightness band). Its **dark** column passes every check on
**both** surfaces, so that is the set used:

```
#3987e5  #d95926  #199e70  #c98500  #d55181  #008300  #9085e9  #e66767
```

- Light surface `#fcfcfb`: ALL CHECKS PASS. One WARN — `#c98500` at 2.99:1 —
  triggers the **relief rule**, which is satisfied structurally: every chart in
  this dashboard sits beside a data table.
- Dark surface `#1a1a19`: ALL CHECKS PASS, no warnings.

Ordinal ramp for the competition signal band (`low → moderate → elevated`):

```
#86b6ef  #3987e5  #184f95
```

Passes the ordinal checks in both modes (monotone lightness, adjacent ΔL ≥ 0.06,
single hue, light end clears the surface).

**Why the signal band is blue and not a red "danger" ramp:** the band is
*ordinal*, not categorical, so a single-hue ramp is the correct form. More
importantly, `docs/clinical_interpretation_guardrails.md` forbids presenting
these signals as verdicts — a red "elevated" would encode a judgment the
project explicitly disclaims. Blue carries magnitude without implying alarm.

`chartDivergingColors` is intentionally **not set**: no chart in this dashboard
uses a diverging encoding (YAGNI).

---

### Task 1: Theme configuration

**Files:**
- Create: `.streamlit/config.toml`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `.streamlit/config.toml` with `theme.chartCategoricalColors`,
  `theme.chartSequentialColors`, and semantic `theme.greenColor` /
  `theme.redColor`, all readable at runtime via
  `st.get_option("theme.<key>")`. Task 2 consumes these.

- [ ] **Step 1: Write the failing test**

Create `tests/test_theme.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: FAIL — `assert CONFIG.exists()` fails, config file does not exist.

- [ ] **Step 3: Create the config**

Create `.streamlit/config.toml`. **Key ordering matters in TOML** — every
top-level `[theme]` key must appear before the `[theme.dark]` and
`[theme.sidebar]` tables, or it will be parsed into the wrong table.

```toml
# Dashboard theme — clinical analytics identity.
#
# Chart palettes are GLOBAL in Streamlit (there is no theme.light/theme.dark
# variant for chart colors), so the categorical set below was chosen to pass
# the dataviz validator against BOTH the light and dark chart surfaces.
# See docs/superpowers/plans/2026-08-21-dashboard-ui-ux-light-pass.md.

[theme]
base = "light"
primaryColor = "#2a78d6"
backgroundColor = "#fcfcfb"
secondaryBackgroundColor = "#f2f1ee"
textColor = "#0b0b0b"
linkColor = "#2a78d6"
borderColor = "#dedcd6"
linkUnderline = false

showWidgetBorder = true
showSidebarBorder = true
baseRadius = "6px"
buttonRadius = "6px"

# Inter loads from Google Fonts; offline it degrades to the system sans stack.
font = "'Inter':https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
headingFont = "'Inter':https://fonts.googleapis.com/css2?family=Inter:wght@600;700&display=swap"
baseFontSize = 14
headingFontSizes = ["28px", "22px", "18px", "16px", "14px", "12px"]
headingFontWeights = [700, 600, 600, 600, 500, 500]
metricValueFontSize = "30px"
metricValueFontWeight = 600

dataframeBorderColor = "#dedcd6"
dataframeHeaderBackgroundColor = "#f2f1ee"

greenColor = "#008300"
redColor = "#e34948"
yellowColor = "#eda100"
orangeColor = "#eb6834"
blueColor = "#2a78d6"
grayColor = "#52514e"

chartCategoricalColors = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]

chartSequentialColors = [
    "#cde2fb",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
]

[theme.dark]
backgroundColor = "#1a1a19"
secondaryBackgroundColor = "#262624"
textColor = "#ffffff"
borderColor = "#383835"
primaryColor = "#3987e5"
linkColor = "#3987e5"
greenColor = "#008300"
redColor = "#e66767"
dataframeBorderColor = "#383835"
dataframeHeaderBackgroundColor = "#262624"

[theme.sidebar]
backgroundColor = "#f7f6f3"
borderColor = "#dedcd6"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 100 passed (95 baseline + 5 new).

- [ ] **Step 6: Commit**

```bash
git add .streamlit/config.toml tests/test_theme.py
git commit -m "feat(dashboard): add validated clinical theme and chart palette"
```

---

### Task 2: Route all chart color through the theme

Removes local color overrides so the theme actually inherits, and moves the two
encodings the global theme cannot express into a shared module.

**Files:**
- Create: `dashboard/components/palette.py`
- Modify: `dashboard/pages/2_Competition_Landscape.py:28-40`
- Modify: `dashboard/pages/3_Geography_Trends.py:32`
- Modify: `dashboard/pages/8_Eligibility_Criteria.py:39`
- Modify: `dashboard/pages/9_OMOP_Explorer.py:33`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: `theme.greenColor` / `theme.redColor` from Task 1's config.
- Produces: `components.palette.SIGNAL_BAND_SCALE: dict[str, str]` mapping
  `"low" | "moderate" | "elevated"` to hex, and
  `components.palette.semantic(role: str) -> str` returning a themed color for
  a role name such as `"green"` or `"red"`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_theme.py`:

```python
import re

PAGES_DIR = ROOT / "dashboard" / "pages"
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


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
    import sys

    sys.path.insert(0, str(ROOT / "dashboard"))
    from components.palette import SIGNAL_BAND_SCALE

    assert list(SIGNAL_BAND_SCALE) == ["low", "moderate", "elevated"]
    assert len(set(SIGNAL_BAND_SCALE.values())) == 3, "each band needs its own step"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v -k "hardcode or signal_band"`
Expected: FAIL — `test_pages_never_hardcode_colors` reports
`8_Eligibility_Criteria.py:39` (`#2ecc71`, `#e74c3c`), and
`test_signal_band_scale_is_ordinal_and_complete` fails with
`ModuleNotFoundError: components.palette`.

- [ ] **Step 3: Create the palette module**

Create `dashboard/components/palette.py`:

```python
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
```

- [ ] **Step 4: Remove the local color overrides**

In `dashboard/pages/3_Geography_Trends.py`, delete this line from the
`px.choropleth(...)` call so `chartSequentialColors` applies:

```python
    color_continuous_scale="Blues",
```

In `dashboard/pages/9_OMOP_Explorer.py`, delete the identical line from the
`px.bar(...)` call:

```python
    color_continuous_scale="Blues",
```

In `dashboard/pages/8_Eligibility_Criteria.py`, add the import at the top with
the other `components` imports:

```python
from components.palette import semantic
```

and replace the hardcoded map:

```python
        color_discrete_map={"inclusion": "#2ecc71", "exclusion": "#e74c3c"},
```

with:

```python
        color_discrete_map={
            "inclusion": semantic("green"),
            "exclusion": semantic("red"),
        },
```

In `dashboard/pages/2_Competition_Landscape.py`, add the import:

```python
from components.palette import SIGNAL_BAND_ORDER, SIGNAL_BAND_SCALE
```

then in the `px.scatter(...)` call replace:

```python
    category_orders={"competition_signal_band": ["low", "moderate", "elevated"]},
```

with:

```python
    category_orders={"competition_signal_band": SIGNAL_BAND_ORDER},
    color_discrete_map=SIGNAL_BAND_SCALE,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 6: Run the full suite and lint**

Run: `.venv/bin/python -m pytest tests/ -q && make lint`
Expected: 102 passed; ruff reports no issues.

- [ ] **Step 7: Commit**

```bash
git add dashboard/components/palette.py dashboard/pages tests/test_theme.py
git commit -m "refactor(dashboard): route all chart color through the theme"
```

---

### Task 3: Grouped navigation

**Files:**
- Create: `dashboard/pages/0_Overview.py`
- Rewrite: `dashboard/app.py`
- Modify: `tests/test_dashboard_smoke.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: `dashboard/app.py` as a router whose source contains a
  `pages/<filename>` string for every file in `dashboard/pages/`. Task 7's
  documentation describes this structure.

- [ ] **Step 1: Write the failing test**

In `tests/test_dashboard_smoke.py`, replace the `PAGES` list with full coverage
(pages 8, 9, and 10 are currently untested) and add the registration test:

```python
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


def test_every_page_is_registered_in_navigation():
    """A new page must appear in the sidebar, not silently fail to ship."""
    source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    missing = [
        page.name
        for page in sorted((ROOT / "dashboard" / "pages").glob("*.py"))
        if f"pages/{page.name}" not in source
    ]
    assert not missing, f"pages missing from app.py navigation: {missing}"
```

Also update `test_every_page_shows_disclaimer` — `app.py` is becoming a router
and no longer calls `page_setup()`, so the assertion must run over `PAGES`
only. The existing loop already iterates `PAGES`, so removing
`"dashboard/app.py"` from that list (done above) is sufficient. Leave the
assertion body unchanged.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_dashboard_smoke.py -v`
Expected: FAIL — `test_every_page_is_registered_in_navigation` fails (app.py has
no `pages/...` strings), and the parametrized run for
`dashboard/pages/0_Overview.py` fails because the file does not exist.

- [ ] **Step 3: Move the Overview content into a page**

Create `dashboard/pages/0_Overview.py` containing the **current full contents of
`dashboard/app.py`, unchanged**. The existing `st.page_link("pages/1_Priority_Queue.py", …)`
call stays exactly as written: `st.Page` paths resolve relative to the
entrypoint's directory, which is still `dashboard/`.

- [ ] **Step 4: Rewrite app.py as a router**

Replace the entire contents of `dashboard/app.py` with:

```python
"""Router — Clinical Trial Access & Recruitment Competition Intelligence."""

import streamlit as st

st.set_page_config(
    page_title="Clinical Trial Intelligence",
    page_icon=":material/monitor_heart:",
    layout="wide",
)

NAVIGATION = {
    "": [
        st.Page(
            "pages/0_Overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
        ),
    ],
    "Feasibility Signals": [
        st.Page("pages/1_Priority_Queue.py", title="Priority Queue", icon=":material/format_list_numbered:"),
        st.Page("pages/2_Competition_Landscape.py", title="Competition Landscape", icon=":material/scatter_plot:"),
        st.Page("pages/3_Geography_Trends.py", title="Geography Trends", icon=":material/public:"),
        st.Page("pages/5_Sponsor_Landscape.py", title="Sponsor Landscape", icon=":material/apartment:"),
        st.Page("pages/4_Site_Overlap.py", title="Site Overlap", icon=":material/join_inner:"),
    ],
    "Clinical Data Explorer": [
        st.Page("pages/7_Trial_Explorer.py", title="Trial Explorer", icon=":material/search:"),
        st.Page("pages/8_Eligibility_Criteria.py", title="Eligibility Criteria", icon=":material/rule:"),
        st.Page("pages/9_OMOP_Explorer.py", title="OMOP Explorer", icon=":material/database:"),
    ],
    "Forecasting & Data Trust": [
        st.Page("pages/10_Enrollment_Forecast.py", title="Enrollment Forecast", icon=":material/trending_up:"),
        st.Page("pages/6_Data_Reliability.py", title="Data Reliability", icon=":material/verified:"),
    ],
}

st.navigation(NAVIGATION).run()
```

Note the section order deliberately differs from filename order: Sponsor
Landscape precedes Site Overlap because sponsor concentration is read before
facility overlap in a feasibility review.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dashboard_smoke.py -v`
Expected: PASS — 11 parametrized page tests plus the disclaimer and
registration tests.

- [ ] **Step 6: Verify the app boots**

Run: `make dashboard`
Expected: Streamlit starts; the sidebar shows Overview above three labeled
sections; every page opens without error. Stop the server with Ctrl-C.

- [ ] **Step 7: Run the full suite and lint**

Run: `.venv/bin/python -m pytest tests/ -q && make lint`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add dashboard/app.py dashboard/pages/0_Overview.py tests/test_dashboard_smoke.py
git commit -m "feat(dashboard): group navigation into sections via st.navigation"
```

---

### Task 4: KPI cards and consistent section rhythm

**Files:**
- Modify: `dashboard/pages/0_Overview.py`, `1_Priority_Queue.py`,
  `2_Competition_Landscape.py`, `5_Sponsor_Landscape.py`,
  `7_Trial_Explorer.py`, `9_OMOP_Explorer.py`, `10_Enrollment_Forecast.py`

**Interfaces:**
- Consumes: the `showWidgetBorder` / `baseRadius` / `borderColor` settings from
  Task 1, which is what makes `st.container(border=True)` read as a card.
- Produces: no importable surface; visual only.

- [ ] **Step 1: Wrap every KPI row in a bordered container**

For each page listed above, find the `st.columns(...)` block whose columns call
`.metric(...)` and wrap it. Example — in `dashboard/pages/0_Overview.py`,
change:

```python
col1, col2, col3, col4 = st.columns(4)
col1.metric("Trials tracked", f"{int(metrics['total_trials']):,}")
col2.metric("Currently recruiting", f"{int(metrics['recruiting_trials']):,}")
col3.metric("States with listed sites", int(metrics["states_with_sites"]))
col4.metric("Listed facilities", f"{int(metrics['listed_facilities']):,}")
```

to:

```python
with st.container(border=True):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Trials tracked", f"{int(metrics['total_trials']):,}")
    col2.metric("Currently recruiting", f"{int(metrics['recruiting_trials']):,}")
    col3.metric("States with listed sites", int(metrics["states_with_sites"]))
    col4.metric("Listed facilities", f"{int(metrics['listed_facilities']):,}")
```

Apply the same wrapping to the metric rows in `1_Priority_Queue.py` (the
three-band row), `2_Competition_Landscape.py`, `5_Sponsor_Landscape.py`,
`7_Trial_Explorer.py`, `9_OMOP_Explorer.py`, and `10_Enrollment_Forecast.py`.

**Do not** wrap `st.columns` blocks that are used for filter widgets rather than
metrics — for example the `fcol1, fcol2, fcol3` row in `7_Trial_Explorer.py`
stays as it is.

Note: `7_Trial_Explorer.py` currently builds its metric row with
`st.columns(3)[:2]`, which allocates three columns and discards one. Leave that
behavior alone; only add the wrapper.

- [ ] **Step 2: Add a divider before each major section heading**

On the same pages, insert `st.divider()` immediately before each `st.subheader(...)`
that starts a new section, so pages share one rhythm: KPI card → divider →
section → content. Do not add a divider before the first subheader when it
directly follows the KPI card, and do not add one immediately before
`guarded_footer()` — that function already emits its own divider.

- [ ] **Step 3: Run the smoke tests**

Run: `.venv/bin/python -m pytest tests/test_dashboard_smoke.py -q`
Expected: PASS — all 11 pages still execute.

- [ ] **Step 4: Run the full suite and lint**

Run: `.venv/bin/python -m pytest tests/ -q && make lint`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add dashboard/pages
git commit -m "style(dashboard): card KPI rows and standardize section rhythm"
```

---

### Task 5: Typed dataframe columns on every table page

Only `7_Trial_Explorer.py` currently passes `column_config`; every other table
renders raw untyped columns.

**Files:**
- Modify: `dashboard/pages/0_Overview.py`, `1_Priority_Queue.py`,
  `2_Competition_Landscape.py`, `3_Geography_Trends.py`, `4_Site_Overlap.py`,
  `5_Sponsor_Landscape.py`, `6_Data_Reliability.py`, `9_OMOP_Explorer.py`,
  `10_Enrollment_Forecast.py`

**Interfaces:**
- Consumes: `dataframeHeaderBackgroundColor` / `dataframeBorderColor` from Task 1.
- Produces: no importable surface; visual only.

- [ ] **Step 1: Add column_config to each st.dataframe call**

For every `st.dataframe(...)` call on the pages above, add a `column_config`
mapping that (a) gives each column a human-readable label and (b) types numeric
and score columns. Use `st.column_config.NumberColumn` with an explicit
`format` for scores and shares, and `st.column_config.TextColumn` with
`width="large"` for long free-text columns.

Worked example — in `dashboard/pages/0_Overview.py`, the queue preview becomes:

```python
st.dataframe(
    queue.head(10)[
        [
            "priority_rank",
            "condition_group",
            "state_normalized",
            "phase_normalized",
            "feasibility_review_priority_score",
            "priority_band",
            "recruiting_trial_count",
            "priority_explanation",
        ]
    ],
    hide_index=True,
    width="stretch",
    column_config={
        "priority_rank": st.column_config.NumberColumn("Rank", format="%d"),
        "condition_group": st.column_config.TextColumn("Condition group"),
        "state_normalized": st.column_config.TextColumn("State"),
        "phase_normalized": st.column_config.TextColumn("Phase"),
        "feasibility_review_priority_score": st.column_config.NumberColumn(
            "Priority score", format="%.3f"
        ),
        "priority_band": st.column_config.TextColumn("Band"),
        "recruiting_trial_count": st.column_config.NumberColumn(
            "Recruiting listings", format="%d"
        ),
        "priority_explanation": st.column_config.TextColumn(
            "Why this rank", width="large"
        ),
    },
)
```

Apply the same treatment to the remaining tables. Two rules to keep the
guardrails intact:

- Never rename a column to something that implies more certainty than the
  metric carries — keep "listings", "listed", and "proxy" wording as-is.
- Do not use `ProgressColumn` for the priority score. It reads as a completion
  bar and invites the "this is a validated probability" misreading the project
  explicitly disclaims.

- [ ] **Step 2: Run the smoke tests**

Run: `.venv/bin/python -m pytest tests/test_dashboard_smoke.py -q`
Expected: PASS — 11 pages execute. A mistyped column name raises at render
time, so a failure here means a `column_config` key does not match a real
column.

- [ ] **Step 3: Run the full suite and lint**

Run: `.venv/bin/python -m pytest tests/ -q && make lint`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add dashboard/pages
git commit -m "style(dashboard): type dataframe columns across all table pages"
```

---

### Task 6: Browser verification and residual CSS

Automated tests confirm pages execute; they cannot confirm pages look right.
This task is the visual gate.

**Files:**
- Conditional create: `dashboard/components/theme.py`
- Conditional modify: `dashboard/components/guardrails.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: if created, `components.theme.inject_css() -> None`, called once
  from `page_setup()` in `guardrails.py`.

- [ ] **Step 1: Launch and inspect every page**

Run: `make dashboard`

Walk all 11 pages and check each against this list:
- KPI cards read as cards, not floating numbers
- charts use the themed palette (no stray Plotly default blue/red)
- the choropleth and OMOP bar use the blue sequential ramp
- the signal-band scatter reads low → elevated as light → dark blue
- tables have styled headers and typed columns
- the disclaimer banner is present but not visually dominant
- no clipped text, overlapping labels, or horizontal overflow

Then switch to dark mode (Streamlit menu → Settings → Theme → Dark) and repeat.
The chart palette is global, so confirm the categorical colors still separate
against the dark surface.

- [ ] **Step 2: Record the gaps**

Write down only gaps that config provably cannot close. The known candidate is
`.block-container` top padding, which Streamlit leaves large and which no theme
key exposes.

**If there are no gaps, skip to Step 5.** Do not create `theme.py`
speculatively — an empty CSS module is worse than none.

- [ ] **Step 3: Add the residual CSS**

Only if Step 2 found gaps. Create `dashboard/components/theme.py`:

```python
"""Residual CSS for the few things Streamlit's theme config cannot reach.

Every rule here must correspond to a gap observed in the browser after the
native theme was applied. These selectors target Streamlit internals and can
break on upgrade, so keep this file small and prefer config whenever config
can do the job.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
  /* Streamlit reserves a large top gap above the first element. */
  .block-container { padding-top: 2.5rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
```

Then call it from `page_setup()` in `dashboard/components/guardrails.py`,
immediately after `st.set_page_config(...)` and before `st.title(...)`:

```python
from components.theme import inject_css
```

```python
def page_setup(title: str, icon: str = ":material/monitor_heart:") -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    inject_css()
    st.title(title)
    st.info(DISCLAIMER)
```

- [ ] **Step 4: Re-verify in the browser**

Run: `make dashboard`
Expected: the recorded gaps are closed and nothing else regressed.

- [ ] **Step 5: Run the full suite and lint**

Run: `.venv/bin/python -m pytest tests/ -q && make lint`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/components
git commit -m "style(dashboard): close residual layout gaps config cannot reach"
```

If Step 2 found no gaps, skip the commit and note in the task handoff that the
native theme was sufficient.

---

### Task 7: Update documentation

**Files:**
- Modify: `docs/dashboard_spec.md`
- Modify: `PROJECT_DOCUMENTATION.md` (§11 Streamlit dashboard)

**Interfaces:**
- Consumes: the final structure from Tasks 1–6.
- Produces: documentation only.

- [ ] **Step 1: Update the dashboard spec**

In `docs/dashboard_spec.md`:
- Add `palette.py` to the shared-components table: "ordinal signal-band ramp and
  semantic color lookup; the only place besides config.toml where color lives".
- Add `theme.py` to that table **only if** Task 6 created it.
- Replace the flat page list with the four navigation sections and note that
  `app.py` is now a router and Overview lives at `pages/0_Overview.py`.
- Add a "Theming" section recording: the theme lives in `.streamlit/config.toml`;
  the categorical palette was validated against both chart surfaces; chart
  colors are global in Streamlit so one palette serves both modes.
- Fix the stale smoke-coverage line — it says "all 8 scripts"; it is now 11.

- [ ] **Step 2: Update the project documentation**

In `PROJECT_DOCUMENTATION.md` §11, update the page inventory and navigation
structure to match. Leave the guardrail and methodology sections untouched —
this pass changed no metric.

- [ ] **Step 3: Verify the docs match reality**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: green. Then re-read both documents against the actual
`dashboard/` tree and confirm every page named exists and every page that
exists is named.

- [ ] **Step 4: Commit**

```bash
git add docs/dashboard_spec.md PROJECT_DOCUMENTATION.md
git commit -m "docs: update dashboard spec for theming and grouped navigation"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| 4.1 Theme config | Task 1 |
| 4.2 Chart call-site cleanup | Task 2 |
| 4.3 Navigation | Task 3 |
| 4.4 Per-page polish (KPI, rhythm) | Task 4 |
| 4.4 Per-page polish (column_config) | Task 5 |
| 4.5 Residual CSS | Task 6 |
| 6 Testing — all 11 pages | Task 3 Step 1 |
| 6 Testing — nav registration | Task 3 Step 1 |
| 6 Testing — guardrail contract preserved | Task 3 Step 1 |
| 6 Manual browser verification, both modes | Task 6 Step 1 |
| 7 Documentation | Task 7 |

No spec requirement is unassigned.

**Type consistency:** `SIGNAL_BAND_SCALE` and `SIGNAL_BAND_ORDER` are defined in
Task 2 Step 3 and consumed in Task 2 Step 4 under those exact names.
`semantic(role)` is defined and consumed likewise. `inject_css()` is defined and
called in Task 6 Step 3 under one name.

**Known deferrals (deliberate, not gaps):**
- `5_Sponsor_Landscape.py` colors by `sponsor_class`, which has **8** distinct
  values — exactly the categorical cap, with four of them semantically
  "other-ish" (`OTHER`, `UNKNOWN`, `OTHER_GOV`, `INDIV`). Folding them would
  improve legibility, but that changes what the chart reports, which this
  presentation-only pass excludes. Raise it in sub-project 3.
- `priority_band` currently holds only `review` and `watch` in the built
  warehouse; the documented third band `priority_review` does not appear. Not a
  UI issue — noted for sub-project 2.
