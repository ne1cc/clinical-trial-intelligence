# Trial Similarity Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic (V1-only) trial comparability scorer: a
new dbt intermediate model gathering comparability features per trial, a
new mart self-joining and scoring pairs (bounded to each trial's top 25
matches), and a new dashboard page reusing the row-click breakdown
pattern from the explainable feasibility scorecard.

**Architecture:** dbt computes and persists everything (features model →
scoring mart with a `qualify row_number() <= 25` window filter); the
dashboard is presentation-only, matching this project's "dashboard reads
Gold marts only" rule. Weights are config-driven (YAML + dbt seed,
dbt-tested to stay in sync), mirroring the existing feasibility score's
pattern exactly.

**Tech Stack:** dbt-duckdb (SQL, one new macro), Python/pytest (weight
sync test), Streamlit (one new page).

**Spec:** `docs/superpowers/specs/2026-09-05-trial-similarity-explorer-design.md`

## Global Constraints

- All 7 similarity factors are deterministic 0/1 matches (additive
  boolean bonuses), not min-max normalized — pairwise comparability is
  inherently "same or different," unlike the feasibility score's
  continuous inputs.
- **Null-handling rule:** a null on either side of an equality or
  overlap check must never count as a match. Plain SQL `a.x = b.x`
  already evaluates to `NULL` (falsy) when either side is null — this is
  correct and must not be "fixed" with `coalesce()`. Verified this
  session: `NULL = NULL` inside a `CASE WHEN` correctly yields 0, not 1.
  The one deliberate exception is age-range overlap, where a null bound
  means "no age restriction" (unbounded, always compatible on that
  side) — see Task 2's exact SQL.
- Weights (`config/similarity_weights.yml` +
  `dbt_clinical_trials/seeds/similarity_score_weights.csv`) must sum to
  1.0 and must match each other exactly — dbt-tested in Task 3, mirroring
  the existing `tests/test_metrics.py` pattern for
  `config/score_weights.yml` / `feasibility_score_weights.csv`.
- The mart's grain is **one row per `(nct_id_a, nct_id_b)` pair, where
  `nct_id_b` is one of `nct_id_a`'s top-25 most comparable trials** (not
  all pairs — bounded via a window filter before materializing, since a
  full self-join is ~6.7M row-pairs for ~2,618 trials).
