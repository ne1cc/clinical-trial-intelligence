# Product Roadmap — Analytical Differentiation

## How to use this document

This is a pre-planning reference, not an implementation plan. It captures
the strategic case and candidate feature set for what to build next, now
that the platform itself (ingestion, warehouse, dbt marts, dashboard,
Fly.io deployment) is live and stable. Each roadmap item below still needs
its own pass through this project's normal process before code gets
written: brainstorm the specific feature, write a design spec to
`docs/superpowers/specs/`, then a task-by-task plan to
`docs/superpowers/plans/`. Treat the phases here as a prioritized backlog
to brainstorm from, one at a time — not a spec to implement wholesale.

---

Your dashboard has moved beyond a portfolio prototype: it is now a live,
containerized ClinicalTrials.gov intelligence product with a weekly
refresh loop, dbt quality gates, and seven decision-oriented dashboard
pages. The best next step is **not** to imitate Citeline, IQVIA, or H1's
proprietary data; it is to deepen the **free, explainable feasibility
workflow** that public registry data can genuinely support.

## TL;DR

- **Concept:** Position CTI as an open, auditable *trial feasibility and
  competitive-pressure workbench* built from ClinicalTrials.gov — not as a
  commercial site-performance or patient-access database.
- **Use case:** Let a clinical strategy analyst answer: "Where is
  recruitment competition rising, which studies are comparable, and where
  are the most defensible opportunities to investigate?"
- **Key takeaway:** The highest-value next features are **change
  intelligence, protocol comparability, explainable scores, data-confidence
  signals, and decision-ready exports** — all possible with the current
  free data foundation.

## Current Product Assessment

The repository (`ne1cc/cti-dashboard`) is publicly deployed. Its current
commit history shows the deployment pipeline, first-boot warehouse build,
weekly refresh process, and automatic Fly deployment on pushes to `main`
were just implemented. The app runs one always-on process because the
background refresh loop needs to remain active, persists the warehouse on
a mounted volume, and health-checks the Streamlit service.

The existing analytical foundation is already strong:

| Layer | Current implementation | Why it matters |
|---|---|---|
| Ingestion | ClinicalTrials.gov API ingestion using `requests`, after resolving an API edge-protection issue with `httpx` | Shows real-world source reliability troubleshooting and robust client design |
| Warehouse | DuckDB with Bronze → Silver → Gold/dbt structure | Gives reproducibility, fast local analytics, and transparent transformations |
| Quality | 73 dbt tests and a pytest suite in the latest pipeline run | Signals production-minded data quality and test discipline |
| History | Weekly snapshot history through `fct_trial_snapshot` | Enables time-series and change-detection features, far more valuable than static registry search |
| Intelligence marts | Trial activity, recruiting competition, site overlap, geography trends, data reliability, feasibility priority queue | Covers the baseline feasibility workflow |
| User experience | Priority Queue, Competition Landscape, Geography Trends, Site Overlap, Sponsor Landscape, Data Reliability, Trial Explorer | A coherent decision journey rather than disconnected charts |
| Deployment | Docker, Fly configuration, GitHub Actions auto-deploy, live demo | Makes the project interviewable and usable by others, not just locally runnable |

The repository also contains well-defined dimensions and facts — trials,
conditions, sponsors, geography, trial sites, and snapshots — plus a
config-driven feasibility score and a dedicated reliability mart. That is
the correct architecture for adding features without turning the
dashboard into unmaintainable Streamlit-only logic.

### What is already comparable

The current feature set maps most closely to the **early feasibility /
competitive-intelligence** parts of Citeline Trialtrove and H1 Site
Universe:

| Enterprise concept | Current free equivalent | Important limitation |
|---|---|---|
| Competitive trial landscape | `mart_recruiting_competition` and Competition Landscape | Registry data will not represent every commercial intelligence signal |
| Geographic trial activity | `mart_condition_geography_trends` and Geography Trends | Site location does not prove recruitment capacity or patient availability |
| Study/site overlap | `mart_site_overlap` and Site Overlap | Co-location signals competition, not verified site performance |
| Trial prioritization | `mart_feasibility_priority_queue` and Priority Queue | Ranking is an analytical hypothesis, not an operational recommendation |
| Sponsor landscape | `dim_sponsor`, bridge table, Sponsor Landscape | Sponsor normalization is difficult with registry-entered organization names |
| Data confidence | `mart_data_reliability` and Data Reliability | Reliability reflects registry completeness and timeliness, not scientific validity |

That scope is valuable. It answers the defensible question: **"What can
we infer from public trial registrations, and how confident should we be
in that inference?"**

## High-Impact Free Features

### 1. Trial Change Intelligence

**Plain-English intuition:** A static registry dashboard tells users what
exists. Change intelligence tells them what changed this week — and that
is what makes analysts return.

**Technical definition:** Compare the latest record for each `nct_id` with
its immediately preceding snapshot in `fct_trial_snapshot`. Generate typed
events at the `trial × snapshot_date` grain, such as recruitment-status,
enrollment, dates, locations, and protocol changes.

Weekly historical snapshots are already collected, so this is the most
natural next feature.

#### Events detectable for free

- Recruitment status changed: `RECRUITING → ACTIVE_NOT_RECRUITING`,
  `RECRUITING → COMPLETED`, `NOT_YET_RECRUITING → RECRUITING`, or
  `RECRUITING → WITHDRAWN`.
- Enrollment changed: planned or actual enrollment increase/decrease.
- New country, state, city, or facility added.
- Site removed from the registry record.
- Study start, primary-completion, or completion dates revised.
- Last update posted changed.
- Sponsor or responsible-party value changed.
- Phase, study type, intervention, condition, primary outcome, or
  eligibility text changed, if those fields are snapshotted at the
  raw/silver level.
- A new competing recruiting study entered a selected condition/geography/phase market.
- A competing study exited recruitment.

#### Business value

A clinical strategy or competitive-intelligence analyst does not need to
manually rerun dozens of searches. They can open CTI and ask:

> "Show me the 20 new recruiting Phase II–III studies in oncology that
> added Washington or California locations this week, ranked by likely
> competition relevance."

That produces a realistic, public-data intelligence workflow without
claiming private site or patient insights.

#### Recommended dashboard page

**Page name:** `8_Change_Intelligence.py`

Core UI:

- Date-range selector: last 7, 30, or 90 days.
- Condition, phase, country/state, sponsor, and status filters.
- KPI cards: New trials, newly recruiting, completed, withdrawn, locations
  added, locations removed.
- Event timeline with filters by event type.
- "Top competitor movements" table.
- Exportable CSV for a weekly intelligence brief.
- Trial detail drawer with "before vs. after" values.

### 2. Explainable Feasibility Scorecard

**Plain-English intuition:** The priority queue is powerful only if a user
can explain why trial A ranks above trial B.

**Technical definition:** Turn the output of
`mart_feasibility_priority_queue` into a factorized scorecard where each
score component, raw input, weighting rule, directionality, source date,
and data-confidence flag is visible at the individual-trial level.

A feasibility priority queue and a `feasibility_score_weights` dbt seed
already exist, so the score architecture is already configurable.

#### What to expose

- **Competition pressure:** Number of related actively recruiting studies
  in the same geography and condition.
- **Site overlap pressure:** Count or share of locations shared with
  potentially competing studies.
- **Sponsor concentration:** Whether a few sponsors dominate trial
  activity in a selected market.
- **Recency:** How recently the competing study was posted or updated.
- **Enrollment burden proxy:** Planned enrollment and, where appropriate,
  number of listed locations.
- **Geographic saturation:** Active/recruiting trial count for
  `condition × geography`.
- **Data confidence:** Completeness, freshness, and ambiguity flags from
  `mart_data_reliability`.

