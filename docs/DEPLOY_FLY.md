# Deploy the Streamlit dashboard (Fly.io)

**Live:** this project's own deployment runs at
[cti-dashboard.fly.dev](https://cti-dashboard.fly.dev/).

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
  Verified locally: this takes roughly 30-45 seconds end to end (2,618
  trials, 30 dbt models, 73 dbt tests).
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
gets a 403). That fix was re-verified inside this project's own Docker
container (a different network path than a bare local run), succeeding
identically. It has not been verified from an actual Fly egress IP — if
the first-boot pipeline run fails with a 403, check
`/app/data/logs/pipeline.log` first; this would be the most likely cause.

## Notes

- This app is a **portfolio demonstration**, not clinical decision
  support.
