# Deploy the Streamlit dashboard (Fly.io)

**Live:** this project's own deployment runs at
[cti-dashboard.fly.dev](https://cti-dashboard.fly.dev/).

The dashboard reads a local DuckDB warehouse built by the pipeline. Unlike
Streamlit Community Cloud (see `docs/DEPLOY_STREAMLIT.md`), this Fly.io
setup keeps the pipeline running: the container bootstraps the warehouse on
first boot and then refreshes it every 7 days on its own, matching this
project's weekly-snapshot design (`config/project_config.yml`'s
`scope.refresh_cadence: weekly`). A refresh briefly stops the dashboard,
because DuckDB will not let a writer run while a reader holds the file — see
"What the first week in production caught" for the failure that forced this
shape.

## What's already in the repo

- `Dockerfile` — builds the app image (Python 3.12, `uv`, dbt deps).
- `entrypoint.sh` — a supervisor, not just a launcher: it runs `make pipeline`
  once if no warehouse exists yet, then owns the Streamlit child process and,
  on schedule, stops that process, reruns the pipeline, and starts it again.
- `fly.toml` — Fly app config: one always-on machine, one persistent
  volume (`cti_data`) mounted at `/app/data`, health-checked against
  Streamlit's `/_stcore/health` endpoint, and `kill_timeout = '90s'` so a
  deploy that lands during a refresh lets the pipeline finish rather than
  killing it mid-write.

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
  Measured on the live app: 59 seconds from `starting make pipeline` to
  `pipeline succeeded` (2026-09-05T02:35:56Z → 02:36:55Z), which includes a
  real 27-page download from ClinicalTrials.gov.
- **Every 7 days**, the entrypoint pauses the dashboard, reruns the pipeline,
  and resumes serving. The outage is exactly as long as a pipeline run: 19
  seconds measured locally on 2026-09-05 over a reused ingestion run
  (3,037 trials, 32 dbt models, 115 dbt tests — counts as of that date, they
  drift with the catalogue and with `dbt_clinical_trials/models/`). It has to
  pause: DuckDB takes one writer *or* readers, and the dashboard caches its
  read-only connection for the life of the process. While paused, Fly's proxy
  stops routing to the machine, but nothing restarts: the machine's
  `restart` policy is `on-failure`, which keys off the entrypoint process's
  exit code, and the supervisor stays PID 1 through the whole refresh.
  Output is appended to `/app/data/logs/pipeline.log` on the volume, and every
  cadence tick logs its inputs (`refresh check: now=… last=… elapsed=…s
  interval=…s`), so a skipped refresh is visible in the log rather than merely
  absent. Both intervals are tunable via `CTI_REFRESH_INTERVAL_SECONDS` and
  `CTI_REFRESH_CHECK_SECONDS`.
- **This machine cannot auto-suspend to zero.** `auto_stop_machines` is set
  to `"off"` because the background refresh loop must keep running
  continuously — unlike a typical Fly demo app that scales to zero when
  idle. Expect a small recurring cost (roughly $2-5/month on Fly's
  smallest shared-CPU tier as of this writing), not a free deployment.

## What the first week in production caught

The original design — refresh in the background while the dashboard keeps
serving — did not work, and nothing in the deployment looked broken while it
was failing. Two independent defects, both fixed on this branch:

**1. The refresh could never get the DuckDB write lock.** Nine consecutive
scheduled attempts (10:19Z through 18:21Z on 2026-09-05) died at `dbt-seed`:

```
_duckdb.IOException: IO Error: Could not set lock on file
"/app/data/warehouse/clinical_trials.duckdb": Conflicting lock is held in
/usr/local/bin/python3.12 (PID 672)
```

PID 672 was the dashboard: `dashboard/components/data.py` caches a read-only
DuckDB connection with `@st.cache_resource` for the lifetime of the Streamlit
process, and DuckDB permits one read-write connection *or* read-only ones,
never both. Serving had to stop for the writer to run, which is what the
pause-and-resume bullet above describes. `entrypoint.sh` in the running
container was byte-identical to the committed copy (md5
`ccc84f88a22bbe1105884dcb8487a2ae`), so this was not a stale-image artefact.

**2. Even a fully green pipeline run could refresh no data.** `make ingest`
defaults `--profile` to `default`, which resolves through the registry to the
`adrd` profile and writes `data/bronze/adrd/manifests/`. `make transform` takes
no profile at all and reads the global config's legacy
`data/bronze/manifests/`. Reproduced locally on 2026-09-05 in a clean worktree,
where it fails silently:

```
Run 20260905T203954Z_89f2b958 finished: status=success pages=31 records=3037
uv run python -m src.cli transform
No runs to transform (0 manifests inspected).
```

Fourteen seconds after that run started, transform was looking at an
empty directory, and dbt and the quality gate went on to pass against silver
the run had never touched. The live volume shows the same
divorce: `data/bronze/manifests/` holds the 02:36Z bootstrap's manifest while
`data/bronze/adrd/manifests/` holds the 19:19Z run's. Fixed by pointing the
default config's bronze paths at the adrd profile, with tests pinning that the
default config, the adrd profile, and dbt's `ingestion_manifests` source all
name the same directory.

What the log cannot settle: the loop's first attempt came at 10:19:47Z, 7.7
hours after the 02:36:55Z bootstrap, and then retried hourly. Firing at all
requires `elapsed >= 604800`, which means `.last_pipeline_run` was missing or
ancient by 10:19Z — a healthy marker would have made the loop skip silently for
six more days. But the same day's log also holds three pipeline runs (09:07Z,
19:19Z, 19:55Z) with no `[entrypoint]` prefix, started from outside the loop,
and the marker now on the volume carries a 20:02:42Z timestamp that matches no
`[entrypoint]` line at all. That day's `pipeline.log` therefore mixes
loop-driven runs with manually driven ones, so it cannot settle the 10:19Z
trigger. The per-tick `refresh check:` line added here is what makes the next
occurrence answerable.

## Egress from Fly is verified

ClinicalTrials.gov's bot protection blocks `httpx`'s TLS/HTTP handshake
specifically — `curl`, stdlib `urllib`, and `requests` all succeed with
identical requests while `httpx` gets a 403 — which is why this project's
ingestion client uses `requests`. That fix now holds from a real Fly egress
IP: the container's run `20260905T191901Z_77632421` reported
`status=success pages=27 records=2618 quarantined=0` with no 403.

## Notes

- **The refresh covers one indication.** `make ingest` sends the Makefile's
  default `CONDITION` (`Alzheimer Disease`, which is the `adrd` profile). Other
  profiles' bronze trees are untouched by a scheduled run. Widening it is not
  just a loop change: silver, gold and the DuckDB warehouse are shared across
  profiles and the dashboard has no indication filter, so a second profile
  added to the refresh would land its trials in the same `dim_trial` and be
  indistinguishable in the UI. Per-indication dashboard scoping has to come
  first.
- This app is a **portfolio demonstration**, not clinical decision
  support.
