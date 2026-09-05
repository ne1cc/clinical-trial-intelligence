# Fly.io Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the deployment artifacts (Dockerfile, entrypoint script, Fly
config, docs) needed to run the Streamlit dashboard on Fly.io as an
always-on service that bootstraps its DuckDB warehouse on first boot and
refreshes it weekly.

**Architecture:** One Fly Machine, one Fly Volume mounted at `/app/data`,
one container running two co-located processes via a shell entrypoint: a
background weekly `make pipeline` refresh loop, and `streamlit` in the
foreground. No cron daemon; no multi-process Fly process groups (Fly
Volumes attach to only one machine, so co-location in a single container is
required to let both the refresh job and the dashboard share the same
warehouse file).

**Tech Stack:** Docker (`python:3.12-slim`), `uv`, bash, Fly.io (`fly.toml`
v2 app config).

**Spec:** `docs/superpowers/specs/2026-09-04-fly-deploy-design.md`

## Global Constraints

- All data paths resolve relative to the process working directory /
  `project_root()` (`src/utils/paths.py`); the container's working
  directory MUST be `/app` and the Fly Volume MUST mount at `/app/data` so
  every existing relative path (`data/bronze/...`, `data/warehouse/...`)
  resolves onto the persistent volume with no env-var or code changes.
- No secrets exist in this project (public, unauthenticated API) — no
  `fly secrets set` step is needed or should be documented as required.
- The container must NOT auto-suspend (`auto_stop_machines = "off"` in
  `fly.toml`) — the background refresh loop must keep running continuously.
- Do not run any `fly` CLI provisioning command (`fly launch`, `fly
  deploy`, `fly volumes create`, `fly secrets set`, `fly scale`) as part of
  implementing this plan — those are documented for the user to run
  themselves, never executed by an implementer or the controller.
- Dockerfile's dependency install step MUST be `uv sync --all-groups
  --frozen` (exact flags CI uses in `.github/workflows/ci.yml`), so the
  image reproduces what CI already verified rather than drifting from it.
- The refresh loop's marker file is `/app/data/.last_pipeline_run`,
  storing a UNIX timestamp; refresh cadence is exactly 7 days (604800
  seconds), checked hourly. A failed `make pipeline` run must NOT update
  the marker (so the loop retries within the hour rather than waiting
  another 7 days).
- Pipeline log output goes to `/app/data/logs/pipeline.log`.
- `entrypoint.sh` MUST `mkdir -p` the full `data/bronze/api_responses`,
  `data/bronze/manifests`, `data/silver`, `data/gold`, `data/warehouse`
  tree under `/app/data` on every boot, before calling `make pipeline`.
  Verified this session: DuckDB raises `IOException` rather than
  auto-creating a missing parent directory, and a Fly Volume mounts empty
  on its first attach — shadowing whatever the Dockerfile's own `mkdir`
  baked into the image at that path. Without this, first-boot bootstrap
  fails at `dbt-run`.
- Streamlit MUST bind `0.0.0.0:8501` (Fly routes external traffic to the
  container's exposed port; default Streamlit binds to `localhost` only).
- Health check target: Streamlit's built-in `/_stcore/health` endpoint on
  port 8501.

---

## Task 1: Dockerfile and entrypoint script

**Files:**
- Create: `Dockerfile`
- Create: `entrypoint.sh`
- Create: `.dockerignore`
- Test: manual Docker build + run (no warehouse present) verified locally;
  no pytest coverage applies (infrastructure files, not Python code)

**Interfaces:**
- Consumes: `pyproject.toml` / `uv.lock` (already committed, verified in
  sync via `uv lock --check` this session), `Makefile`'s `pipeline` target,
  `dbt_clinical_trials/profiles.yml.example`, `.streamlit/config.toml`
  (dark theme + `gatherUsageStats = false` — must be copied into the image
  or the deployed dashboard falls back to Streamlit's default light theme,
  a visible regression from what this session verified in the browser).
- Produces: a Docker image whose `ENTRYPOINT` is `/app/entrypoint.sh`,
  which Task 2 (`fly.toml`) references via `EXPOSE 8501` and the health
  check path.

- [ ] **Step 1: Write `.dockerignore`**

```gitignore
.venv/
.git/
.env
.env.*
data/
.pytest_cache/
.ruff_cache/
__pycache__/
*.pyc
dbt_clinical_trials/target/
dbt_clinical_trials/logs/
dbt_clinical_trials/profiles.yml
.superpowers/
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates make \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY dbt_clinical_trials/ dbt_clinical_trials/
COPY src/ src/
COPY dashboard/ dashboard/
COPY config/ config/
COPY tests/ tests/
COPY .streamlit/ .streamlit/
COPY Makefile README.md ./

