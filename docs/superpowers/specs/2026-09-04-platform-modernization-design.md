# Platform Modernization — Design

Date: 2026-09-04
Status: Approved (all five design sections approved by the user in chat)
Branch: `feat/platform-modernization`

## Goal

Upgrade the project from a well-built local pipeline into a modern, production-shaped
data platform, targeting a generalist Data Engineer audience:

1. Real orchestration (Dagster software-defined assets) replacing Makefile sequencing
   and the bash refresh loop.
2. Real weekly scheduling (GitHub Actions cron) with a durable object-storage lake
   (GCS free tier), making the project's "weekly snapshot history" claim demonstrably true.
3. Deep CI: static typing, coverage gate, dbt build on fixtures, pre-commit.
4. Data contracts on gold marts and orchestrator-enforced quality gates.
5. Warehouse portability (dbt-bigquery on free tier) as a completed stretch goal.
6. Docker polish (multi-stage, non-root) on top of the existing Fly.io deployment.

Explicit user instruction: do not scope-protect; build the best finished product.
Everything below is in scope.

## Context (current state)

- Pipeline: `make pipeline` = ingest → transform → dbt-run → dbt-test → quality-report.
- Stack: Python 3.11+ / uv, requests + tenacity, pydantic v2, pandas + pyarrow,
  DuckDB, dbt-core + dbt-duckdb (1.12 / 1.10.1), Streamlit, loguru, ruff, pytest.
- Architecture: bronze (raw JSON + manifests) → silver (parquet entities) → gold
  (dbt dimensional models in DuckDB); config-driven YAML; extensive docs; 54 pytest
  tests passing (8 smoke tests skipped without real data) + 73 dbt tests.
- Deployment: Docker + Fly.io implemented on branch `feat/fly-deploy` (Dockerfile,
  entrypoint.sh, fly.toml; one machine + volume; in-container weekly bash refresh
  loop; first-boot `make pipeline` bootstrap). That branch is a prerequisite for the
  serving-layer changes here and should merge into (or be rebased under) this work.
- Known gaps: no orchestration, no scheduler, CI runs only ruff + pytest, no type
  checking, no pre-commit, no container-native CI data tests.

## Architecture (approved topology)

```
GitHub Actions (cron, weekly)          Fly.io (serving)              GCS (lake, free tier)
┌──────────────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│ dagster job execute      │     │ Streamlit dashboard  │     │ bronze/  (raw +  │
│   → ingest → transform   │────▶│ pulls latest marts   │◀────│   manifests)     │
│   → dbt build            │     │ from the lake        │     │ silver/ (parquet)│
│   → asset checks         │     │ (read-only)          │     │ gold/  (duckdb)  │
│   → publish-on-green     │     └──────────────────────┘     └──────────────────┘
└──────────────────────────┘   Dagster webserver runs LOCALLY
                               only (dagster dev) for the
                               lineage UI and run history
```

Role separation:

- **Dagster** owns orchestration: assets, checks, retries, schedules, lineage UI.
  It is never a long-running cloud service; CI executes the weekly job headlessly
  via `dagster job execute`.
- **GitHub Actions** owns scheduling: weekly cron triggers the Dagster job; run
  history in the repo is the public, verifiable evidence of weekly snapshots.
- **GCS** owns durability: the lake is the system of record; the Fly volume becomes
  a cache.
- **Fly.io** owns serving: the container pulls `gold/latest/clinical_trials.duckdb`
  from GCS instead of re-running the pipeline in-container. The in-container
  pipeline bootstrap remains as a fallback (`CTI_BOOTSTRAP_MODE=gcs|pipeline`).
  This retires the bash loop's scheduling role and eliminates the unverified
  ClinicalTrials.gov egress-IP risk from the Fly machine entirely.

## Components

### 1. Dagster project — `src/orchestration/`

- `definitions.py` — `Definitions` object wiring assets, asset checks, resources,
  schedules, jobs.
- `assets/bronze.py` — wraps `src.ingest` (paginated pull, tenacity retry policy,
  manifests). Incremental by default; `--full-refresh` preserved.
