# Fly.io Deployment — Design

## Goal

Deploy the Streamlit dashboard (`dashboard/app.py`) to Fly.io as a running
service that keeps its own DuckDB warehouse populated, rebuilding it from a
live `make pipeline` run on first boot and refreshing it weekly thereafter —
matching this project's own "weekly snapshot" design intent
(`config/project_config.yml`'s `scope.refresh_cadence: weekly`).

This spec covers only the deployment artifacts (Dockerfile, entrypoint
script, Fly config, docs). It does not cover running `fly launch`,
`fly deploy`, `fly volumes create`, or `fly secrets set` — those provision
real, billed cloud resources under the user's Fly account and are the
user's to run.

## Context

- The pipeline (`make ingest && make transform && make dbt-run && make
  dbt-test && make quality-report`, or `make pipeline` which is
  `ingest transform dbt-run dbt-test quality-report`) already runs
  end-to-end locally; confirmed in this session (2,618 real trials, 30 dbt
  models, 73 dbt tests, all green).
- All data paths (`src/utils/paths.py::resolve_path`) resolve relative to
  `project_root()` (repo root) unless `CTI_PROJECT_ROOT` or an absolute
  path is set. `config/project_config.yml`'s `paths:` block points at
  `data/bronze/...`, `data/silver`, `data/gold`, `data/warehouse/...` — all
  relative. `dbt_clinical_trials/profiles.yml.example` likewise points at
  `data/warehouse/clinical_trials.duckdb` relative to the process's working
  directory (the Makefile always runs dbt from the repo root).
  **Consequence:** mounting a persistent volume at the container's
  `/app/data` (with the app's working directory at `/app`) makes every
  path resolve onto the volume with zero env-var or code changes.
- The dashboard's DuckDB connection (`dashboard/components/data.py`) opens
  `read_only=True` and is cached process-wide via `st.cache_resource` — a
  single long-lived connection per process, not per-request.
- Root-caused earlier this session: ClinicalTrials.gov's bot protection
  blocks `httpx` specifically (TLS/handshake fingerprinting), not `curl`,
  stdlib `urllib`, or `requests`. The ingest client was already migrated to
  `requests` (commit `db4347d`). This should behave the same from Fly's
  network, but has not been verified from an actual Fly egress IP — flagged
  as a residual risk, not a blocker.

## Architecture

**One Fly Machine, one Fly Volume, two co-located processes in one
container.** Not Fly's `[processes]` multi-process-group feature: that
schedules each process group onto its own separate machine(s), and a Fly
Volume attaches to exactly one machine at a time — two machines cannot both
mount the same volume to share the DuckDB file. Co-locating the web server
and the refresh loop inside one container sidesteps this entirely.

```
┌─────────────────────────── Fly Machine ───────────────────────────┐
│  entrypoint.sh (PID 1's child tree)                                │
│    1. If /app/data/warehouse/clinical_trials.duckdb is missing:    │
│       run `make pipeline` synchronously (first-boot bootstrap)     │
│    2. Background: refresh loop (see below)                         │
│    3. Foreground: streamlit run dashboard/app.py                   │
│                          │                                          │
│                          ▼                                          │
│                  /app/data  (bind mount)                            │
└──────────────────────────┬──────────────────────────────────────────┘
                            │
                     Fly Volume (1GB)
```

### Refresh loop (inside `entrypoint.sh`)

No cron daemon dependency — a small bash loop, consistent with this
project's existing minimal-dependencies style (config-driven YAML, no
orchestration framework for the MVP per `docs/architecture.md` §6):

- A marker file `/app/data/.last_pipeline_run` stores the UNIX timestamp of
  the last successful `make pipeline` completion.
- Every hour, the loop checks: has 7 days (604800 seconds) elapsed since
  the marker's timestamp (or does the marker not exist)? If yes, run
  `make pipeline`, and on success, write the current timestamp to the
  marker.
- The loop runs as a background job (`&`) so `streamlit` can run in the
  foreground as the container's PID 1 substitute (via `exec`), so Fly's
  process supervision (SIGTERM on deploy/restart) reaches Streamlit
  directly.
- Pipeline output is appended to `/app/data/logs/pipeline.log` (created via
  `mkdir -p`) so a failed refresh is inspectable via `fly ssh console` or
  `fly logs`, without crashing the container or interrupting the dashboard.
- A `make pipeline` failure (e.g., a transient ClinicalTrials.gov error) is
  logged but must not update the marker — the loop must retry on its next
  hourly check rather than silently waiting another 7 days.
- **Verified this session:** DuckDB does not auto-create parent
  directories for a new database file (`duckdb.connect()` on a missing
  directory raises `IOException`, confirmed by direct test), and nothing
  in `src/ingest`/`src/transform`/`src/quality` creates `data/warehouse/`
  — only `make setup`'s own `mkdir -p` does, locally, once. A Fly Volume
  mounts empty on its first attach, shadowing anything the Dockerfile
  baked into the image at that mount path. Consequence: `entrypoint.sh`
  must `mkdir -p` the full data tree itself on every boot, before calling
  `make pipeline` — not rely on the Dockerfile's build-time `mkdir`.

### Fly configuration (`fly.toml`)

- `[[mounts]]`: one volume, mounted at `/app/data`, minimum size (1GB —
  comfortably fits the ~20MB warehouse plus bronze/silver growth over many
  weekly runs; the user can resize later via `fly volumes extend` if
  needed).
- `auto_stop_machines = "off"` (string mode), `auto_start_machines = false`
  (boolean — Fly's schema requires a bool here, not the string mode
  `auto_stop_machines` accepts; caught by `flyctl config validate`)
  are irrelevant here since the machine must stay running continuously for
  the background refresh loop — an auto-suspended machine would never fire
  its weekly job. This is called out explicitly in the deploy doc as a
  real, non-free recurring cost (roughly $2-5/month on Fly's smallest
  shared-CPU tier as of this writing) — not the free/auto-sleep model many
  Fly demo apps use.
- HTTP service on port 8501 (Streamlit's default), with a health check
  against Streamlit's built-in `/_stcore/health` endpoint.
- `[env]`: none required — no secrets exist in this project (the API is
  public, unauthenticated); `CTI_PROJECT_ROOT`, `CTI_DUCKDB_PATH`, etc. are
  left at their defaults since the volume-at-`/app/data` approach makes
  overriding them unnecessary.

### Dockerfile

- Base: `python:3.12-slim`.
- Installs `uv` (via the official install script or pinned pip install),
  copies the repo, runs `uv sync --all-groups --frozen` (matches CI's exact
  install command, so the image reproduces what CI already verified),
  then `uv run dbt deps --project-dir dbt_clinical_trials --profiles-dir
  dbt_clinical_trials`.
- Copies `dbt_clinical_trials/profiles.yml.example` to
  `dbt_clinical_trials/profiles.yml` at build time (mirroring what `make
  setup` does locally), since there's no interactive setup step in a
  container build.
- `ENTRYPOINT ["/app/entrypoint.sh"]`.
- `EXPOSE 8501`.

## Out of scope

- Running any `fly` CLI provisioning command (`fly launch`, `fly deploy`,
  `fly volumes create`, `fly secrets set`, `fly scale`) — these create
  real, billed resources under the user's account and are the user's to
  run, or to explicitly ask for by name.
- Verifying ClinicalTrials.gov's bot protection against Fly's actual
  egress IPs (can't be tested until the app is actually deployed).
- Any change to the ingestion/transform/dbt pipeline itself — this spec is
  packaging-only.

## Files touched

- Create: `Dockerfile`
- Create: `entrypoint.sh`
- Create: `fly.toml`
- Create: `docs/DEPLOY_FLY.md` (mirrors the structure of the existing
  `docs/DEPLOY_STREAMLIT.md`, documents the manual `fly launch`/`fly
  deploy`/`fly volumes create` steps the user runs themselves, the cost
  note, and the untested-egress-IP caveat)
- Modify: `README.md` documentation index table (add the new doc, same
  pattern as the existing `docs/DEPLOY_STREAMLIT.md` row — that row is
  currently absent from the index table too; add both in the same edit)
