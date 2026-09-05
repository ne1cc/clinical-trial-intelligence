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
