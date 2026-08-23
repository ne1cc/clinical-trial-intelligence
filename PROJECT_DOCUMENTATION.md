# Clinical Trial Access & Recruitment Competition Intelligence — Full Project Documentation

> **Planning signal only.** Every figure in this document is derived from public
> ClinicalTrials.gov registry listings. Outputs are *potential competition signals* for
> feasibility review — **not** recruitment forecasts, patient availability estimates,
> site-capacity measurements, or trial-outcome judgments. No contact or investigator
> information is collected or shown anywhere in this project.

Documentation snapshot: built and verified against the live warehouse of **2026-07-24**.

---

## Table of contents

1. [Project at a glance](#1-project-at-a-glance)
2. [The problem and the decision supported](#2-the-problem-and-the-decision-supported)
3. [System architecture](#3-system-architecture)
4. [Repository layout](#4-repository-layout)
5. [Data flow through the medallion layers](#5-data-flow-through-the-medallion-layers)
6. [Ingestion design (bronze)](#6-ingestion-design-bronze)
7. [Normalization design (silver)](#7-normalization-design-silver)
8. [Warehouse design (gold — dbt on DuckDB)](#8-warehouse-design-gold--dbt-on-duckdb)
9. [Dimensional data model](#9-dimensional-data-model)
10. [The feasibility priority score](#10-the-feasibility-priority-score)
11. [Streamlit dashboard](#11-streamlit-dashboard)
12. [Data quality framework](#12-data-quality-framework)
13. [Clinical interpretation guardrails](#13-clinical-interpretation-guardrails)
14. [Testing and verification](#14-testing-and-verification)
15. [Runbook — commands and operations](#15-runbook--commands-and-operations)
16. [Configuration reference](#16-configuration-reference)
17. [Known limitations](#17-known-limitations)
18. [Roadmap](#18-roadmap)
19. [Documentation index](#19-documentation-index)
20. [Glossary](#20-glossary)

---

## 1. Project at a glance

| Property | Value |
|---|---|
| Domain | Clinical-operations site-feasibility intelligence |
| Therapeutic area | Alzheimer's disease and related dementias (config-driven) |
| Geography | United States (raw data keeps all countries; marts are U.S.-only) |
| Source | [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api) (public, no key) |
| Stack | Python 3.11+ · uv · DuckDB · dbt · Streamlit · Plotly · pytest · ruff |
| Architecture | Local-first medallion: bronze JSON → silver Parquet → gold dbt marts |
| Automated tests | **73 dbt data tests** + **117 pytest tests** — all green |
| dbt resources | 30 models (8 staging views, 7 intermediate views, 15 mart tables) + 3 seeds |

**Live warehouse figures (single snapshot, 2026-07-24):**

| Measure | Value |
|---|---|
| Versioned trial records (`dim_trial`) | 2,592 |
| Currently recruiting | 419 |
| Not yet recruiting | 157 |
| Active, not recruiting | 139 |
| Completed | 1,877 |
| U.S. states/territories with listed sites | 50 |
| Distinct listed facilities (best-effort normalized) | 6,241 |
| Facilities listed on >1 recruiting trial | 301 |
| Trial × facility × snapshot rows | 12,244 |
| Lead sponsors | 1,743 |
| Distinct condition terms | 1,173 |
| Ranked condition × state × phase segments | 449 |
| Segments in `review`/`priority_review` bands | 75 |

Trial status mix in the current snapshot:

```mermaid
pie showData title Trials by current overall status (n=2,592)
    "COMPLETED" : 1877
    "RECRUITING" : 419
    "NOT_YET_RECRUITING" : 157
    "ACTIVE_NOT_RECRUITING" : 139
```

Phase mix (registry-reported; `NOT_APPLICABLE` dominates because many dementia
studies are behavioral/device interventions):

```mermaid
pie showData title Trials by normalized phase (n=2,592)
    "NOT_APPLICABLE" : 1203
    "PHASE2" : 452
    "PHASE1" : 416
    "PHASE3" : 225
    "PHASE4" : 108
    "PHASE1/PHASE2" : 83
    "EARLY_PHASE1" : 55
    "PHASE2/PHASE3" : 50
```

---

## 2. The problem and the decision supported

**Stakeholder:** Director of Clinical Operations / Head of Site Feasibility at a
sponsor or CRO.

**Question:** *"Which condition–geography–phase combinations should receive a
feasibility review before we invest in activating or expanding clinical trial sites?"*

Site activation is expensive and slow. Before committing startup resources, a
feasibility team wants to know where the public registry already shows:

- high **competing-study density** (many recruiting trials in the same segment),
- recent **trial growth** (new studies entering the segment),
- concentrated **sponsor activity** (a few sponsors dominating listings),
- repeated **site participation** (the same facilities listed across many trials),
- and how much **confidence** the underlying records deserve.

This project turns those public signals into a transparent, ranked
**Feasibility Review Priority Queue** — a to-do list for *human* feasibility review,
never an automated verdict.

```mermaid
flowchart LR
    A[Public registry<br/>listings] --> B[Transparent<br/>weighted signals]
    B --> C[Ranked priority queue<br/>449 segments]
    C --> D{{Human feasibility<br/>review + outreach}}
    D --> E[Site activation<br/>decision]
    style D stroke-dasharray: 5 5
```

The dashed step is the point: the pipeline **stops** at prioritization. Decisions
require qualified clinical-operations judgment and primary feasibility outreach.

---

## 3. System architecture

```mermaid
flowchart TB
    subgraph SRC["Source (public)"]
        CTG["ClinicalTrials.gov API v2<br/>GET /api/v2/studies<br/>pageSize + pageToken pagination"]
    end

    subgraph BRONZE["Bronze — immutable raw"]
        RAW["Raw JSON pages<br/>data/bronze/api_responses/run_id=&lt;id&gt;/page=NNNNN.json"]
        MAN["Ingestion manifests<br/>data/bronze/manifests/manifest_&lt;run_id&gt;.json"]
        BASE["Schema baseline<br/>_schema_baseline.json (125 field paths)"]
    end

    subgraph SILVER["Silver — normalized entities"]
        PQ["7 Parquet entity sets per run<br/>trials · locations · sponsors · conditions<br/>interventions · outcomes · statuses"]
        QUAR["Quarantine<br/>rejected records + reason codes"]
    end

    subgraph GOLD["Gold — dimensional warehouse"]
        DUCK[("DuckDB<br/>data/warehouse/clinical_trials.duckdb")]
        DBT["dbt: 8 staging + 7 intermediate<br/>+ 15 marts + 3 seeds + 73 tests"]
    end

    subgraph DELIVERY["Delivery"]
        APP["Streamlit dashboard<br/>11 pages, read-only"]
        DQ["Data-quality report<br/>reports/data_quality_report.md"]
        MEMO["Executive memo template"]
    end

    CTG -->|"httpx + retry/backoff<br/>run_id per snapshot"| RAW
    CTG --> MAN
    RAW -->|"flatten + normalize<br/>(pandas/pyarrow)"| PQ
    RAW -.->|invalid records| QUAR
    RAW -.->|field-path scan| BASE
    PQ -->|"read_parquet() sources"| DBT
    DBT --> DUCK
    DUCK --> APP
    DUCK --> DQ
    DUCK --> MEMO
```

**Key architectural decisions**

| Decision | Rationale |
|---|---|
| Bronze is immutable | Reproducibility: any downstream layer can be rebuilt byte-identically from raw pages |
| Snapshot-based history | The API serves only *current* records; history is constructed by retaining weekly snapshots keyed by `run_id` |
| DuckDB + dbt locally | Zero-cost, fully tested warehouse; SQL is portable to BigQuery/Snowflake later |
| All query parameters in YAML | `config/project_config.yml` — nothing is hard-coded in ingestion code |
| Dashboard is read-only | Connection opened `read_only=True`; the UI can never mutate the warehouse |
| Contacts deliberately excluded | `stg_trial_contacts` is an intentionally empty model (`where 1=0`) — a mechanical privacy guardrail |

---

## 4. Repository layout

```
clinical-trial-intelligence/
├── Makefile                      # reproducible entry points (make help)
├── pyproject.toml                # uv-managed dependencies + tool config
├── README.md                     # front-door documentation
├── PROJECT_DOCUMENTATION.md      # this file
├── .env.example                  # local overrides (no secrets needed)
│
├── config/
│   ├── project_config.yml        # API endpoint, query params, paths, HTTP policy
│   ├── condition_taxonomy.yml    # ADRD condition-group mapping rules
│   ├── geography_rules.yml       # US state normalization rules
│   ├── score_weights.yml         # feasibility score weights + bands
│   └── roi_assumptions.yml       # editable scenario-calculator assumptions
│
├── src/
│   ├── cli.py                    # python -m src.cli {ingest,transform,quality-report}
│   ├── config.py                 # typed pydantic config with .env overrides
│   ├── ingest/                   # ctg_client, pagination, retry_policy,
│   │                             # snapshot_manifest, validate_api_payload,
│   │                             # extract_studies (orchestrator)
│   ├── transform/                # flatten_studies, normalize_conditions,
│   │                             # normalize_locations, export_parquet,
│   │                             # build_silver_entities (orchestrator)
│   ├── quality/                  # profiling, schema_drift, reconciliation,
│   │                             # data_quality_report
│   ├── analysis/roi_scenarios.py # pure-arithmetic scenario calculator
│   └── utils/                    # dates, hashing, logging, paths, text
│
├── dbt_clinical_trials/
│   ├── dbt_project.yml           # schemas + feasibility band vars
│   ├── profiles.yml              # DuckDB target
│   ├── macros/                   # generate_surrogate_key, normalize_text,
│   │                             # parse_partial_date, safe_divide
│   ├── seeds/                    # status_mapping, phase_mapping,
│   │                             # feasibility_score_weights
│   ├── models/staging/           # 8 views over silver Parquet (+ sources, tests)
│   ├── models/intermediate/      # 7 views (status history, concentration, ...)
│   ├── models/marts/             # 5 dims, 2 facts, 2 bridges, 6 marts (+ tests)
│   ├── tests/                    # 6 singular SQL assertions
│   └── analyses/                 # 4 compiled-but-not-materialized analyses
│
├── dashboard/
│   ├── app.py                    # Overview page
│   ├── components/               # data (cached queries), guardrails, filters
│   └── pages/                    # 7 numbered pages (queue → trial explorer)
│
├── tests/                        # 117 pytest tests (unit + dashboard smoke)
├── docs/                         # 10 focused documents (see §19)
├── data/                         # git-ignored: bronze/ silver/ warehouse/ quarantine/
└── reports/                      # generated data-quality report
```

---

## 5. Data flow through the medallion layers

```mermaid
flowchart LR
    subgraph B["Bronze (JSON, immutable)"]
        direction TB
        b1["page=00000.json … page=00025.json<br/>~100 studies per page"]
        b2["manifest_&lt;run_id&gt;.json<br/>pages, counts, hashes, status"]
    end
    subgraph S["Silver (Parquet, per run)"]
        direction TB
        s1["trials/run_id=&lt;id&gt;.parquet"]
        s2["trial_locations/…"]
        s3["trial_sponsors/…"]
        s4["trial_conditions/…"]
        s5["trial_interventions/…"]
        s6["trial_outcomes/…"]
        s7["trial_statuses/…"]
    end
    subgraph G["Gold (DuckDB tables/views)"]
        direction TB
        g1["main_staging (8 views)"]
        g2["main_intermediate (7 views)"]
        g3["main_marts (15 tables)"]
        g4["main_seeds (3 mapping tables)"]
    end
    B -->|"make transform<br/>(flatten, normalize, quarantine)"| S
    S -->|"make dbt-run<br/>(read_parquet sources)"| G
```

Grain contract at every layer:

| Layer | Object | Grain |
|---|---|---|
| Bronze | JSON page | API page × ingestion run |
| Silver | `trials` | NCT ID × ingestion run |
| Silver | `trial_locations` | NCT ID × facility × city × state × run |
| Gold | `dim_trial` | NCT ID (current record) |
| Gold | `fct_trial_snapshot` | NCT ID × snapshot date |
| Gold | `fct_trial_site` | NCT ID × facility × city × state × snapshot date |
| Gold | `mart_feasibility_priority_queue` | condition group × state × phase × latest snapshot |

---

## 6. Ingestion design (bronze)

One ingestion run = one dated snapshot of the full query result, stored verbatim.

```mermaid
sequenceDiagram
    participant U as make ingest
    participant O as extract_studies
    participant C as ctg_client (httpx)
    participant A as ClinicalTrials.gov API v2
    participant D as data/bronze/

    U->>O: run_ingestion(condition, full_refresh, max_pages)
    O->>O: incremental check — recent completed run<br/>for same query hash? reuse & exit
    O->>O: mint run_id (UTC timestamp + query hash)
    loop until no nextPageToken
        O->>C: GET /studies?query.cond=…&pageSize=100&pageToken=…
        C->>A: request (timeout 30s)
        A-->>C: JSON page (+ totalCount on page 1)
        Note over C: on 429/5xx: exponential backoff,<br/>max 5 retries
        C-->>O: validated payload
        O->>D: write page=NNNNN.json (immutable)
    end
    O->>D: write manifest_&lt;run_id&gt;.json<br/>(pages, study count, totalCount,<br/>per-page hashes, status=success)
    O-->>U: exit 0
```

Properties worth noting:

- **Idempotent by default** — `incremental` mode refuses to silently re-download a
  query completed within the reuse window (24 h); `make full-refresh` overrides.
- **Honest partials** — a run capped by `--max-pages` or interrupted mid-way is
  marked `partial`/`failed` in its manifest and **excluded from analytics**.
- **Verifiable** — the manifest records per-page SHA-256 hashes and the API's
  `totalCount`, later reconciled against silver and gold row counts (§12).
- Last full pull: **26 pages, 2,592 studies**, matching the API `totalCount` exactly.

## 7. Normalization design (silver)

`make transform` flattens each bronze run into seven typed Parquet entity sets.

| Entity | Contents | Normalization applied |
|---|---|---|
| `trials` | One row per study: status, phase, dates, enrollment, sponsor | partial-date parsing (`2026`, `2026-07`), phase mapping, text cleanup |
| `trial_locations` | Listed facilities with city/state/zip/status | state → USPS 2-letter code, facility/city casefold+trim (best-effort) |
| `trial_sponsors` | Lead sponsor + collaborators with class | role normalized to `lead_sponsor` / `collaborator` |
| `trial_conditions` | Registry condition terms | mapped to ADRD condition groups via `config/condition_taxonomy.yml`, with confidence flag |
| `trial_interventions` | Intervention name + type | text normalization |
| `trial_outcomes` | Primary/secondary outcome measures | text normalization |
| `trial_statuses` | Status + record dates per snapshot | feeds status-history construction |

Records that fail structural validation (missing NCT ID, unparseable payload) go to
`data/quarantine/` with machine-readable **reason codes** — never silently dropped.
Every silver row carries `ingestion_run_id` and `source_json_hash` lineage columns.

---

## 8. Warehouse design (gold — dbt on DuckDB)

Simplified dbt DAG (arrows flow downstream):

```mermaid
flowchart LR
    subgraph ST["Staging (views over Parquet)"]
        st1[stg_trials]
        st2[stg_trial_locations]
        st3[stg_trial_sponsors]
        st4[stg_trial_conditions]
        st5[stg_trial_snapshots]
        st6["stg_trial_contacts<br/>(deliberately empty)"]
    end
    subgraph IN["Intermediate"]
        i1[int_trial_status_history]
        i2[int_current_trial_status]
        i3[int_geography_normalized]
        i4[int_trial_site_activity]
        i5[int_trial_condition_mapping]
        i6[int_sponsor_concentration]
        i7[int_condition_geography_activity]
    end
    subgraph MA["Marts"]
        d1[dim_trial]
        d2[dim_geography]
        d3[dim_sponsor]
        d4[dim_condition]
        d5[dim_date]
        f1[fct_trial_snapshot]
        f2[fct_trial_site]
        br1[bridge_trial_condition]
        br2[bridge_trial_sponsor]
        m1[mart_trial_activity]
        m2[mart_recruiting_competition]
        m3[mart_site_overlap]
        m4[mart_condition_geography_trends]
        m5[mart_data_reliability]
        m6[[mart_feasibility_priority_queue]]
    end
    st1 --> i1 --> i2
    st1 --> i2
    st2 --> i3 --> i4
    st4 --> i5
    st3 --> i6
    i5 --> i7
    i3 --> i7
    i2 --> d1
    st1 --> d1
    i3 --> d2
    st3 --> d3
    i5 --> d4
    i1 --> f1
    i4 --> f2
    i2 --> br1
    i5 --> br1
    i2 --> br2
    st3 --> br2
    i7 --> m1
    i7 --> m2
    i6 --> m2
    i4 --> m3
    i7 --> m4
    st5 --> m5
    m2 --> m6
    m3 --> m6
    m5 --> m6
    f1 --> m6
    style m6 stroke-width:3px
```

Seeds (version-controlled mapping tables): `status_mapping` (status → is_active /
is_recruiting flags), `phase_mapping` (registry phase → order), and
`feasibility_score_weights` (the score's weight vector — see §10).

Four reusable macros: `generate_surrogate_key` (MD5 of concatenated inputs),
`normalize_text`, `parse_partial_date`, `safe_divide` (null-safe denominators).

Four analyses (compiled, not materialized) provide ready-made review queries:
top priority segments, sponsor landscape, site-overlap hotspots, reliability trend.

---

## 9. Dimensional data model

```mermaid
erDiagram
    dim_trial ||--o{ fct_trial_snapshot : "nct_id"
    dim_trial ||--o{ fct_trial_site : "nct_id"
    dim_trial ||--o{ bridge_trial_condition : "trial_key"
    dim_trial ||--o{ bridge_trial_sponsor : "trial_key"
    dim_condition ||--o{ bridge_trial_condition : "condition_key"
    dim_sponsor ||--o{ bridge_trial_sponsor : "sponsor_key"
    dim_geography ||--o{ fct_trial_site : "state_code"
    dim_date ||--o{ fct_trial_snapshot : "snapshot_date"
    fct_trial_snapshot }o--|| mart_feasibility_priority_queue : "aggregated into"

    dim_trial {
        string trial_key PK
        string nct_id UK "NCT identifier"
        string registry_url "clinicaltrials.gov/study/NCTxxxxxxxx"
        string current_brief_title
        string current_overall_status
        string current_phase
        string current_lead_sponsor
        date study_first_post_date
        int enrollment_count "sponsor-reported plan"
        bool record_quality_flag
        date first_seen_snapshot_date
        date latest_seen_snapshot_date
    }
    fct_trial_snapshot {
        string snapshot_key PK
        string nct_id FK
        date snapshot_date
        string overall_status
        int condition_group_count
        int site_count_us
        string record_hash "source JSON SHA-256"
        bool current_record_flag
    }
    fct_trial_site {
        string trial_site_key PK
        string nct_id FK
        string facility_normalized "best-effort identity"
        string city_normalized
        string state_normalized
        date snapshot_date
        string location_status
    }
    mart_feasibility_priority_queue {
        string condition_group PK
        string state PK
        string phase PK
        date snapshot_date PK
        double feasibility_priority_score "0..1"
        string priority_band "watch|review|priority_review"
        int priority_rank
        bool growth_uses_registry_proxy_flag
        string priority_explanation "deterministic"
        string interpretation_note "always present"
    }
```

Bridges resolve the many-to-many relationships (a trial lists many conditions and
sponsors) and are scoped to each trial's **current** snapshot so dimension joins
never double-count history.

---

## 10. The feasibility priority score

The centerpiece mart ranks every **condition group × U.S. state × phase** segment.

**Formula** (all inputs min-max normalized to [0, 1] within the latest snapshot;
degenerate spreads where max = min score 0):

```
score = 0.35 · norm(recruiting_trial_count)        -- competing-study density
      + 0.20 · norm(recent_growth_input)           -- new studies entering
      + 0.20 · norm(sponsor_HHI)                   -- sponsor concentration
      + 0.15 · norm(site_overlap_share)            -- repeated facility listings
      + 0.10 · norm(data_confidence_input)         -- record completeness
```

```mermaid
pie showData title Score component weights (sum = 1.00)
    "Recruiting-trial density" : 0.35
    "Recent recruiting growth" : 0.20
    "Sponsor concentration (HHI)" : 0.20
    "Site overlap share" : 0.15
    "Data-confidence adjustment" : 0.10
```

Component definitions:

| Component | Definition | Honesty mechanism |
|---|---|---|
| Density | `COUNT(DISTINCT nct_id)` recruiting in the segment | never a per-capita claim (no population layer yet) |
| Growth | new recruiting trials in 90 days — **snapshot transitions** when ≥2 snapshots exist, else registry `study_first_post_date` proxy | `growth_uses_registry_proxy_flag` exposed per row; dashboard warns |
| Sponsor HHI | Σ(lead-sponsor share)² over segment listings | labeled listing concentration, not market share |
| Site overlap | share of segment trials listing a facility that appears on >1 recruiting trial | facility identity is best-effort name matching |
| Data confidence | 0.5 · record-quality-ok share + 0.5 · usable-location share | *raises* priority of well-documented segments; never punishes patients/sites |

**Banding** (thresholds are dbt vars, synchronized with `config/score_weights.yml`
and the seed CSV — a pytest test fails if the three ever diverge):

```mermaid
flowchart LR
    A["score ∈ [0, 0.45)"] --> W[watch]
    B["score ∈ [0.45, 0.70)"] --> R[review]
    C["score ∈ [0.70, 1.00]"] --> P[priority_review]
    style P stroke-width:3px
```

Current live distribution: **449** segments → 374 `watch`, **75** `review`,
0 `priority_review` (expected on single-snapshot history: the growth component
still uses the registry proxy, and top-band evidence is intentionally hard to reach).

Every row also ships:

- `priority_explanation` — a deterministic, template-generated sentence naming the
  dominant components (no free-text generation);
- `interpretation_note` — the fixed sentence *"Potential competition signal from
  public registry listings. Not a recruitment forecast; requires human feasibility
  review."*

---

## 11. Streamlit dashboard

`make dashboard` → http://localhost:8501. Eleven pages, all read-only.

`app.py` is a router: it declares the sidebar sections with `st.navigation` and
runs the selected page. All page content lives in `dashboard/pages/`, including
the Overview.

```mermaid
flowchart TB
    APP["app.py — router<br/>st.navigation sections"]
    OV["0 · Overview<br/>KPIs + top-of-queue preview"]
    subgraph S1["Feasibility Signals"]
        P1["1 · Priority Queue<br/>ranked segments, score components"]
        P2["2 · Competition Landscape<br/>density vs. sponsor-HHI scatter"]
        P3["3 · Geography Trends<br/>US choropleth + monthly trend"]
        P5["5 · Sponsor Landscape<br/>top lead sponsors by listings"]
        P4["4 · Site Overlap<br/>multi-trial facilities table"]
    end
    subgraph S2["Clinical Data Explorer"]
        P7["7 · Trial Explorer<br/>per-trial records with links"]
        P8["8 · Eligibility Criteria<br/>criterion mix and complexity"]
        P9["9 · OMOP Explorer<br/>SNOMED / RxNorm concept mappings"]
    end
    subgraph S3["Forecasting & Data Trust"]
        P10["10 · Enrollment Forecast<br/>stage mix + velocity signals"]
        P6["6 · Data Reliability<br/>run health + scenario explorer"]
    end
    APP --> OV
    APP --> S1
    APP --> S2
    APP --> S3
```

The visual identity lives in `.streamlit/config.toml` — palette, typography,
surfaces, and chart colors. See `docs/dashboard_spec.md` § Theming for why the
categorical palette had to validate against both the light and dark chart
surfaces, and why the competition signal band uses an ordinal blue ramp rather
than a red scale.

| Guardrail | Enforcement |
|---|---|
| Disclaimer banner on every page | shared `page_setup()`; a pytest test greps every page source for the call |
| Growth-proxy warning | shown whenever any displayed row has `growth_uses_registry_proxy_flag` |
| Read-only warehouse | `duckdb.connect(..., read_only=True)` behind `st.cache_resource` |
| Query caching | `st.cache_data(ttl=600)` |
| Scenario explorer never writes | sliders adjust session-only copies of `config/roi_assumptions.yml` |
| Trial links | `registry_url` column rendered with `st.column_config.LinkColumn` — opens the authoritative public record |
| No hardcoded chart colors | `tests/test_theme.py` fails if any page contains a hex literal; color lives in config or `components/palette.py` |
| Every page reachable | `test_every_page_is_registered_in_navigation` fails if a page file is missing from `app.py` |
| Score shown as an index, not a bar | priority score and HHI use decimal `NumberColumn`, never `ProgressColumn`, which would imply a validated probability |

The page-6 **scenario explorer** replaces fake ROI claims: users plug in *their own*
cost assumptions (review cost, deprioritized-share, activation cost, influence share)
under conservative/base/optimistic multipliers; the arithmetic is pure
multiplication, and the disclaimer renders above every result.

---

## 12. Data quality framework

Quality gates run at every layer; failures block promotion of the affected data.

```mermaid
flowchart TB
    subgraph L1["Gate 1 — Ingestion"]
        a1["HTTP retry/backoff on 429/5xx"]
        a2["Payload structural validation"]
        a3["Manifest: page count, study count,<br/>totalCount, per-page SHA-256"]
    end
    subgraph L2["Gate 2 — Transform"]
        b1["Quarantine + reason codes"]
        b2["Schema-drift scan vs. baseline<br/>(125 field paths, explicit update flag)"]
        b3["Per-run profiling stats"]
    end
    subgraph L3["Gate 3 — Warehouse (dbt, 73 tests)"]
        c1["Schema tests: unique, not_null,<br/>accepted_values, relationships"]
        c2["6 singular assertions: one current<br/>record/trial, valid dates & states,<br/>score ∈ [0,1], site integrity,<br/>snapshot completeness"]
    end
    subgraph L4["Gate 4 — Cross-layer reconciliation"]
        d1["bronze count = silver count per run"]
        d2["NCT uniqueness within run"]
        d3["dim_trial = latest silver distinct NCTs"]
        d4["current_record_flag ≤ dim_trial"]
    end
    L1 --> L2 --> L3 --> L4 --> R["reports/data_quality_report.md<br/>(make quality-report)"]
```

**Severity philosophy:** `error` = structural invariants this pipeline controls
(grains, keys, reconciliation); `warn` = registry messiness the pipeline must
tolerate and report (odd dates, missing fields) — real-world messiness is surfaced,
not hidden and not fatal.

Latest live reconciliation: **4/4 checks pass** — API `totalCount` 2,592 → manifest
2,592 → silver 2,592 → `dim_trial` 2,592.

---

## 13. Clinical interpretation guardrails

The project's language rules are mechanical, not aspirational:

| Prohibited claim | Why | Mechanical control |
|---|---|---|
| "Site X is failing to recruit" | registry status ≠ operational truth | no site-performance metric exists in any mart |
| "Patients are available in state Y" | no participant-level data exists | density metrics labeled *listing* counts |
| "Sponsor Z is underperforming" | listings ≠ performance | sponsor mart shows listing counts only |
| Any contact/investigator info | privacy by design | `stg_trial_contacts` is empty by construction; smoke test asserts no such columns render |
| Predicted enrollment / ROI | would be invented | score is a *ranking*, scenario calculator uses only user-supplied assumptions |

Every scored row carries `interpretation_note`; every dashboard page carries the
banner; every document (including this one) opens with the planning-signal rule.

## 14. Testing and verification

| Suite | Count | Scope |
|---|---|---|
| dbt data tests | **73** | grains, keys, referential integrity, accepted values, score bounds, current-record uniqueness, state validity, date sanity |
| pytest | **47** | HTTP client/retry, pagination, manifests, normalization, metric math (weights sync, min-max edge cases, HHI fixtures), ROI arithmetic + disclaimer, dashboard smoke (all 8 pages via Streamlit `AppTest`) |
| ruff | clean | lint + format, line length 100 |

Last full verification (2026-07-24): `dbt build` **105/105 PASS** (3 seeds,
15 tables, 15 views, 72 tests at that run; now 73 after the `registry_url` test),
`pytest` **47/47**, dashboard HTTP 200 with all pages exercised.

Operational note: the dashboard smoke tests and a live dashboard server cannot share
the DuckDB file — stop the server before running `make test`.

---

## 15. Runbook — commands and operations

### First-time setup

```bash
git clone <repo-url> clinical-trial-intelligence
cd clinical-trial-intelligence
make setup            # uv sync, .env, data/ directories
```

### Full pipeline

```bash
make pipeline         # ingest → transform → dbt-run → dbt-test → quality-report
make dashboard        # http://localhost:8501
```

### Individual stages

| Command | What it does |
|---|---|
| `make ingest` | incremental bronze snapshot (skips if a recent complete run exists) |
| `make full-refresh` | force a complete re-pull as a new run |
| `make transform` | bronze → silver Parquet (+ profiling, quarantine, drift scan) |
| `make dbt-deps` / `dbt-run` / `dbt-test` / `dbt-docs` | warehouse build, tests, docs |
| `make quality-report` | write `reports/data_quality_report.md` |
| `make test` / `lint` / `format` | pytest / ruff check / ruff format |
| `make clean` | remove caches and build artifacts (**never** touches `data/`) |

### Weekly snapshot cadence

```mermaid
flowchart LR
    CRON["cron / systemd timer / CI<br/>(weekly)"] --> I[make ingest]
    I --> T[make transform]
    T --> R[make dbt-run + dbt-test]
    R --> Q[make quality-report]
    Q --> H{{"history accrues:<br/>transition metrics activate<br/>at snapshot #2"}}
```

Each additional snapshot deepens `fct_trial_snapshot`; at two or more snapshots the
growth component automatically switches from the registry proxy to true
status-transition counts (and `growth_uses_registry_proxy_flag` flips off).

## 16. Configuration reference

| File | Controls |
|---|---|
| `config/project_config.yml` | API base URL, endpoint, `query.cond`, status/type filters, page size, HTTP timeout/retry policy, all data paths, incremental reuse window |
| `config/condition_taxonomy.yml` | mapping of registry condition strings → ADRD condition groups, with confidence rules |
| `config/geography_rules.yml` | state-name → USPS code normalization |
| `config/score_weights.yml` | score weights, normalization method, band thresholds (mirrored in seed + dbt vars; sync enforced by pytest) |
| `config/roi_assumptions.yml` | scenario-calculator assumptions and multipliers (with embedded disclaimer) |
| `.env` | optional local overrides (`CTI_CONFIG_PATH`, `CTI_HTTP_TIMEOUT_SECONDS`, `CTI_MAX_RETRIES`) — no secrets required |
| `dbt_clinical_trials/dbt_project.yml` | schema routing, seed types, feasibility band vars |

## 17. Known limitations

1. **Registry lag** — statuses can trail real-world operations by weeks; listing ≠
   verified activity.
2. **Single-snapshot history (currently)** — transition-based metrics are honestly
   zero/proxy-flagged until weekly snapshots accumulate.
3. **Facility identity is fuzzy** — names are not stable identifiers; overlap
   metrics are best-effort normalized-name matches.
4. **No population adjustment** — density is absolute, not per-capita, until an ACS
   layer is added.
5. **Condition mapping is rule-based** — taxonomy confidence is tracked and
   low-confidence share is reported, but mapping is not clinically adjudicated.
6. **Portfolio demonstration** — real feasibility decisions require qualified
   clinical-operations review and primary outreach.

## 18. Roadmap

```mermaid
flowchart LR
    M1["MVP (done)<br/>CT.gov pipeline,<br/>marts, dashboard"] --> M2["ACS population layer<br/>per-capita density"]
    M2 --> M3["CDC/ATSDR SVI<br/>county access-barrier context"]
    M3 --> M4["Oncology module<br/>NCI CTS API"]
    M4 --> M5["Cloud warehouse portability<br/>+ orchestration (Dagster/Airflow)"]
```

## 19. Documentation index

| Document | Purpose |
|---|---|
| [`README.md`](README.md) | front door: setup, scope, methodology summary |
| [`docs/architecture.md`](docs/architecture.md) | layer-by-layer architecture detail |
| [`docs/source_documentation.md`](docs/source_documentation.md) | API v2 endpoint, parameters, pagination, snapshot rationale |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | every object and column, silver + gold |
| [`docs/metric_definitions.md`](docs/metric_definitions.md) | formal definition + denominator + guardrail per metric |
| [`docs/data_quality_framework.md`](docs/data_quality_framework.md) | gates, tests, severity philosophy |
| [`docs/clinical_interpretation_guardrails.md`](docs/clinical_interpretation_guardrails.md) | prohibited claims and required framing |
| [`docs/assumptions_and_limitations.md`](docs/assumptions_and_limitations.md) | expanded limitations |
| [`docs/dashboard_spec.md`](docs/dashboard_spec.md) | page-by-page dashboard specification |
| [`docs/executive_memo_template.md`](docs/executive_memo_template.md) | fill-in memo with live example figures |
| [`docs/development_log.md`](docs/development_log.md) | complete step-by-step build record, phases 1–7 |

## 20. Glossary

| Term | Meaning here |
|---|---|
| **NCT ID** | ClinicalTrials.gov registry identifier (e.g. `NCT07721467`) — the only stable trial key |
| **Snapshot** | one complete ingestion run's view of all matching current records |
| **Segment** | a condition group × U.S. state × phase combination |
| **Run ID** | unique identifier minted per ingestion run; partitions bronze and silver |
| **Manifest** | per-run JSON recording pages, counts, hashes, and completion status |
| **HHI** | Herfindahl–Hirschman Index of lead-sponsor listing shares within a segment |
| **Proxy growth** | growth measured from registry first-post dates when snapshot history is insufficient (always flagged) |
| **Quarantine** | storage for records rejected at transform time, with reason codes |
| **Priority band** | `watch` / `review` / `priority_review` — a queueing label, not a verdict |

---

**Disclaimer:** Source: ClinicalTrials.gov public registry data (NLM). This project
is an analytical portfolio demonstration. All metrics are feasibility-review
planning signals — not enrollment forecasts, not clinical decision support, and not
judgments of any site, sponsor, or population. Validate with qualified
clinical-operations teams before any real-world use.
