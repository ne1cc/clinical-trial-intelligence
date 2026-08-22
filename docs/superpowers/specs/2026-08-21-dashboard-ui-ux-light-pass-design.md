# Dashboard UI/UX Light Pass — Design

Date: 2026-08-21
Status: approved in chat, pending spec review
Scope: sub-project 1 of 3 (UI/UX → scientific relevancy → new capabilities)

## 1. Goal

Give the Streamlit dashboard a deliberate visual identity and a navigable
information architecture, without changing any metric, model, or data
contract. Success means a clinical-operations reader can find the right page
quickly, and a portfolio reader does not perceive "default Streamlit app".

Two audiences, weighted equally:

- **Clin-ops stakeholder** — navigation must mirror how feasibility work is
  actually sequenced, and guardrail framing must stay prominent.
- **Portfolio reviewer** — the app must read as designed, not generated.

## 2. Current state

Verified 2026-08-21 against the working tree:

- Streamlit **1.59.1** installed (`pyproject.toml` floor is `>=1.36`).
- **No `.streamlit/config.toml`** — the app runs on stock Streamlit theming
  (default red-orange `#FF4B4B` primary, default fonts).
- **No custom CSS anywhere** — zero `unsafe_allow_html` style blocks.
- 10 pages in `dashboard/pages/`, flat and numbered `1_`–`10_`; `app.py` is
  itself the Overview page and carries content.
- 9 Plotly charts across 8 pages, each falling through to Plotly defaults
  independently. Two pages hardcode `color_continuous_scale="Blues"`
  (`3_Geography_Trends.py:32`, `9_OMOP_Explorer.py:33`); one hardcodes raw hex
  `#2ecc71`/`#e74c3c` (`8_Eligibility_Criteria.py:39`). There is no shared
  palette.
- Only `7_Trial_Explorer.py` uses `st.dataframe(column_config=...)`; the other
  table-bearing pages render untyped columns.
- Baseline test suite: **95 passed** (`.venv/bin/python -m pytest tests/ -q`).

## 3. Key technical finding (revises the approach)

The approach was originally chosen as "theme config + a custom CSS module",
on the assumption that native Streamlit theming could not style metric tiles,
borders, dataframes, or chart palettes. **That assumption was wrong for 1.59.**

Streamlit 1.59 natively exposes, via `.streamlit/config.toml`:

- `theme.chartCategoricalColors`, `chartSequentialColors`, `chartDivergingColors`
  — and `streamlit/elements/plotly_chart.py:516` documents these as applying to
  Plotly charts (Streamlit builds a Plotly template setting `colorway`).
- `theme.showWidgetBorder`, `showSidebarBorder`, `baseRadius`, `buttonRadius`,
  `borderColor`.
- `theme.dataframeHeaderBackgroundColor`, `dataframeBorderColor`.
- `theme.metricValueFontSize`, `metricValueFontWeight`.
- `theme.font`, `headingFont`, `headingFontSizes`, `headingFontWeights`,
  `baseFontSize`, `fontFaces`.
- Semantic colors: `greenColor`, `redColor`, `yellowColor`, `orangeColor`, etc.
- Scoped overrides: `[theme.sidebar]`, `[theme.light]`, `[theme.dark]`.

**Consequence:** custom CSS shrinks from the bulk of the work to a residual.
This is strictly better — the fragile part of the original plan (hand-written
rules against `data-testid` internals, which break on Streamlit upgrades) is
mostly unnecessary. The design below is therefore **config-first, CSS-residual**.

Streamlit also ships reference theme presets at
`streamlit/.agents/skills/developing-with-streamlit/assets/templates/themes/configs/`;
`financial-dashboard.toml` is the closest analogue and is used as a structural
reference (not copied — it is dark-mode and finance-semantic).

## 4. Design

### 4.1 Theme (`.streamlit/config.toml`) — new file

A light-base clinical palette, with a `[theme.dark]` override so both modes are
deliberate rather than accidental.

- **Base**: light. Clinical and enterprise tooling skews light, and light
  screenshots reproduce better in a portfolio context.
- **Primary**: a calm clinical blue, replacing Streamlit's default red-orange.
  Red must stay semantically free for risk/exclusion signals — a red primary
  actively fights this app's meaning.
- **Typography**: Inter for body and headings, with an explicit heading size and
  weight ramp so section hierarchy is visible. *Trade-off:* Streamlit's font
  syntax loads Inter from Google Fonts, i.e. a network dependency in an
  otherwise local-first project. It degrades to the system sans stack offline,
  which is acceptable; noted so the choice is not silent.