RUN uv sync --all-groups --frozen
RUN uv run dbt deps --project-dir dbt_clinical_trials --profiles-dir dbt_clinical_trials
RUN test -f dbt_clinical_trials/profiles.yml || cp dbt_clinical_trials/profiles.yml.example dbt_clinical_trials/profiles.yml
RUN mkdir -p data/bronze/api_responses data/bronze/manifests data/silver data/gold data/warehouse

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8501

ENTRYPOINT ["/app/entrypoint.sh"]
```

- [ ] **Step 3: Write `entrypoint.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="/app/data"
WAREHOUSE="$DATA_DIR/warehouse/clinical_trials.duckdb"
MARKER="$DATA_DIR/.last_pipeline_run"
LOG_DIR="$DATA_DIR/logs"
REFRESH_INTERVAL_SECONDS=604800   # 7 days
CHECK_INTERVAL_SECONDS=3600       # 1 hour

mkdir -p "$LOG_DIR"

# DuckDB does not create parent directories for a new database file (verified:
# duckdb.connect() raises IOException on a missing directory), and a Fly
# Volume mounts as EMPTY on its very first boot, shadowing whatever the
# Dockerfile baked into the image at this path. Recreate the full tree on
# every boot (idempotent, cheap) so `make pipeline` never fails here.
mkdir -p "$DATA_DIR/bronze/api_responses" "$DATA_DIR/bronze/manifests" \
    "$DATA_DIR/silver" "$DATA_DIR/gold" "$DATA_DIR/warehouse"

run_pipeline() {
    echo "[entrypoint] $(date -u +%FT%TZ) starting make pipeline" >> "$LOG_DIR/pipeline.log"
    if make pipeline >> "$LOG_DIR/pipeline.log" 2>&1; then
        date +%s > "$MARKER"
        echo "[entrypoint] $(date -u +%FT%TZ) pipeline succeeded" >> "$LOG_DIR/pipeline.log"
        return 0
    else
        echo "[entrypoint] $(date -u +%FT%TZ) pipeline FAILED (marker not updated, will retry)" >> "$LOG_DIR/pipeline.log"
        return 1
    fi
}

# First-boot bootstrap: block startup until the warehouse exists at least once,
# so the dashboard never shows "warehouse not found" on a fresh volume.
if [ ! -f "$WAREHOUSE" ]; then
    echo "[entrypoint] no warehouse found, running first-boot pipeline" >> "$LOG_DIR/pipeline.log"
    run_pipeline || echo "[entrypoint] first-boot pipeline failed; dashboard will show 'warehouse not found' until the next successful refresh" >> "$LOG_DIR/pipeline.log"
fi

# Background weekly refresh loop.
(
    while true; do
        sleep "$CHECK_INTERVAL_SECONDS"
        now=$(date +%s)
        last=0
        if [ -f "$MARKER" ]; then
            last=$(cat "$MARKER")
        fi
        elapsed=$(( now - last ))
        if [ "$elapsed" -ge "$REFRESH_INTERVAL_SECONDS" ]; then
            run_pipeline || true
        fi
    done
) &

