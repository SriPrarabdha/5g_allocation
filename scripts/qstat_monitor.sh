#!/bin/bash
# qstat-based PBS job monitor (this cluster uses PBS Pro, not Slurm).
#
# Usage:
#   bash scripts/qstat_monitor.sh             # watch all of your jobs
#   bash scripts/qstat_monitor.sh <jobid>     # watch one job in detail
#   INTERVAL=5 bash scripts/qstat_monitor.sh  # change refresh seconds
#
# Ctrl-C to stop.

JOBID="${1:-}"
INTERVAL="${INTERVAL:-10}"
USER_NAME="${USER:-$(whoami)}"

while true; do
    clear
    date
    if [ -n "$JOBID" ]; then
        echo "== qstat -f $JOBID (refresh ${INTERVAL}s) =="
        qstat -f "$JOBID" 2>&1 | grep -E \
            'Job_Name|job_state|resources_used|exec_host|comment|Exit_status|queue' \
            || echo "Job $JOBID not found (finished? check logs/)."
    else
        echo "== qstat -u $USER_NAME (refresh ${INTERVAL}s) =="
        qstat -u "$USER_NAME" 2>&1 || echo "qstat failed."
    fi
    sleep "$INTERVAL"
done