Do not label this "site feasibility score" without actual site
performance and patient-access data. Better labels:

- **Registry-Based Competition Pressure**
- **Feasibility Research Priority**
- **Public-Registry Opportunity Score**
- **Competitive Recruitment Risk Signal**

#### Scorecard formula

A transparent normalized score could be:

```
Priority Score = wc*C + wo*O + wg*G + we*E + wr*R - wq*Q
```

Where:

- `C` = competition density.
- `O` = site-overlap pressure.
- `G` = geographic saturation.
- `E` = enrollment burden proxy.
- `R` = recency / change momentum.
- `Q` = data-quality penalty.
- `w*` values come from the existing dbt seed rather than hardcoded
  dashboard logic.

**Critical design choice:** show the complete breakdown and let users
change the weights in a sandbox side panel without persisting them. This
creates a realistic "what-if" workflow while retaining the canonical
dbt-generated baseline ranking.

### 3. Protocol Similarity Explorer

**Plain-English intuition:** "Same condition" is often too broad. A Phase
III trial for early-stage disease with one endpoint and one population may
not meaningfully compete with a late-stage trial using a different
intervention class and eligibility profile.

**Technical definition:** Create a trial-pair similarity model using
normalized registry text and structured fields, returning comparable-study
candidates and an explainable feature-level similarity breakdown.

#### Free data features to use

From ClinicalTrials.gov records, derive:

- Condition overlap.
- Intervention names and intervention types.
- Phase overlap.
- Study type and allocation.
- Primary-purpose similarity.
- Recruitment status overlap.
- Country/state/city/facility overlap.
- Enrollment-size similarity.
- Age-range overlap.
- Sex eligibility compatibility.
- Healthy-volunteer eligibility.
- Lead sponsor overlap.
- Primary-outcome text similarity.
- Eligibility-criteria text similarity.
- Start and completion-date overlap.
- Frequency of condition/intervention terms across the active landscape.

#### Implementation approach

Start with **transparent rules**, then add a text-similarity layer.

**V1: deterministic comparability**

- Same normalized condition: +0.30
- Same phase: +0.20
- Overlapping geography: +0.20
- Same intervention type: +0.10
- Similar enrollment band: +0.10
- Overlapping recruitment period: +0.10

**V2: lightweight semantic similarity**

- `TfidfVectorizer` for eligibility and primary-outcome text.
- Cosine similarity for trial-pair candidate ranking.
- Limit comparisons to condition/phase prefiltered candidate sets to avoid
  an O(n²) full-table pairwise join.
- Keep the structured score separate from text similarity so results
  remain interpretable.

**V3: embeddings, only after V1/V2**

Use a local open-source sentence-transformer only if deployment cost and
model download constraints are acceptable. For a public free deployment,
precompute embeddings offline, version the resulting artifact, and never
generate embeddings on dashboard load.

#### Dashboard output

- Select an index trial.
- Display the top 10–25 comparable studies.
- Show total similarity score and factor breakdown.
- List shared conditions, phase, geography, intervention types, enrollment
  bands, and recruitment dates.
- Highlight overlapping listed locations.
- Include a "Why is this comparable?" sentence generated from
  deterministic factors — not an ungrounded LLM explanation.

This feature would closely resemble the user value of Citeline's trial
benchmarking without pretending to have the curated, proprietary benchmark
data.

### 4. Geographic Saturation and Market Entry

**Plain-English intuition:** A country with many trials may be attractive
because it is experienced, or difficult because it is already saturated.
The dashboard should let users see both.

**Technical definition:** Model a `condition × geography × time` panel
that measures active/recruiting activity, sponsor concentration,
enrollment burden proxy, study start rates, recruitment exits, and
registry completeness.

`dim_geography`, `fct_trial_site`, `mart_condition_geography_trends`, and
the Geography Trends page already exist — this should be an enhancement,
not a rebuild.

#### New metrics to add