- `assets/silver.py` — wraps `src.transform` (flatten/normalize → parquet entities).
- dbt assets via `dagster-dbt`: models surfaced from `manifest.json` as individual
  assets (staging → intermediate → marts visible as a real graph), `seed → run →
  test` as one build path; dbt tests mapped to asset checks via `DagsterDbtTranslator`
  so all 73 dbt tests appear as check results.
- `checks.py` — asset checks wrapping `src/quality` (manifest reconciliation,
  cross-layer reconciliation, schema-drift detection).
- `resources.py` — CTG client, paths, GCS as injectable resources (swappable in tests).
- Weekly `ScheduleDefinition` on a refresh job.
- `dagster dev` runs locally only (lineage UI, run history, manual materializations).

Dependency placement: `dagster`, `dagster-webserver`, `dagster-dbt`, `dagster-gcp`
live in a uv dependency group `orchestration`. CI installs `--all-groups`; the Fly
serving image syncs without that group to stay lean. `mypy` and `pre-commit` join
the existing `dev` group.

### 2. GCS lake layout

```
gs://<bucket>/
  bronze/ingestion_run_id=<id>/api_responses/...   (append-only, per run)
  bronze/ingestion_run_id=<id>/manifests/...
  silver/ingestion_run_id=<id>/*.parquet
  gold/snapshots/<ingestion_run_id>/clinical_trials.duckdb   (immutable)
  gold/latest/clinical_trials.duckdb                          (pointer, swapped last)
```

- Publish-on-green only: uploads happen after all asset checks pass.
- The gold artifact is the built DuckDB warehouse file itself — the Fly dashboard's
  `read_only=True` connection works with zero dashboard code changes.
- Storage math: ~20 MB/week ≈ 1 GB/year; inside GCS free tier; no lifecycle
  pruning needed for MVP (bronze history is the asset).
- Auth: GCS service account key stored as a GitHub Actions secret.

### 3. CI changes

- `ci.yml` additions: mypy (scope below), pytest with `--cov-fail-under` gate,
  `dbt build` (seed + run + test) against a hand-crafted fixture bronze snapshot
  (~10 trials covering all statuses/phases, `tests/fixtures/`), which doubles as
  integration-test data.
- `pre-commit`: ruff check, ruff format, mypy on changed files, hygiene hooks.
- New `weekly.yml`: Monday cron (`workflow_dispatch` enabled) → `dagster job
  execute` → GCS upload. Actions' built-in failure notifications; optional Slack
  webhook via secret.

### 4. Data contracts

`contracts: { enforced: true }` with declared columns on gold mart models, so
schema drift fails the build instead of flowing downstream. Pairs with the existing
schema-drift detection on silver.

### 5. Stretch goal — in scope (user requested full scope): BigQuery portability

- `dbt-bigquery` profile; GCS → BigQuery load of silver; marts built on BQ in a
  separate workflow/job. Demonstrates "portable dbt models across DuckDB and BigQuery."

### 6. Docker polish (on top of `feat/fly-deploy`)

Multi-stage build (builder + runtime), non-root user, explicit HEALTHCHECK, and
`uv sync` without the `orchestration` group in the serving image.

## Data flow (one weekly run)

1. Trigger: Actions cron (or manual dispatch, or local `dagster job execute`).
2. Bronze materialize: existing ingest logic; raw pages + manifest under
   `data/bronze/api_responses/<ingestion_run_id>/`.
3. Check: ingestion integrity (manifest reconciliation). Fail → nothing downstream.
4. Silver materialize + checks: cross-layer reconciliation, schema drift.
5. dbt build: 30 models as graph nodes, 73 tests as checks, contracts on marts.
6. Publish-on-green: bronze dir (append), silver parquet, warehouse →
   `gold/snapshots/<run_id>/` then swap `gold/latest/`.
7. Serving: Fly pulls `latest`, verifies GCS md5 checksum, atomic swap (previous
   file kept as `.bak`), restarts the Streamlit child so the cached read-only
   connection picks up the new file.

**Deliberate choice — no partitions/backfills.** The registry serves current state
only; backfilling historical snapshots is impossible, and pretending otherwise would
undermine the project's honesty story. History accrues from real run dates only;
Dagster's materialization history provides run-level visibility.

**Deliberate choice — the warehouse is a rebuild artifact.** Every run builds DuckDB
fresh from bronze→silver; publish-on-green + append-only bronze means a failed run
leaves last week's lake state serving.

