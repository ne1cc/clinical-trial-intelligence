# Deploy the Streamlit dashboard (Fly.io)

**Live:** this project's own deployment runs at
[cti-dashboard.fly.dev](https://cti-dashboard.fly.dev/).

The dashboard reads a local DuckDB warehouse built by the pipeline. Unlike
Streamlit Community Cloud (see `docs/DEPLOY_STREAMLIT.md`), this Fly.io
setup keeps the pipeline running: the container bootstraps the warehouse on
first boot and then attempts to refresh it every 7 days on its own, matching
this project's weekly-snapshot design (`config/project_config.yml`'s
`scope.refresh_cadence: weekly`). The scheduled refresh has a known failure
mode while the dashboard is serving traffic — read "Known issue" below
before relying on it.

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

# Create the app from fly.toml (app = "cti-dashboard"; rename that line
# first if the name is already taken on Fly).
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
  Verified locally and on Fly: this takes roughly 30-45 seconds end to end
  (2,618 trials, 32 dbt models, 114 dbt tests).
- **Every 7 days**, the same pipeline reruns in the background. Its output is
  appended to `/app/data/logs/pipeline.log` inside the volume — inspect it
  with `fly ssh console` then `cat /app/data/logs/pipeline.log`. On the live
  app the first-boot bootstrap succeeded and every later scheduled attempt
  has failed; read "Known issue" below before assuming the warehouse is
  fresh.
- **This machine cannot auto-suspend to zero.** `auto_stop_machines` is set
  to `"off"` because the background refresh loop must keep running
  continuously — unlike a typical Fly demo app that scales to zero when
  idle. Expect a small recurring cost (roughly $2-5/month on Fly's
  smallest shared-CPU tier as of this writing), not a free deployment.

## Known issue: the scheduled refresh loses the DuckDB lock

The in-container refresh is unresolved as of 2026-09-05. On the live app, the
first-boot bootstrap run succeeded and the next nine scheduled attempts all
failed at the `dbt-seed` step with:

```
_duckdb.IOException: IO Error: Could not set lock on file
"/app/data/warehouse/clinical_trials.duckdb": Conflicting lock is held in
/usr/local/bin/python3.12 (PID 672)
```

PID 672 is the dashboard: `dashboard/components/data.py` caches a read-only
DuckDB connection with `@st.cache_resource`, so it stays open for the whole
life of the Streamlit process. DuckDB lets a database file be opened by one
read-write connection *or* by read-only connections, never both, so a
pipeline run started while the dashboard is serving cannot become a writer.
Because `entrypoint.sh` only advances `.last_pipeline_run` on success, the
failures arrived at the loop's one-hour check interval — consistent with each
failed attempt being retried an hour later and failing identically. One thing
the log does *not* explain: the first failure at 10:19Z came roughly 7.7 hours
after the successful 02:36Z bootstrap, well short of the committed 7-day
threshold, so the loop's arithmetic in the deployed image does not match the
`entrypoint.sh` in this branch. Worth reconciling before trusting the refresh
cadence at all.

Practical consequence: treat the deployed warehouse's freshness as
unverified. The failure only occurs while something holds the warehouse open.
Two later runs on the live machine (19:19Z and 19:55Z) completed green with
all 114 dbt tests passing; neither carries an `[entrypoint]` marker line, so
both were started by hand, and they succeeded because the just-restarted
Streamlit process had not opened the warehouse yet. The scheduled loop is the
case that reliably does not.

## Egress from Fly is verified

ClinicalTrials.gov's bot protection blocks `httpx`'s TLS/HTTP handshake
specifically — `curl`, stdlib `urllib`, and `requests` all succeed with
identical requests while `httpx` gets a 403 — which is why this project's
ingestion client uses `requests`. That fix now holds from a real Fly egress
IP: the container's run `20260905T191901Z_77632421` reported
`status=success pages=27 records=2618 quarantined=0` with no 403.

## Notes

- This app is a **portfolio demonstration**, not clinical decision
  support.
