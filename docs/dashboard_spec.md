# Dashboard Specification

Audience: Director of Clinical Operations / Head of Site Feasibility.
Stack: Streamlit multipage over read-only DuckDB (`make dashboard`).
`dashboard/app.py` is a **router**: it declares the sidebar sections via
`st.navigation` and runs the selected page. Page content lives entirely in
`dashboard/pages/`, including the Overview (`pages/0_Overview.py`).
Every page renders the shared disclaimer banner via
`components/guardrails.page_setup()` (test-enforced) and a guarded footer.

## Shared components (`dashboard/components/`)
| Module | Responsibility |
|---|---|
| data.py | cached read-only warehouse access; `require_warehouse()` stops with build instructions if missing |
| guardrails.py | disclaimer banner, snapshot-proxy note, footer |
| filters.py | condition/state/phase sidebar multiselects with row-count caption |
| palette.py | the two chart encodings the global theme cannot express: the ordinal signal-band ramp and `semantic()` role lookup |

## Navigation

Pages are grouped into sidebar sections. Section order follows how a
feasibility review is sequenced, which is why it does not match filename
order — sponsor concentration is read before facility overlap.

| Section | Pages |
|---|---|
| *(top level)* | Overview |
| Feasibility Signals | Priority Queue, Competition Landscape, Geography Trends, Sponsor Landscape, Site Overlap |
| Clinical Data Explorer | Trial Explorer, Eligibility Criteria, OMOP Explorer |
| Forecasting & Data Trust | Enrollment Forecast, Data Reliability |

Adding a page file without registering it in `app.py` fails
`test_every_page_is_registered_in_navigation`, so a page cannot silently
ship without appearing in the sidebar.

## Pages

### Overview (`pages/0_Overview.py`)
KPIs (trials tracked, recruiting, states, facilities), snapshot count,
top-10 queue preview, "how to read this dashboard". Link to the full
queue.

### 1 · Priority Queue
Band KPIs (priority_review / review / watch), proxy warning when growth
uses the registry-date fallback, full ranked table (score, band,
components, deterministic explanation), horizontal stacked bar of
normalized *unweighted* components for the top 15, interpretation note.

### 2 · Competition Landscape
Latest-snapshot segments: density vs sponsor-HHI scatter (bubble = listed
sites, color = signal band with explicit "relative percentile cuts"
caption) + sortable segment table.

### 3 · Geography Trends
Condition-group selector → USA choropleth of recruiting listings by
state, top-states table, monthly trend line — or an honest notice showing
how many snapshot months exist when a series is not yet possible.

### 4 · Site Overlap
Multi-trial facility table (default filter on), states ranked by
multi-trial facilities, mandatory caption: best-effort matching, not
workload/performance.

### 5 · Sponsor Landscape
Top lead sponsors by recruiting listings (colored by registry sponsor
class), full table, "not market share" caption.

### 6 · Data Reliability & Assumptions
Run reliability table (success + partial runs shown; only success feeds
analytics), latest-run confidence metrics, known limitations, and the
**illustrative scenario explorer**: sliders adjust session-only copies of
`config/roi_assumptions.yml`; the disclaimer always renders above results
and the file is never written.

### 7 · Trial Explorer
Individual registry records with status/phase filters and free-text
search (title, sponsor, NCT ID); each row links to the authoritative
public record via `registry_url`
(`https://clinicaltrials.gov/study/<NCT_ID>`, a `dim_trial` column).
Caption states rows reflect this project's latest snapshot and that
listed enrollment is the sponsor-reported plan, not actual accrual.

### 8 · Eligibility Criteria
Portfolio-level eligibility complexity: criterion-type distribution split
by inclusion/exclusion (semantic green/red from the theme, not hardcoded),
and complexity by phase.

### 9 · OMOP Explorer
Condition concept mappings (SNOMED CT) and intervention concept mappings
(RxNorm / SNOMED) from the curated ADRD-relevant seed, with mapped/unmapped
counts. Unmapped entries reflect novel or non-standard interventions.

### 10 · Enrollment Forecast
Trial-lifecycle and enrollment-velocity analytics: stage mix by condition
group and velocity signals. Rates are planning proxies derived from public
registry date fields and target enrollment — not measured accrual.

## Theming

The visual identity lives in `.streamlit/config.toml`, not in page code.

- Chart palettes are **global** in Streamlit — there is no
  `theme.light.chartCategoricalColors` / `theme.dark.…` variant — so one
  palette serves both surfaces. The categorical set was validated to pass
  every check against **both** the light (`#fcfcfb`) and dark (`#1a1a19`)
  chart surfaces.
- The competition signal band uses a single-hue **ordinal** blue ramp
  rather than a red "danger" scale. The bands are relative percentile cuts,
  and `clinical_interpretation_guardrails.md` forbids presenting them as
  verdicts.
- Semantic colors (`greenColor` / `redColor`) *are* per-mode configurable and
  are read at runtime through `components.palette.semantic()`.
- `tests/test_theme.py` pins the validated palette and fails the build if any
  page hardcodes a hex value.
- Numeric formatting distinguishes 0..1 fractions (`format="percent"`) from
  values already scaled to 0..100 (`format="%.1f"`). HHI and the priority
  score stay decimal indices — never progress bars, which would imply a
  validated probability the project disclaims.

## Non-functional rules
- Warehouse opened `read_only=True`; the dashboard can never mutate data.
- Queries cached (`st.cache_data`, TTL 600s); connection cached per
  process.
- No contact/investigator data exists to display.
- Smoke coverage: `tests/test_dashboard_smoke.py` runs all 11 pages via
  Streamlit `AppTest` (auto-skips without a warehouse). Overview is
  exercised through the router rather than standalone, because its
  `st.page_link` resolves against the page graph `st.navigation` builds.
- `column_config` keys are checked against real dataframe columns. Streamlit
  silently ignores an unknown key — the column just renders untyped — so
  without this guard a typo would pass every other test.