| Metric | Calculation | Interpretation |
|---|---|---|
| Recruiting trial count | Distinct actively recruiting trial IDs | Current competitive volume |
| New recruiting entrants | Trial IDs entering recruiting status in period | Momentum / recently increased competition |
| Recruiting exits | Trial IDs leaving recruiting status in period | Potentially easing competition |
| Listed-location count | Distinct `trial × location` rows | Registry-reported operational footprint |
| Enrollment demand proxy | Sum of planned enrollment for recruiting studies | Approximate market recruitment burden |
| Sponsor HHI | Sum of squared sponsor shares in a market | Whether activity is diversified or concentrated |
| Trial density growth | Percent change in recruiting trials period-over-period | Whether saturation is accelerating |
| Data-confidence rate | Share of records passing freshness/completeness thresholds | Whether the signal should be trusted |

#### Useful visual

Use a bivariate matrix rather than just a map:

- X-axis: competition density.
- Y-axis: change momentum.
- Bubble size: planned enrollment burden.
- Color: data confidence.
- Tooltip: top sponsors and recent study changes.

Quadrants become interpretable:

- **High density + high growth:** escalating recruitment competition.
- **Low density + high growth:** emerging market to monitor.
- **High density + low growth:** established but saturated.
- **Low density + low growth:** potentially lower activity, but may lack
  infrastructure — do not infer opportunity automatically.

### 5. Sponsor Strategy Lens

**Plain-English intuition:** A sponsor landscape should answer more than
"who has the most trials?" It should reveal whether sponsors are
expanding, concentrating, or withdrawing in a condition and geography.

**Technical definition:** Build `mart_sponsor_competitive_momentum` at the
`sponsor × condition × geography × period` grain, using weekly snapshots
and status transitions.

The existing sponsor dimension, trial-sponsor bridge, and Sponsor
Landscape page make this feasible.

#### Free features

- Recruiting trials by sponsor and therapeutic area.
- New recruiting studies by sponsor in the last 30/90 days.
- Countries/states newly entered by a sponsor.
- Completion/termination/withdrawal transitions by sponsor.
- Portfolio mix by phase.
- Enrollment burden proxy by sponsor.
- Sponsor concentration by geography.
- "Emerging competitor" detection: low historical presence but high
  recent growth.
- "Dominant competitor" flag: high active-study and planned-enrollment
  share.

**Caution:** Registry sponsor fields are self-reported and organization
names vary. Add sponsor-normalization rules, retain raw sponsor names, and
surface a confidence flag when matching is fuzzy.

### 6. Data Confidence and Freshness

The **Data Reliability** page is an unusually strong differentiator. Make
it a first-class decision-control layer, not a technical appendix.

#### Add these user-facing reliability indicators

- **Record freshness:** Days since a trial's last update posted date.
- **Snapshot freshness:** Days since the last successful ingestion.
- **Completeness:** Presence of enrollment, dates, phase, sponsor,
  conditions, eligibility, and locations.
- **Ambiguity:** Multiple or blank condition terms, inconsistent sponsor
  strings, incomplete location hierarchy.
- **Volatility:** Number of material changes in the past 30/90 days.
- **Source scope:** "ClinicalTrials.gov registry data only" badge on every
  intelligence view.
- **Confidence tier:** High / medium / low, based on transparent rules.

Example label:

> **Medium confidence:** Study record was updated 84 days ago; has phase,
> status, planned enrollment, and 12 listed locations, but lacks primary
> completion date and eligibility text.

This is the kind of product discipline enterprise users respect because it
prevents overinterpretation.

## Recommended Roadmap

### Phase 1: Highest ROI

Build these first because the warehouse prerequisites already exist.

1. **Change Intelligence**
   - Uses the snapshot history immediately.
   - Delivers a recurring weekly-use case.
   - Demonstrates slowly changing data and event modeling.
   - Provides strong material for a dashboard landing page and portfolio
     screenshots.