- Do not modify `mart_feasibility_priority_queue`, any existing
  dashboard page, or `dim_trial` — this is a wholly new, independent
  mart and page. `int_trial_comparability_features` joins
  `int_current_trial_status` + `stg_trials` directly (mirroring
  `dim_trial.sql`'s own join pattern) rather than extending `dim_trial`,
  since these fields are single-purpose to this feature.
- No `bridge_trial_intervention` model exists and none should be
  created for this feature — aggregate `intervention_type` directly from
  `stg_trial_interventions` via `list(distinct ...)`.
- Verified working in this session (DuckDB, via direct `duckdb.sql()`
  calls) before writing this plan: `list(distinct x)`,
  `regexp_extract` + `try_cast` for age parsing, `list_intersect` +
  `len(...) > 0` for set-overlap checks (including both-empty and
  one-empty cases, which correctly return 0/false, not an error), and
  `concat_ws('; ', ...)` skipping `NULL` arguments (confirmed:
  `concat_ws('; ', 'a', NULL, 'b', NULL)` → `'a; b'`). Every SQL pattern
  below uses only these verified constructs.
- `tests/test_dashboard_smoke.py` has a **hardcoded** `PAGES` list (not
  auto-discovered) — Task 5 must add the new page to it explicitly, or
  the new page gets zero smoke-test coverage.

---

## Task 1: Schema extension — capture `allocation` and `primary_purpose`

**Files:**
- Modify: `src/transform/flatten_studies.py`
- Modify: `dbt_clinical_trials/models/staging/stg_trials.sql`
- Modify: `tests/test_normalization.py`
- Test: `tests/test_normalization.py::test_flatten_study_produces_all_entities`

**Interfaces:**
- Consumes: the existing `dig()` helper in `flatten_studies.py`
  (`dig(obj, *keys) -> Any`, already used for
  `dig(design, "enrollmentInfo", "count")` a few lines above where this
  task adds two more calls).
- Produces: `allocation` and `primary_purpose` columns on
  `silver_trials` / `stg_trials`, consumed by Task 2's
  `int_trial_comparability_features` model.

- [ ] **Step 1: Add the two fields to `flatten_study()`**

In `src/transform/flatten_studies.py`, find the `trial` dict (it already
has `"phase_raw": phase_raw,` and `"enrollment_count": dig(design,
"enrollmentInfo", "count"),` — add these two lines immediately after the
`enrollment_type` line:

```python
        "allocation": dig(design, "designInfo", "allocation"),
        "primary_purpose": dig(design, "designInfo", "primaryPurpose"),
```

- [ ] **Step 2: Extend the shared test fixture**

In `tests/test_normalization.py`, find `FIXTURE_STUDY`'s
`"designModule"` block (currently
`{"studyType": "INTERVENTIONAL", "phases": ["PHASE2", "PHASE3"],
"enrollmentInfo": {"count": 300, "type": "ESTIMATED"}}`). Replace it
with:

```python
        "designModule": {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE2", "PHASE3"],
            "designInfo": {
                "allocation": "RANDOMIZED",
                "primaryPurpose": "TREATMENT",
            },
            "enrollmentInfo": {"count": 300, "type": "ESTIMATED"},
        },
```

- [ ] **Step 3: Add assertions to the existing flatten test**

In `test_flatten_study_produces_all_entities`, immediately after the
existing `assert trial["enrollment_count"] == 300` line, add:

```python
    assert trial["allocation"] == "RANDOMIZED"
    assert trial["primary_purpose"] == "TREATMENT"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_normalization.py -v`
Expected: all tests pass, including the two new assertions.

- [ ] **Step 5: Add the passthrough columns to `stg_trials.sql`**

In `dbt_clinical_trials/models/staging/stg_trials.sql`, immediately
after the `enrollment_type,` line, add:

```sql
    allocation,
    primary_purpose,
```

- [ ] **Step 6: Backfill from existing bronze (no re-ingestion needed)**

Run: `make transform && make dbt-run`
Expected: both complete successfully. This reruns the existing
`flatten_study()` over already-downloaded bronze JSON (unchanged bronze
schema — schema-drift detection compares raw bronze field paths, which
this doesn't touch — so `data/bronze/_schema_baseline.json` needs no
update).

- [ ] **Step 7: Verify the backfilled data with a real query**

Run:
```bash
uv run python -c "
import duckdb
c = duckdb.connect('data/warehouse/clinical_trials.duckdb', read_only=True)
print(c.execute('select allocation, primary_purpose, count(*) from main_staging.stg_trials group by 1, 2 order by 3 desc limit 5').df())
"
```
Expected: non-null, non-empty `allocation`/`primary_purpose` values
(e.g. `RANDOMIZED`/`TREATMENT`) appear with real counts — confirms the
backfill actually populated real data, not just that the pipeline ran.

- [ ] **Step 8: Commit**

```bash
git add src/transform/flatten_studies.py dbt_clinical_trials/models/staging/stg_trials.sql tests/test_normalization.py
git commit -m "feat(ingest): capture allocation and primary_purpose fields"
```

---

## Task 2: New macro and comparability-features intermediate model

**Files:**
- Create: `dbt_clinical_trials/macros/parse_age_years.sql`
- Create: `dbt_clinical_trials/models/intermediate/int_trial_comparability_features.sql`

**Interfaces:**
- Consumes: `stg_trials` (Task 1's new `allocation`/`primary_purpose`
  columns, plus existing `phase_normalized`, `study_type`,
  `enrollment_count`, `healthy_volunteers`, `sex`, `minimum_age`,
  `maximum_age`, `start_date`, `completion_date`), `int_current_trial_status`
  (one row per `nct_id` at its own latest snapshot — same join pattern
  as `dim_trial.sql`), `bridge_trial_condition` (already current-only
  per its own header comment), `stg_trial_interventions`,
  `fct_trial_site`.
- Produces: one row per `nct_id` with columns `nct_id`,
  `phase_normalized`, `study_type`, `allocation`, `primary_purpose`,
  `enrollment_count`, `enrollment_band` (`'small'`/`'medium'`/`'large'`/
  `null`), `healthy_volunteers`, `sex`, `minimum_age_years`,
  `maximum_age_years` (both integer or null), `start_date`,
  `completion_date`, `condition_groups` (list of varchar),
  `intervention_types` (list of varchar), `states` (list of varchar) —
  consumed by Task 4's `mart_trial_similarity`.

- [ ] **Step 1: Write the age-parsing macro**

Create `dbt_clinical_trials/macros/parse_age_years.sql`:

```sql
{#- ClinicalTrials.gov ages are free text like "18 Years" or "N/A".
    Extracts the leading integer; non-numeric input (missing/unbounded)
    returns null, which callers must treat as "no restriction," not
    zero. Verified: try_cast(regexp_extract('18 Years', '(\d+)', 1) as
    integer) -> 18; same on 'N/A' -> null. -#}
{% macro parse_age_years(column) %}
    try_cast(regexp_extract({{ column }}, '(\d+)', 1) as integer)
{% endmacro %}
```

- [ ] **Step 2: Write the intermediate model**

Create `dbt_clinical_trials/models/intermediate/int_trial_comparability_features.sql`:

```sql
-- One row per NCT ID (current record from latest snapshot): the fields
-- needed to score pairwise trial comparability against another trial.
-- Presentation-neutral -- assembles inputs only; mart_trial_similarity
-- does the actual pairwise scoring.
with current_trials as (
    select ingestion_run_id, nct_id
    from {{ ref('int_current_trial_status') }}
),

trial_fields as (
    select
        t.nct_id,
        t.phase_normalized,
        t.study_type,
        t.allocation,
        t.primary_purpose,
        t.enrollment_count,
        case
            when t.enrollment_count is null then null
            when t.enrollment_count < 50 then 'small'
            when t.enrollment_count <= 200 then 'medium'
            else 'large'
        end as enrollment_band,
        t.healthy_volunteers,
        t.sex,
        {{ parse_age_years('t.minimum_age') }} as minimum_age_years,
        {{ parse_age_years('t.maximum_age') }} as maximum_age_years,
        t.start_date,
        t.completion_date
    from {{ ref('stg_trials') }} t
    inner join current_trials c
        on t.ingestion_run_id = c.ingestion_run_id and t.nct_id = c.nct_id
),

conditions as (
    select nct_id, list(distinct condition_group) as condition_groups
    from {{ ref('bridge_trial_condition') }}
    group by nct_id
),

interventions as (
    select i.nct_id, list(distinct i.intervention_type) as intervention_types
    from {{ ref('stg_trial_interventions') }} i
    inner join current_trials c
        on i.ingestion_run_id = c.ingestion_run_id and i.nct_id = c.nct_id
    where i.intervention_type is not null
    group by i.nct_id
),

latest_site_snapshot as (
    select max(snapshot_date) as snapshot_date from {{ ref('fct_trial_site') }}
),

geography as (
    select f.nct_id, list(distinct f.state_normalized) as states
    from {{ ref('fct_trial_site') }} f
    inner join latest_site_snapshot ls on f.snapshot_date = ls.snapshot_date
    where f.state_normalized is not null
    group by f.nct_id
)

select
    tf.*,
    coalesce(co.condition_groups, []) as condition_groups,
    coalesce(iv.intervention_types, []) as intervention_types,
    coalesce(g.states, []) as states
from trial_fields tf
left join conditions co on tf.nct_id = co.nct_id
left join interventions iv on tf.nct_id = iv.nct_id
left join geography g on tf.nct_id = g.nct_id
```

- [ ] **Step 3: Build and verify**

Run: `make dbt-run`
Expected: `int_trial_comparability_features` builds successfully (view,
in `main_intermediate`).

Run:
```bash
uv run python -c "
import duckdb
c = duckdb.connect('data/warehouse/clinical_trials.duckdb', read_only=True)
df = c.execute('select * from main_intermediate.int_trial_comparability_features limit 3').df()
print(df.to_string())
print('row count:', c.execute('select count(*) from main_intermediate.int_trial_comparability_features').fetchone()[0])
"
```
Expected: 3 rows print with populated `condition_groups`,
`intervention_types`, `states` as non-empty lists for most rows; row
count is close to (may be slightly less than, if any trials have zero
sites/conditions/interventions) the total trial count seen in earlier
sessions (~2,618).

- [ ] **Step 4: Commit**

```bash
git add dbt_clinical_trials/macros/parse_age_years.sql dbt_clinical_trials/models/intermediate/int_trial_comparability_features.sql
git commit -m "feat(dbt): add trial comparability features intermediate model"
```

---

## Task 3: Similarity weights config, seed, and Python sync tests

**Files:**
- Create: `config/similarity_weights.yml`
- Create: `dbt_clinical_trials/seeds/similarity_score_weights.csv`
- Create: `tests/test_similarity.py`

**Interfaces:**
- Produces: the 7 factor weights (summing to 1.0), consumed by Task 4's
  `mart_trial_similarity.sql` via a `weights` CTE reading the seed
  (same pattern `mart_feasibility_priority_queue.sql` already uses for
  `feasibility_score_weights`).

- [ ] **Step 1: Write the config file**

Create `config/similarity_weights.yml`:

```yaml
# Trial Similarity Explorer score configuration.
# Deterministic comparability signal between two trials -- NOT a claim
# of clinical equivalence, and NOT itself a competition/recruitment
# signal (two trials can be highly comparable in design while
# recruiting in entirely different places).
#
# Must stay consistent with dbt seed similarity_score_weights.csv
# (tests/test_similarity.py enforces this).

similarity:
  # Each factor is a deterministic 0/1 match (not min-max normalized --
  # pairwise comparability is inherently "same or different," unlike
  # the feasibility score's continuous inputs). Weights must sum to 1.0.
  weights:
    same_condition: 0.15
    same_phase: 0.20
    geography_overlap: 0.15
    intervention_type_overlap: 0.15
    study_design_match: 0.15
    eligibility_compatible: 0.10
    enrollment_band_match: 0.10
```

- [ ] **Step 2: Write the dbt seed**

Create `dbt_clinical_trials/seeds/similarity_score_weights.csv`:

```csv
component,weight,description
same_condition,0.15,Trials share at least one mapped condition group
same_phase,0.20,Trials have the same normalized phase
geography_overlap,0.15,Trials share at least one listed U.S. state
intervention_type_overlap,0.15,Trials share at least one intervention type
study_design_match,0.15,Trials match on study type, allocation, and primary purpose (all three)
eligibility_compatible,0.10,Trials have compatible sex, healthy-volunteer, and age-range eligibility
enrollment_band_match,0.10,Trials fall in the same enrollment size band (small/medium/large)
```

- [ ] **Step 3: Write the Python sync tests**

Create `tests/test_similarity.py`:

```python
"""Trial similarity weight-configuration tests: config/seed consistency."""

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SIMILARITY_WEIGHTS_YML = ROOT / "config" / "similarity_weights.yml"
SEED_CSV = ROOT / "dbt_clinical_trials" / "seeds" / "similarity_score_weights.csv"


def load_similarity_config() -> dict:
    return yaml.safe_load(SIMILARITY_WEIGHTS_YML.read_text(encoding="utf-8"))


def load_seed_weights() -> dict[str, float]:
    with open(SEED_CSV, encoding="utf-8") as handle:
        return {row["component"]: float(row["weight"]) for row in csv.DictReader(handle)}


def test_similarity_weights_sum_to_one():
    weights = load_similarity_config()["similarity"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_yaml_weights_match_dbt_seed():
    yaml_weights = load_similarity_config()["similarity"]["weights"]
    assert yaml_weights == load_seed_weights()
```

- [ ] **Step 4: Load the seed and run the tests**

Run: `make dbt-seed`
Expected: `similarity_score_weights` loads successfully (3 seeds become
4).

Run: `uv run pytest tests/test_similarity.py -v`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add config/similarity_weights.yml dbt_clinical_trials/seeds/similarity_score_weights.csv tests/test_similarity.py
git commit -m "feat: add trial similarity weight config, seed, and sync tests"
```

---

## Task 4: `mart_trial_similarity` and dbt tests

**Files:**
- Create: `dbt_clinical_trials/models/marts/mart_trial_similarity.sql`
- Modify: `dbt_clinical_trials/models/marts/_marts.yml`
- Create: `dbt_clinical_trials/tests/assert_similarity_score_within_bounds.sql`
- Create: `dbt_clinical_trials/tests/assert_no_self_similarity_pairs.sql`
- Create: `dbt_clinical_trials/tests/assert_similarity_rank_is_dense_sequence.sql`

**Interfaces:**
- Consumes: `int_trial_comparability_features` (Task 2),
  `similarity_score_weights` seed (Task 3), the `generate_surrogate_key`
  macro (`dbt_clinical_trials/macros/generate_surrogate_key.sql`,
  already used throughout the project — signature:
  `generate_surrogate_key(field_list)`).
- Produces: `main_marts.mart_trial_similarity` with columns
  `trial_similarity_key`, `nct_id_a`, `nct_id_b`, `similarity_score`,
  `similarity_rank`, and for each of the 7 factors — `<factor>` (0/1
  match flag), `weight_<factor>`, `weighted_<factor>` — plus
  `similarity_explanation`. Consumed by Task 5's dashboard page.

- [ ] **Step 1: Write the mart**

Create `dbt_clinical_trials/models/marts/mart_trial_similarity.sql`:

```sql
-- Deterministic trial-pair comparability. Grain: one row per
-- (nct_id_a, nct_id_b) pair, where nct_id_b is one of nct_id_a's top-25
-- most comparable trials. A structural/design comparability signal --
-- NOT a claim of clinical equivalence, and NOT itself a competition or
-- recruitment signal. Weights live in the similarity_score_weights seed
-- (mirrored in config/similarity_weights.yml).
with weights as (
    select
        max(case when component = 'same_condition' then weight end) as w_condition,
        max(case when component = 'same_phase' then weight end) as w_phase,
        max(case when component = 'geography_overlap' then weight end) as w_geography,
        max(case when component = 'intervention_type_overlap' then weight end) as w_intervention,
        max(case when component = 'study_design_match' then weight end) as w_design,
        max(case when component = 'eligibility_compatible' then weight end) as w_eligibility,
        max(case when component = 'enrollment_band_match' then weight end) as w_enrollment
    from {{ ref('similarity_score_weights') }}
),

pairs as (
    select
        a.nct_id as nct_id_a,
        b.nct_id as nct_id_b,
        a.phase_normalized as a_phase, b.phase_normalized as b_phase,
        a.enrollment_band as a_enrollment_band, b.enrollment_band as b_enrollment_band,
        case when len(list_intersect(a.condition_groups, b.condition_groups)) > 0
            then 1 else 0 end as same_condition,
        case when a.phase_normalized = b.phase_normalized
            then 1 else 0 end as same_phase,
        case when len(list_intersect(a.states, b.states)) > 0
            then 1 else 0 end as geography_overlap,
        case when len(list_intersect(a.intervention_types, b.intervention_types)) > 0
            then 1 else 0 end as intervention_type_overlap,
        case when a.study_type = b.study_type
            and a.allocation = b.allocation
            and a.primary_purpose = b.primary_purpose
            then 1 else 0 end as study_design_match,
        case when (a.sex = b.sex or a.sex = 'ALL' or b.sex = 'ALL')
            and a.healthy_volunteers = b.healthy_volunteers
            and (a.minimum_age_years is null or b.maximum_age_years is null
                 or a.minimum_age_years <= b.maximum_age_years)
            and (b.minimum_age_years is null or a.maximum_age_years is null
                 or b.minimum_age_years <= a.maximum_age_years)
            then 1 else 0 end as eligibility_compatible,
        case when a.enrollment_band = b.enrollment_band
            then 1 else 0 end as enrollment_band_match
    from {{ ref('int_trial_comparability_features') }} a
    inner join {{ ref('int_trial_comparability_features') }} b
        on a.nct_id != b.nct_id
),

scored as (
    select
        p.*,
        w.w_condition as weight_same_condition,
        w.w_phase as weight_same_phase,
        w.w_geography as weight_geography_overlap,
        w.w_intervention as weight_intervention_type_overlap,
        w.w_design as weight_study_design_match,
        w.w_eligibility as weight_eligibility_compatible,
        w.w_enrollment as weight_enrollment_band_match,
        round(w.w_condition * p.same_condition, 4) as weighted_same_condition,
        round(w.w_phase * p.same_phase, 4) as weighted_same_phase,
        round(w.w_geography * p.geography_overlap, 4) as weighted_geography_overlap,
        round(w.w_intervention * p.intervention_type_overlap, 4) as weighted_intervention_type_overlap,
        round(w.w_design * p.study_design_match, 4) as weighted_study_design_match,
        round(w.w_eligibility * p.eligibility_compatible, 4) as weighted_eligibility_compatible,
        round(w.w_enrollment * p.enrollment_band_match, 4) as weighted_enrollment_band_match,
        round(
            w.w_condition * p.same_condition
            + w.w_phase * p.same_phase
            + w.w_geography * p.geography_overlap
            + w.w_intervention * p.intervention_type_overlap
            + w.w_design * p.study_design_match
            + w.w_eligibility * p.eligibility_compatible
            + w.w_enrollment * p.enrollment_band_match,
            4
        ) as similarity_score
    from pairs p
    cross join weights w
)

select
    {{ generate_surrogate_key(['nct_id_a', 'nct_id_b']) }} as trial_similarity_key,
    nct_id_a,
    nct_id_b,
    similarity_score,
    row_number() over (
        partition by nct_id_a order by similarity_score desc, nct_id_b
    ) as similarity_rank,
    same_condition, weight_same_condition, weighted_same_condition,
    same_phase, weight_same_phase, weighted_same_phase,
    geography_overlap, weight_geography_overlap, weighted_geography_overlap,
    intervention_type_overlap, weight_intervention_type_overlap, weighted_intervention_type_overlap,
    study_design_match, weight_study_design_match, weighted_study_design_match,
    eligibility_compatible, weight_eligibility_compatible, weighted_eligibility_compatible,
    enrollment_band_match, weight_enrollment_band_match, weighted_enrollment_band_match,
    concat_ws(
        '; ',
        case when same_condition = 1 then 'shared condition mapping' end,
        case when same_phase = 1 then 'same phase (' || a_phase || ')' end,
        case when geography_overlap = 1 then 'overlapping U.S. states' end,
        case when intervention_type_overlap = 1 then 'shared intervention type' end,
        case when study_design_match = 1 then 'matching study type, allocation, and primary purpose' end,
        case when eligibility_compatible = 1 then 'compatible eligibility criteria' end,
        case when enrollment_band_match = 1 then 'similar enrollment size (' || a_enrollment_band || ')' end
    ) as similarity_explanation
from scored
qualify similarity_rank <= 25
```

- [ ] **Step 2: Add column docs and tests to `_marts.yml`**

In `dbt_clinical_trials/models/marts/_marts.yml`, add a new top-level
model entry (after the existing `mart_feasibility_priority_queue`
entry, matching its indentation):

```yaml
  - name: mart_trial_similarity
    description: >
      Deterministic trial-pair comparability -- a structural/design
      signal, not clinical equivalence and not itself a competition
      signal. One row per (nct_id_a, nct_id_b) pair, nct_id_a's top 25
      matches only.
    columns:
      - name: trial_similarity_key
        tests: [not_null, unique]
      - name: nct_id_a
        tests: [not_null]
      - name: nct_id_b
        tests: [not_null]
      - name: similarity_score
        tests: [not_null]
      - name: similarity_rank
        tests: [not_null]
      - name: same_condition
        tests: [not_null]
      - name: weight_same_condition
        tests: [not_null]
      - name: weighted_same_condition
        tests: [not_null]
      - name: same_phase
        tests: [not_null]
      - name: weight_same_phase
        tests: [not_null]
      - name: weighted_same_phase
        tests: [not_null]
      - name: geography_overlap
        tests: [not_null]
      - name: weight_geography_overlap
        tests: [not_null]
      - name: weighted_geography_overlap
        tests: [not_null]
      - name: intervention_type_overlap
        tests: [not_null]
      - name: weight_intervention_type_overlap
        tests: [not_null]
      - name: weighted_intervention_type_overlap
        tests: [not_null]
      - name: study_design_match
        tests: [not_null]
      - name: weight_study_design_match
        tests: [not_null]
      - name: weighted_study_design_match
        tests: [not_null]
      - name: eligibility_compatible
        tests: [not_null]
      - name: weight_eligibility_compatible
        tests: [not_null]
      - name: weighted_eligibility_compatible
        tests: [not_null]
      - name: enrollment_band_match
        tests: [not_null]
      - name: weight_enrollment_band_match
        tests: [not_null]
      - name: weighted_enrollment_band_match
        tests: [not_null]
      - name: similarity_explanation
```

- [ ] **Step 3: Write the three singular tests**

Create `dbt_clinical_trials/tests/assert_similarity_score_within_bounds.sql`:

```sql
-- The weighted similarity score must always land in [0, 1].
select trial_similarity_key, similarity_score
from {{ ref('mart_trial_similarity') }}
where similarity_score < 0
   or similarity_score > 1
```

Create `dbt_clinical_trials/tests/assert_no_self_similarity_pairs.sql`:

```sql
-- A trial must never be listed as comparable to itself.
select trial_similarity_key, nct_id_a, nct_id_b
from {{ ref('mart_trial_similarity') }}
where nct_id_a = nct_id_b
```

Create `dbt_clinical_trials/tests/assert_similarity_rank_is_dense_sequence.sql`:

```sql
-- Per nct_id_a, similarity_rank must be a dense 1..N sequence (no gaps,
-- no duplicates), capped at 25 by the mart's own qualify filter.
with per_trial as (
    select
        nct_id_a,
        count(*) as row_count,
        count(distinct similarity_rank) as distinct_ranks,
        max(similarity_rank) as max_rank,
        min(similarity_rank) as min_rank
    from {{ ref('mart_trial_similarity') }}
    group by nct_id_a
)
select *
from per_trial
where row_count != distinct_ranks
   or max_rank != row_count
   or min_rank != 1
```

- [ ] **Step 4: Build and test**

Run: `make dbt-run`
Expected: `mart_trial_similarity` builds successfully (32 models total,
up from 30).

Run: `make dbt-test`
Expected: all tests pass, including the 3 new singular tests and the
~27 new `_marts.yml` column tests (roughly 114 total, up from 84 after
PR #1 — the exact count depends on which of PR #1/#2 have merged by the
time this runs; treat "no failures" as the bar, not an exact number).

- [ ] **Step 5: Spot-check real data**

Run:
```bash
uv run python -c "
import duckdb
c = duckdb.connect('data/warehouse/clinical_trials.duckdb', read_only=True)
df = c.execute('''
    select nct_id_a, nct_id_b, similarity_score, similarity_rank, similarity_explanation
    from main_marts.mart_trial_similarity
    order by nct_id_a, similarity_rank
    limit 5
''').df()
print(df.to_string())
"
```
Expected: 5 rows with populated `similarity_explanation` text and
`similarity_score` values between 0 and 1.

- [ ] **Step 6: Commit**

```bash
git add dbt_clinical_trials/models/marts/mart_trial_similarity.sql dbt_clinical_trials/models/marts/_marts.yml dbt_clinical_trials/tests/assert_similarity_score_within_bounds.sql dbt_clinical_trials/tests/assert_no_self_similarity_pairs.sql dbt_clinical_trials/tests/assert_similarity_rank_is_dense_sequence.sql
git commit -m "feat(dbt): add mart_trial_similarity with bounds/uniqueness/rank tests"
```

---

## Task 5: Dashboard page

**Files:**
- Create: `dashboard/pages/8_Trial_Similarity.py`
- Modify: `dashboard/components/data.py`
- Modify: `tests/test_dashboard_smoke.py`

**Interfaces:**
- Consumes: `mart_trial_similarity` (Task 4), `data.trial_explorer()`
  (existing function in `dashboard/components/data.py`, used for the
  index-trial search — same NCT ID/title fields already used by
  `7_Trial_Explorer.py`), `page_setup`/`guarded_footer` (existing,
  `dashboard/components/guardrails.py`).
- Produces: nothing consumed by a later task — this is the final task.

- [ ] **Step 1: Add the data-access function**

In `dashboard/components/data.py`, add this function (after the
existing `priority_queue()` function, matching the file's existing
`@st.cache_data(ttl=600)` pattern — note this one queries
`_connection()` directly with a parameter, since `query(sql)` doesn't
support bound parameters and `nct_id` must never be interpolated
directly into SQL text):

```python
@st.cache_data(ttl=600)
def trial_similarity(nct_id: str) -> pd.DataFrame:
    return (
        _connection()
        .execute(
            "select * from main_marts.mart_trial_similarity"
            " where nct_id_a = ? order by similarity_rank",
            [nct_id],
        )
        .df()
    )
```

- [ ] **Step 2: Write the dashboard page**

Create `dashboard/pages/8_Trial_Similarity.py`:

```python
"""Trial Similarity Explorer — deterministic protocol comparability."""

import pandas as pd
import streamlit as st
from components import data
from components.guardrails import guarded_footer, page_setup

page_setup("Trial Similarity Explorer")
data.require_warehouse()

st.info(
    "This page scores **structural trial-design comparability** — "
    "shared phase, geography, intervention type, study design, and "
    "eligibility criteria. It is not a claim of clinical equivalence, "
    "and unlike the Competition Landscape and Priority Queue pages, it "
    "is not itself a competition or recruitment signal."
)

trials = data.trial_explorer()
search = st.text_input("Search for an index trial by NCT ID or title")

candidates = trials
if search:
    needle = search.strip().lower()
    mask = candidates["brief_title"].str.lower().str.contains(
        needle, na=False
    ) | candidates["nct_id"].str.lower().str.contains(needle, na=False)
    candidates = candidates[mask]

if candidates.empty:
    st.warning("No trials match that search.")
    st.stop()

options = {
    f"{row.nct_id} — {row.brief_title}": row.nct_id
    for row in candidates.head(50).itertuples()
}
selected_label = st.selectbox("Select the index trial", list(options))
selected_nct_id = options[selected_label]

matches = data.trial_similarity(selected_nct_id)

if matches.empty:
    st.info("No comparable trials found in the current warehouse for this trial.")
    guarded_footer()
    st.stop()

st.subheader(f"Top comparable trials for {selected_nct_id}")
st.caption("Click a row to see its full factor breakdown below.")
match_columns = [
    "similarity_rank",
    "nct_id_b",
    "similarity_score",
    "similarity_explanation",
]
match_event = st.dataframe(
    matches[match_columns],
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = match_event.selection.rows if match_event.selection else []
if selected_rows:
    m = matches.iloc[selected_rows[0]]
    st.subheader(f"Factor breakdown — {selected_nct_id} vs {m['nct_id_b']}")
    factor_rows = [
        ("Same condition", m["same_condition"], m["weight_same_condition"], m["weighted_same_condition"]),
        ("Same phase", m["same_phase"], m["weight_same_phase"], m["weighted_same_phase"]),
        ("Geography overlap", m["geography_overlap"], m["weight_geography_overlap"], m["weighted_geography_overlap"]),
        (
            "Intervention type overlap",
            m["intervention_type_overlap"],
            m["weight_intervention_type_overlap"],
            m["weighted_intervention_type_overlap"],
        ),
        ("Study design match", m["study_design_match"], m["weight_study_design_match"], m["weighted_study_design_match"]),
        (
            "Eligibility compatible",
            m["eligibility_compatible"],
            m["weight_eligibility_compatible"],
            m["weighted_eligibility_compatible"],
        ),
        (
            "Enrollment band match",
            m["enrollment_band_match"],
            m["weight_enrollment_band_match"],
            m["weighted_enrollment_band_match"],
        ),
    ]
    breakdown = pd.DataFrame(
        factor_rows,
        columns=["Factor", "Match (1=yes)", "Weight", "Weighted contribution"],
    )
    st.dataframe(breakdown, hide_index=True, width="stretch")
    weighted_total = sum(row[3] for row in factor_rows)
    st.metric(
        "Weighted total (sum of weighted contributions)",
        f"{weighted_total:.4f}",
        help="Matches similarity_score for this pair.",
    )
    st.caption(m["similarity_explanation"])

guarded_footer()
```

- [ ] **Step 3: Register the page in the smoke test**

In `tests/test_dashboard_smoke.py`, add
`"dashboard/pages/8_Trial_Similarity.py",` to the `PAGES` list (after
the existing `7_Trial_Explorer.py` entry).

- [ ] **Step 4: Lint**

Run: `uv run ruff check src tests dashboard`
Expected: no errors.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest`
Expected: all tests pass, including the new page in the smoke-test
parametrization.

- [ ] **Step 6: Manual verification in the browser**

```bash
uv run streamlit run dashboard/app.py --server.port=8505 --server.headless true
```
Navigate to `http://localhost:8505/Trial_Similarity`. Search for any
known trial (e.g. by partial title), select it, confirm the top-25
matches table renders with non-empty `similarity_explanation` text.
Click a row; confirm the factor breakdown table renders and the
"Weighted total" metric matches that row's `similarity_score` from the
matches table above. Stop the server afterward
(`lsof -ti:8505 | xargs -r kill`).

- [ ] **Step 7: Commit**

```bash
git add dashboard/pages/8_Trial_Similarity.py dashboard/components/data.py tests/test_dashboard_smoke.py
git commit -m "feat(dashboard): add Trial Similarity Explorer page"
```