## Error handling

- Layered retries: tenacity keeps per-request retries inside the CTG client;
  Dagster `RetryPolicy` handles whole-asset retries — bronze 3 attempts exponential
  backoff (transient registry outages), silver/dbt 1 attempt (local, deterministic —
  failure is a real bug), publish 0 (visible immediately, idempotent to re-run).
- Failure isolation via the check graph mirrors the existing "only `success`
  manifests feed metrics" rule, now enforced by the orchestrator.
- Per-asset timeouts (bronze: 30 min) so a hung connection can't pin an Actions runner.
- Alerting without a daemon: Actions failure notifications (email; optional Slack).
  No always-on alerting infra.
- Deliberately absent: pagers, dead-letter queues, custom alert services.

## Testing

Three tiers, all visible in CI:

1. **Unit (mocked, every push)** — existing 54 tests preserved; new Dagster tests
   use `materialize()` with stub resources (CTG via `requests-mock`, GCS via an
   in-memory fake), including failure-propagation cases (bronze check fails →
   downstream never materializes).
2. **Integration (real DuckDB + dbt, no network, every push)** — fixture bronze
   snapshot drives `dbt build` in CI and an end-to-end fixture test asserting mart
   shapes/grains; mart contracts double as schema tests.
3. **Smoke (real API, opt-in)** — the 8 decoupled smoke tests stay manual/nightly
   via env var, never gating CI.

Static analysis: mypy strict on `src/orchestration` (new code, zero debt) and on
`src/ingest`, `src/utils`, `src/quality`; relaxed on `src/transform` initially
(pandas-heavy annotation churn deferred to its own pass) — recorded as a known gap.
Coverage: measure the real baseline first, set `--cov-fail-under` slightly above it,
ratchet upward.

## Sequencing

1. **Week 1 — Orchestration core:** `src/orchestration/` assets wrapping the
   existing pipeline; `dagster dev` showing the real asset graph; asset checks from
   `src/quality`; Dagster unit tests.
2. **Week 2 — CI depth + contracts:** mypy (scoped as above), coverage gate,
   pre-commit, fixture bronze snapshot, `dbt build` in CI, mart contracts.
3. **Week 3 — Scheduling + lake:** `weekly.yml`, GCS resource + publish-on-green,
   Fly entrypoint updated to pull-from-GCS (rebased on `feat/fly-deploy`), Docker
   polish.
4. **Week 4 — Portability + docs:** dbt-bigquery on free tier, README/architecture
   docs updated (new diagrams), resume bullets and interview talking points refreshed.

## Out of scope

- Any `fly`/`gcloud` provisioning by the assistant (real, billed resources — user runs).
- Population-adjusted density (ACS/SVI layers) — existing roadmap, separate effort.
- Oncology module via NCI CTS API.
- Dagster daemon/webserver deployed as a cloud service.
- Backfill of historical registry states (impossible by API design).

## Risks / open questions

- **ClinicalTrials.gov vs GitHub Actions egress IPs:** the earlier `httpx` block was
  TLS fingerprinting; `requests` behaves locally, but Actions IPs are untested.
  Mitigation: run one manual `workflow_dispatch` trial before relying on cron; the
  smoke tier covers this.
- **GCS auth in CI:** service-account key as an Actions secret; rotation is manual
  and documented (workload identity federation is the nicer pattern — noted, not
  built, to keep CI simple).
- **Branch ordering:** this work builds on `feat/fly-deploy`; merge/rebase order
  decided at implementation time.

## Files touched (expected)

- New: `src/orchestration/**`, `tests/test_orchestration_*.py`,
  `tests/fixtures/**`, `.github/workflows/weekly.yml`, `.pre-commit-config.yaml`,
  `dbt_clinical_trials/profiles.bigquery.yml`, deployment-image updates on the
  `feat/fly-deploy` line of work.
- Modified: `pyproject.toml` (dependency groups), `.github/workflows/ci.yml`,
  `dbt_clinical_trials/models/marts/**` (contracts), `README.md`,
  `docs/architecture.md`, and the deployment docs on the `feat/fly-deploy` line
  of work. This spec and `docs/platform_updates_2026-09-04.md` are already
  committed as part of the design phase.