2. **Explainable Priority Scorecard**
   - Builds directly on the existing `mart_feasibility_priority_queue`.
   - Turns a ranking into an auditable decision tool.
   - Makes the config-driven weights visible to nontechnical stakeholders.
   - Improves interview storytelling around responsible analytics.

3. **Priority Queue filtering and CSV export**
   - Add condition, phase, country/state, sponsor, status, and freshness
     filters.
   - Allow "export the currently filtered table."
   - Add a download-ready feasibility brief with score components and
     caveats.

### Phase 2: Strong Differentiators

4. **Protocol Similarity Explorer**
   - Start with deterministic comparability.
   - Add TF-IDF primary outcome and eligibility text similarity later.
   - Keep every match explainable.

5. **Geographic Saturation Matrix**
   - Extend the trends mart rather than create dashboard-only
     calculations.
   - Compare volume, growth, sponsor concentration, enrollment demand
     proxy, and confidence.

6. **Sponsor Competitive Momentum**
   - Add entering/exiting studies, phase mix, geography expansion, and
     trend momentum.

### Phase 3: Advanced Portfolio Features

7. **Saved research scenarios**
   - A URL-encoded or session-state scenario: condition, phase,
     country/state, date window, and score weights.
   - No authentication/database required for V1.
   - Users can reproduce a dashboard view by sharing a link.

8. **Decision brief generator**
   - Create a downloadable CSV and concise Markdown/HTML report.
   - Include filters, extraction timestamp, data scope, confidence
     caveats, ranked studies, competitor movements, and methodology.
   - Do not use generative text unless every assertion is traceable to a
     calculated metric.

9. **Semantic-layer metrics documentation**
   - Publish metric definitions, grain, lineage, validity caveats, and
     owner/source for every KPI.
   - Highly relevant to analytics engineering, healthcare analytics, and
     consulting interviews.

## Production Design

### Event mart pattern

Create a new model named `mart_trial_change_events.sql` with a clear
grain:

> **One row per detected material change for one NCT ID between two
> consecutive CTI snapshots.**

Suggested columns:

```sql
trial_change_event_id
nct_id
previous_snapshot_date
current_snapshot_date
event_type
field_name
previous_value
current_value
numeric_delta
event_severity
condition_key
phase
overall_status
lead_sponsor_name
country
state
detected_at
source_last_update_posted_date
data_confidence_tier
```

Suggested event types:

```text
STATUS_CHANGED
ENROLLMENT_CHANGED
LOCATION_ADDED
LOCATION_REMOVED
SPONSOR_CHANGED
PHASE_CHANGED
PRIMARY_OUTCOME_CHANGED
ELIGIBILITY_CHANGED
START_DATE_CHANGED
PRIMARY_COMPLETION_DATE_CHANGED
COMPLETION_DATE_CHANGED
```

### Defensive Python pattern

Use Python only for robust extraction and normalization; use dbt/DuckDB
for business transformations and event logic.

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import hashlib
import json


@dataclass(frozen=True)
class SnapshotMetadata:
    nct_id: str
    snapshot_at: datetime
    payload_sha256: str
    source_last_update_date: str | None


def stable_payload_hash(payload: dict[str, Any]) -> str:
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def build_snapshot_metadata(payload: dict[str, Any]) -> SnapshotMetadata:
    protocol_section = payload.get("protocolSection", {})
    identification = protocol_section.get("identificationModule", {})
    status = protocol_section.get("statusModule", {})

    nct_id = identification.get("nctId")
    if not isinstance(nct_id, str) or not nct_id.strip():
        raise ValueError("ClinicalTrials.gov payload is missing a valid nctId.")

    last_update = status.get("lastUpdatePostDateStruct", {}).get("date")
    if last_update is not None and not isinstance(last_update, str):
        raise TypeError("lastUpdatePostDateStruct.date must be a string or null.")

    return SnapshotMetadata(
        nct_id=nct_id.strip(),
        snapshot_at=datetime.now(UTC),
        payload_sha256=stable_payload_hash(payload),
        source_last_update_date=last_update,
    )
