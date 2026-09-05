# Trial Similarity Explorer — Design

## Goal

Add a "Protocol Similarity Explorer" (Tier 2 of `docs/competitive_positioning.md`'s
backlog): given one index trial, find and rank the most genuinely
comparable other trials using deterministic, explainable rules over
existing registry fields — not just "same condition," which is too
broad to mean "competing" or "comparable."

This is the V1 (deterministic-rules) scope only, per the backlog's own
staged plan. Text-similarity (TF-IDF over eligibility/outcome text) is
explicitly deferred to a later iteration.

## Context

- The platform (ingestion, warehouse, dbt marts, dashboard, Fly
  deployment) is live and stable; PR #1 (explainable feasibility
  scorecard) and PR #2 (Priority Queue filters/export) are open,
  independent of this feature.
- `docs/competitive_positioning.md` lists this as a Tier 2 backlog item,
  and — unlike Trial Change Intelligence or Sponsor Competitive
  Momentum — it doesn't depend on multi-snapshot history, since
  comparability is inherently point-in-time.
- Verified against real bronze JSON this session:
  `protocolSection.designModule.designInfo.allocation` and
  `.primaryPurpose` exist in every study record but are **not**
  currently captured anywhere in the pipeline. Since bronze retains raw
  JSON immutably, these can be backfilled by rerunning
  `make transform && make dbt-run` against existing bronze — no
  re-ingestion needed.
- No `bridge_trial_intervention` model exists (only
  `bridge_trial_condition` and `bridge_trial_sponsor`). Building one
  isn't warranted for a single internal consumer — intervention types
  are aggregated directly from `stg_trial_interventions` instead.
- `minimum_age`/`maximum_age` are free-text (e.g. `"18 Years"`, `"N/A"`)
  with no existing parsing macro.