- **Chart palette**: one categorical set and one sequential ramp defined here,
  inheriting to all 9 Plotly charts with no per-page code. Colorblind-safe
  ordering and adequate contrast to be validated at implementation time using
  the `dataviz` skill's method.
- **Surfaces**: `showWidgetBorder`/`showSidebarBorder` on, modest `baseRadius`,
  explicit `borderColor`, and dataframe header/border colors so tables read as
  designed objects.

### 4.2 Chart call sites — remove local color overrides

So the theme actually inherits:

- Drop `color_continuous_scale="Blues"` (`3_Geography_Trends.py`,
  `9_OMOP_Explorer.py`) → `chartSequentialColors` applies.
- Replace hardcoded `#2ecc71`/`#e74c3c` (`8_Eligibility_Criteria.py`) with the
  theme's semantic green/red. **Nuance:** inclusion/exclusion is a *semantic*
  encoding, not an arbitrary categorical one, so it maps to `greenColor`/
  `redColor` deliberately rather than falling into the categorical rotation.

### 4.3 Navigation (`st.navigation`)

Replace flat numbered auto-discovery with explicit sections:

| Section | Pages |
|---|---|
| *(top level)* | Overview |
| Feasibility Signals | Priority Queue, Competition Landscape, Geography Trends, Sponsor Landscape, Site Overlap |
| Clinical Data Explorer | Trial Explorer, Eligibility Criteria, OMOP Explorer |
| Forecasting & Data Trust | Enrollment Forecast, Data Reliability |

Structural consequence: under `st.navigation`, `app.py` becomes a router, so
**Overview content moves to `dashboard/pages/0_Overview.py`** and `app.py`
retains only page registration.

Verified constraint: calling `st.set_page_config` inside a sub-page under
`st.navigation` does **not** raise in 1.59.1 (tested via `AppTest`). Therefore
`page_setup()` stays unchanged and the test-enforced guardrail banner contract
survives intact on every page.

Existing filenames and their numeric prefixes are **kept**. `st.navigation`
controls order and labels explicitly, so renaming 10 files would create churn
and break inbound doc links for no functional gain.

### 4.4 Per-page visual polish

Native primitives only; no new metrics, pages, or data:

- KPI rows wrapped in `st.container(border=True)` so headline numbers read as
  one card rather than loose floating metrics.
- One consistent vertical rhythm across all pages: filters → visualization →
  table → caption, with `st.divider()` used consistently rather than ad hoc.
- Extend `st.dataframe(column_config=...)` — currently only in Trial Explorer —
  to every table-bearing page, so numbers, dates, and links are typed and
  aligned instead of raw.

### 4.5 Residual CSS (`dashboard/components/theme.py`) — new file

Created **only** for what config provably cannot reach, injected once from
`page_setup()`. Expected to be a handful of rules; the known candidate is
`.block-container` top padding, which Streamlit leaves large and which no theme
key exposes.

Rule: every rule in this file must be justified by a gap observed in the browser
*after* the native theme is in place — not written speculatively. If the native
theme closes every gap, this file is not created at all.

## 5. Out of scope

Deferred to later sub-projects, explicitly not in this pass:

- New metrics, new pages, or new data sources (ACS per-capita, SVI, oncology).
- Third-party Streamlit component packages.
- A user-facing light/dark toggle (both modes are themed; mode selection stays
  Streamlit's own).
- Changes to dbt models, the priority score, or guardrail wording.

## 6. Testing and verification

- `tests/test_dashboard_smoke.py` currently lists only **8** of the 11 page
  scripts — pages 8, 9, and 10 are untested. Extend `PAGES` to cover every page,
  including the new `0_Overview.py`.
- `app.py` becomes a router and no longer calls `page_setup()`, so the
  "every page shows the disclaimer" assertion must target page scripts rather
  than the entrypoint. The guardrail contract itself does not weaken.
- Add a test asserting every file in `dashboard/pages/` is registered in
  `app.py`'s navigation, so a future page cannot silently fail to appear.
- Full suite must return to green (baseline: 95 passed).
- Manual browser verification of every page via `make dashboard`, in both light
  and dark mode, before the pass is called complete. Automated tests confirm the
  pages execute; they cannot confirm the pages look right.

## 7. Documentation to update

- `docs/dashboard_spec.md` — page inventory (says "8 scripts", lists 7 pages),
  navigation structure, and a new theming section.
- `PROJECT_DOCUMENTATION.md` §11 (Streamlit dashboard).