```

Why this matters: every raw study payload gets a validated ClinicalTrials.gov
identifier, a consistent timestamp showing when CTI observed the record, a
deterministic hash to identify whether a complete raw payload changed, and
a source-reported update date kept separate from CTI's own ingestion time.
That separation matters because "ClinicalTrials.gov says it was updated
last week" and "the pipeline fetched it today" are different facts —
reliability metrics should expose both.

### dbt testing requirements

For every new mart:

- Add `not_null` tests on keys and snapshot dates.
- Add `unique` tests for the stated grain.
- Add accepted-value tests for event types and confidence tiers.
- Add relationship tests from `nct_id` to `dim_trial`.
- Add singular tests such as:
  - no negative elapsed days between consecutive snapshots;
  - no `LOCATION_ADDED` event with a null new location key;
  - no duplicate change event for the same `nct_id`, field, value
    transition, and snapshot pair;
  - no score contribution outside expected normalized range;
  - score components sum to the final displayed score within a rounding
    tolerance.

## Trade-offs

- **Coverage:** Free ClinicalTrials.gov data can give excellent
  registry-based competition and study-design intelligence, but it cannot
  validate real site throughput, patient availability, investigator
  relationships, claims-derived incidence, CTMS workflow status, or
  confidential enrollment performance. Do not imply otherwise.
- **Compute:** Trial-pair similarity can become expensive quickly.
  Pre-filter candidates by condition, phase, and geography; persist
  features in dbt; and avoid calculating all pairs at Streamlit runtime.
- **Maintenance:** Change events require stable normalization. If
  condition, sponsor, intervention, or location parsing changes, version
  the logic and distinguish true source changes from changes introduced by
  the transformation code itself.

## Key Considerations

### Product positioning

Use this concise project description:

> **CTI Dashboard is an open, reproducible clinical-trial feasibility and
> competition-intelligence workbench. It transforms public
> ClinicalTrials.gov records and weekly snapshots into explainable signals
> for trial landscape research, recruitment-competition monitoring,
> geographic saturation analysis, and data-confidence-aware
> prioritization.**

That communicates ambition without making unsupported claims.

### Terms to use carefully

| Term | Safe usage in CTI | Avoid claiming |
|---|---|---|
| Site selection | "Registry-informed site research" or "site-location overlap analysis" | "Optimal site selection" or proven site performance |
| Recruitment | "Recruitment competition signal" or "planned enrollment burden proxy" | Actual recruitment rates or patient availability |
| Feasibility | "Public-registry feasibility research" | End-to-end operational feasibility |
| Risk score | "Explainable analytical priority signal" | Clinical, regulatory, or operational risk prediction |
| Patient access | "Not available from registry-only data" | Patient identification or patient-level recruitment potential |
| Benchmark | "Registry-derived descriptive benchmark" | Validated commercial performance benchmark |

### Production checklist

1. Can every dashboard score, label, and recommendation-like statement be
   traced to a dbt model, source field, formula, snapshot date, and
   data-quality rule?
2. Does each page visibly state what public registry data can show, what
   it cannot show, and when the displayed evidence was last refreshed?

The platform's current maturity — live deployment, automatic main-branch
deploys, weekly data refresh, a repaired fresh-clone dbt seed step, a
clean 73-test dbt run, and real-data ingestion — means the project is
ready to focus next on analytical differentiation rather than
infrastructure.

## External references consulted

- [IQVIA — Clinical Data Analytics Solutions](https://www.iqvia.com/solutions/technologies/orchestrated-clinical-trials/clinical-data-analytics-solutions/clinical-analytics)
- [H1 — Clinical](https://h1.com/clinical/)
- [Citeline — Plus](https://www.citeline.com/en/plus)
- [Citeline — Trialtrove](https://www.citeline.com/en/products-services/clinical/trialtrove)