- **Known dataset limitation, stated honestly rather than hidden:**
  because this project's scope is a single therapeutic area
  (Alzheimer's/dementia), nearly all 2,618 current trials already share
  `condition_group = alzheimers_disease`. The "same condition" factor
  will rarely discriminate *in this dataset* — phase, geography, and
  intervention-type overlap will do most of the real work. The factor
  is still scored (and weighted, deliberately lower than the backlog's
  original suggestion) because it becomes meaningful the moment a
  second condition is ingested (e.g. the study guide's own "Parkinson
  Disease" exercise).

## Architecture decision: where similarity is computed

**Chosen: a new dbt mart, self-joining a trial-features intermediate
model, bounded with a top-N-per-trial window filter before
materializing.** Not computed in the dashboard (would put scoring logic
and weights in a Python-embedded SQL string, breaking from every other
scored feature in this app and this project's stated rule that "the
dashboard reads Gold marts only; no dashboard-side business logic").
Not a Python analysis module like `src/analysis/roi_scenarios.py` —
that module is a live per-render calculator over a handful of editable
assumptions, not a precedent for warehouse-scale (~6.7M row-pair)
pairwise computation.

With ~2,618 trials, a full self-join is ~6.7M row-pairs — trivial for
DuckDB to compute once per `dbt run` — but only the top 25 matches per
trial (~65,000 rows total) are persisted, via
`qualify row_number() over (partition by nct_id_a order by similarity_score desc) <= 25`
in the final model, so nothing wasteful is stored on disk.

## Schema extension

- `src/transform/flatten_studies.py`: add to the `trial` dict —
  `"allocation": dig(design, "designInfo", "allocation")` and
  `"primary_purpose": dig(design, "designInfo", "primaryPurpose")`
  (same `dig()` helper already used for `enrollmentInfo.count` a few
  lines above).
- `dbt_clinical_trials/models/staging/stg_trials.sql`: add `allocation`
  and `primary_purpose` passthrough columns from `silver_trials`.
- Backfill by rerunning `make transform && make dbt-run` against
  existing bronze. `data/bronze/_schema_baseline.json` needs **no**
  update: schema-drift detection (`src/quality/schema_drift.py`)
  compares raw bronze JSON field paths, which are unchanged here — this
  extends what silver *extracts* from fields already present in bronze,
  not what the API returns.

## New dbt macro: `parse_age_years`

Alongside the existing `macros/parse_partial_date.sql`,
`macros/normalize_text.sql`, `macros/safe_divide.sql`. Extracts the
leading integer from free-text age strings (`"18 Years"` → `18`);
non-numeric or null input (e.g. `"N/A"`) returns `null` (unbounded, not
zero — an unbounded age range must not be treated as incompatible with
everything).

## New model: `int_trial_comparability_features.sql`

One row per `nct_id`, at the latest snapshot. Presentation-neutral —
assembles inputs only, no scoring:

- From `dim_trial`/`stg_trials`: `phase_normalized`, `study_type`,
  `allocation`, `primary_purpose`, `enrollment_count` (bucketed into
  `enrollment_band`: small &lt;50, medium 50-200, large &gt;200),
  `healthy_volunteers`, `sex`, `minimum_age_years`/`maximum_age_years`
  (via the new macro), `start_date`, `completion_date`.
- From `bridge_trial_condition` → `dim_condition`: `condition_group`.
- From `stg_trial_interventions`: `list(distinct intervention_type)` per
  `nct_id` (a DuckDB `list` aggregate — no new bridge table).
- From `fct_trial_site`: `list(distinct state_normalized)` per
  `nct_id`, latest snapshot only.

## New config + seed: similarity weights

`config/similarity_weights.yml` (mirrors `config/score_weights.yml`) +
`dbt_clinical_trials/seeds/similarity_score_weights.csv` (mirrors
`feasibility_score_weights.csv`). Seven factors, weights sum to 1.0:

| Factor | Weight | Deterministic check |
|---|---|---|
| `same_condition` | 0.15 | `condition_group` matches |
| `same_phase` | 0.20 | `phase_normalized` matches |
| `geography_overlap` | 0.15 | state lists intersect (non-empty) |
| `intervention_type_overlap` | 0.15 | intervention-type lists intersect |
| `study_design_match` | 0.15 | `study_type`, `allocation`, AND `primary_purpose` all three match |
| `eligibility_compatible` | 0.10 | same `sex` (or either `ALL`), same `healthy_volunteers`, AND age ranges overlap (null bound = unbounded, always compatible on that side) |
| `enrollment_band_match` | 0.10 | same `enrollment_band` |

Each factor is a 0/1 deterministic match — additive boolean bonuses per
the backlog's own V1 framing, not min-max normalized like the
feasibility score (pairwise comparability is inherently "same or
different," not a continuous quantity).

**Null-handling rule, stated explicitly so it isn't "fixed" away during
implementation:** a null value on either side of an equality or overlap
check must never count as a match. SQL's native `a.field = b.field`
already evaluates to `NULL` (falsy) when either side is null, which is
the correct behavior here — two trials both missing `allocation` are
not thereby "the same," they're both unknown. Do not `coalesce()` these
comparisons to force a match. The one deliberate exception is the age
range overlap check, where a null bound means "no age restriction"
(unbounded), which correctly *always* overlaps rather than never
matching: `(a.min_age_years is null or b.max_age_years is null or
a.min_age_years <= b.max_age_years) and (b.min_age_years is null or
a.max_age_years is null or b.min_age_years <= a.max_age_years)`.

## New model: `mart_trial_similarity.sql`

Self-joins `int_trial_comparability_features` (`a.nct_id != b.nct_id`),
computes each of the 7 factors and the weighted `similarity_score`,
keeps only the top 25 matches per trial via the `qualify` window filter
above. Grain: **one row per `(nct_id_a, nct_id_b)` pair, where
`nct_id_b` is one of `nct_id_a`'s top-25 most comparable trials.**

Columns: `trial_similarity_key` (surrogate key), `nct_id_a`, `nct_id_b`,
`similarity_score`, `similarity_rank` (per `nct_id_a`), each factor's
raw match flag and weighted contribution (mirrors the
`weight_*`/`weighted_*` column pattern from `mart_feasibility_priority_queue`,
per PR #1), plus a deterministic `similarity_explanation` text field
(same `concat_ws`-built-phrase pattern already used for
`priority_explanation`).

**New dbt tests:**
- Similarity weights sum to 1.0 (mirrors the existing three-way
  feasibility-weight sync test in `tests/test_metrics.py` — add the
  equivalent for these weights).
- `similarity_score` always in `[0, 1]`.
- No self-pairs (`nct_id_a != nct_id_b`).
- Uniqueness on `(nct_id_a, nct_id_b)`.
- `similarity_rank` is a dense 1..25 sequence per `nct_id_a` (no gaps,
  no duplicates).

## New dashboard page: `8_Trial_Similarity.py`

Reuses the row-click → breakdown interaction pattern from the
explainable scorecard (PR #1) for UI consistency across the app:

1. Guardrail banner (`page_setup`, `require_warehouse`) with a caption
   distinguishing this page from the competition/feasibility marts:
   this is a **trial-design comparability signal**, not clinical
   equivalence and not itself a competition signal (two trials can be
   highly comparable in design while recruiting in entirely different
   places).
2. A search control to pick an index trial (by NCT ID or brief-title
   text match — same interaction style as the existing Trial Explorer
   search box).
3. Once selected: a table of that trial's top 25 matches (rank, NCT ID,
   linked brief title, `similarity_score`, `similarity_explanation`).
4. Click a matched row → a factor breakdown table (factor name, index
   trial's raw value, matched trial's raw value, match Y/N, weight,
   weighted contribution), with a total row reconciling to the
   displayed `similarity_score` — identical presentation pattern to the
   feasibility scorecard breakdown.

## Testing

- `make dbt-run` (32 models, up from 30 — one new intermediate view plus
  one new mart table) and `make dbt-test` (new tests above, in addition
  to the existing 84).
- `uv run pytest` including a new test mirroring
  `tests/test_metrics.py`'s existing feasibility-weight sync check, for
  the new similarity weights.
- Manual verification in the browser: pick a known trial, confirm the
  top-25 list is non-empty and sensible (e.g. same phase/state trials
  rank higher than unrelated ones), click a match, confirm the
  breakdown's weighted contributions sum to the displayed score.

## Out of scope (explicitly deferred)

- TF-IDF/embedding text similarity over eligibility or outcome text
  (the backlog's V2/V3) — a separate future iteration once V1 is
  proven useful.
- Any change to `mart_feasibility_priority_queue` or the competition
  marts — this is a wholly new, independent mart and page.
- Extending `allocation`/`primary_purpose` to any other existing mart
  or page — scoped to this feature's needs only.
