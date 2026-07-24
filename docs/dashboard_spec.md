# Dashboard Specification

Audience: Director of Clinical Operations / Head of Site Feasibility.
Stack: Streamlit multipage over read-only DuckDB (`make dashboard`).
Every page renders the shared disclaimer banner via
`components/guardrails.page_setup()` (test-enforced) and a guarded footer.

## Shared components (`dashboard/components/`)
| Module | Responsibility |
|---|---|
| data.py | cached read-only warehouse access; `require_warehouse()` stops with build instructions if missing |
| guardrails.py | disclaimer banner, snapshot-proxy note, footer |
| filters.py | condition/state/phase sidebar multiselects with row-count caption |

## Pages

### Overview (`app.py`)
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

## Non-functional rules
- Warehouse opened `read_only=True`; the dashboard can never mutate data.
- Queries cached (`st.cache_data`, TTL 600s); connection cached per
  process.
- No contact/investigator data exists to display.
- Smoke coverage: `tests/test_dashboard_smoke.py` runs all 8 scripts via
  Streamlit `AppTest` (auto-skips without a warehouse).