exec uv run streamlit run dashboard/app.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true
```

- [ ] **Step 4: Verify the Dockerfile builds locally**

Run: `docker build -t cti-dashboard-test .`
Expected: build completes with exit code 0 (no test harness available for
Dockerfiles; a successful build plus the manual run below is the
verification for this task).

- [ ] **Step 5: Verify the container boots and bootstraps a warehouse**

Run:
```bash
docker run --rm -p 8501:8501 -v cti-test-data:/app/data cti-dashboard-test
```
Expected: logs show `[entrypoint] no warehouse found, running first-boot
pipeline`, followed by the pipeline's own log lines, then Streamlit's
"You can now view your Streamlit app" banner. Visiting
`http://localhost:8501` shows the Overview page with real trial counts
(not a "Warehouse not found" error) rendered in the dark theme (dark
background, blue accent) — confirms `.streamlit/config.toml` made it into
the image. Stop with Ctrl-C; the named volume `cti-test-data` persists the
warehouse for inspection if needed (`docker volume rm cti-test-data` to
clean up after verifying).

- [ ] **Step 6: Commit**

```bash
git add Dockerfile entrypoint.sh .dockerignore
git commit -m "feat(deploy): add Dockerfile and entrypoint for Fly.io"
```

---

## Task 2: `fly.toml`

**Files:**
- Create: `fly.toml`

**Interfaces:**
- Consumes: Task 1's `Dockerfile` (referenced implicitly — `fly.toml`'s
  `[build]` section has no `dockerfile` key when a `Dockerfile` sits at the
  repo root; Fly's default build strategy picks it up automatically) and
  the `EXPOSE 8501` / entrypoint from Task 1.
- Produces: the Fly app configuration Task 3's deploy doc instructs the
  user to run `fly launch --no-deploy` / `fly deploy` against.

- [ ] **Step 1: Write `fly.toml`**

```toml
app = "clinical-trial-intelligence"
primary_region = "iad"

[build]

[env]

[[mounts]]
source = "cti_data"
destination = "/app/data"

[http_service]
internal_port = 8501
force_https = true
auto_stop_machines = "off"
auto_start_machines = false
min_machines_running = 1

[[http_service.checks]]
grace_period = "60s"
interval = "15s"
method = "GET"
timeout = "5s"
path = "/_stcore/health"

[[vm]]
size = "shared-cpu-1x"
memory = "512mb"
```

- [ ] **Step 2: Verify `fly.toml` is valid TOML**

Run: `python3 -c "import tomllib; tomllib.load(open('fly.toml', 'rb'))"`
Expected: no output, exit code 0 (confirms syntactic validity without
requiring the `fly` CLI or an account).

- [ ] **Step 3: Commit**

```bash
git add fly.toml
git commit -m "feat(deploy): add fly.toml for Fly.io app config"
```

---

## Task 3: Deployment docs and README index

**Files:**
- Create: `docs/DEPLOY_FLY.md`
- Modify: `README.md` (documentation index table, §22)

**Interfaces:**
- Consumes: Task 1's `Dockerfile`/`entrypoint.sh` behavior (what the user
  should expect on first boot and on the weekly refresh) and Task 2's
  `fly.toml` (`app = "clinical-trial-intelligence"`, the volume name
  `cti_data`, the mount path `/app/data`).
- Produces: nothing consumed by a later task — this is the final task.

- [ ] **Step 1: Write `docs/DEPLOY_FLY.md`**

```markdown
# Deploy the Streamlit dashboard (Fly.io)

The dashboard reads a local DuckDB warehouse built by the pipeline. Unlike
Streamlit Community Cloud (see `docs/DEPLOY_STREAMLIT.md`), this Fly.io
setup keeps the pipeline running: the container bootstraps the warehouse on
first boot and refreshes it every 7 days on its own, matching this
project's weekly-snapshot design (`config/project_config.yml`'s
`scope.refresh_cadence: weekly`).

## What's already in the repo

- `Dockerfile` — builds the app image (Python 3.12, `uv`, dbt deps).
- `entrypoint.sh` — on container start: runs `make pipeline` once if no
  warehouse exists yet, then backgrounds a loop that reruns it every 7
  days, then serves the dashboard in the foreground.
- `fly.toml` — Fly app config: one always-on machine, one persistent
  volume (`cti_data`) mounted at `/app/data`, health-checked against
  Streamlit's `/_stcore/health` endpoint.

## One-time setup (you run these — they provision billed Fly resources)

```bash
# Install the Fly CLI if you haven't: https://fly.io/docs/flyctl/install/
fly auth login

# Create the app from fly.toml (rename the `app =` line first if
# "clinical-trial-intelligence" is already taken on Fly).
fly launch --no-deploy

# Create the persistent volume fly.toml expects. 1GB comfortably fits the
# warehouse (~20MB today); extend later with `fly volumes extend` if it
# grows across many weekly runs.
fly volumes create cti_data --region iad --size 1

# Deploy.
fly deploy
```

## No secrets required

ClinicalTrials.gov's API v2 is public and unauthenticated — there is
nothing to pass via `fly secrets set`.

## What to expect

- **First boot** takes longer than a normal deploy: the container runs the
  full pipeline (ingest → transform → dbt-run → dbt-test → quality-report)
  before Streamlit starts serving. Watch progress with `fly logs`.
- **Every 7 days**, the same pipeline reruns automatically in the
  background without interrupting the running dashboard. Its output is
  appended to `/app/data/logs/pipeline.log` inside the volume — inspect it
  with `fly ssh console` then `cat /app/data/logs/pipeline.log`.
- **This machine cannot auto-suspend to zero.** `auto_stop_machines` is set
  to `"off"` because the background refresh loop must keep running
  continuously — unlike a typical Fly demo app that scales to zero when
  idle. Expect a small recurring cost (roughly $2-5/month on Fly's
  smallest shared-CPU tier as of this writing), not a free deployment.

## Known caveat: untested against Fly's egress IPs

This project's ingestion client was fixed to use `requests` instead of
`httpx` after discovering ClinicalTrials.gov's bot protection blocks
`httpx`'s TLS/HTTP handshake specifically (confirmed: `curl`, stdlib
`urllib`, and `requests` all succeed with identical requests; only `httpx`
gets a 403). That fix should behave identically from Fly's network, but it
has not been verified from an actual Fly egress IP. If the first-boot
pipeline run fails with a 403, check `/app/data/logs/pipeline.log` first —
this is the most likely cause.

## Notes

- This app is a **portfolio demonstration**, not clinical decision
  support.
```

- [ ] **Step 2: Add the new docs to the README documentation index**

In `README.md`, find the "## 22. Documentation index" table (currently
ends with the `docs/development_log.md` row). Add two rows — one for the
existing (previously unlisted) `docs/DEPLOY_STREAMLIT.md`, and one for the
new `docs/DEPLOY_FLY.md`:

```markdown
| [`docs/DEPLOY_STREAMLIT.md`](docs/DEPLOY_STREAMLIT.md) | deploy the dashboard to Streamlit Community Cloud |
| [`docs/DEPLOY_FLY.md`](docs/DEPLOY_FLY.md) | deploy the dashboard to Fly.io with an auto-refreshing pipeline |
```

- [ ] **Step 3: Verify the README table still renders as valid Markdown**

Run: `grep -c '^|' README.md`
Expected: a count at least 2 higher than before the edit (confirms the two
new rows were added; exact prior count is whatever `git show HEAD:README.md
| grep -c '^|'` reports before this task's edit).

- [ ] **Step 4: Commit**

```bash
git add docs/DEPLOY_FLY.md README.md
git commit -m "docs: add Fly.io deployment guide, index both deploy docs in README"
```
