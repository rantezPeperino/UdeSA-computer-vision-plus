#!/usr/bin/env bash
# Stops the web front started with upgrade/front/start.sh.
#
# Usage (from anywhere):
#   bash upgrade/front/stop.sh              # stops every front of this repo
#   bash upgrade/front/stop.sh --port 8080  # only the one on that port
#
# A run in progress is cut as with Ctrl-C: the script writes the rows already
# processed to its results file before the server exits.
set -euo pipefail

FRONT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

# The servers of this front: processes running upgrade/front/run.py.
pids=()
for pid in $(pgrep -f -- "$FRONT/run.py" || true); do
  [ "$pid" = "$$" ] && continue
  args="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$args" in *"$FRONT/run.py"*) ;; *) continue ;; esac
  if [ -n "$PORT" ]; then
    case "$args" in *"--port $PORT "*) ;; *) continue ;; esac
  fi
  pids+=("$pid")
done

if [ ${#pids[@]} -eq 0 ]; then
  echo "No front running${PORT:+ on port $PORT}."
  exit 0
fi

# Interrupt a run in progress first, as the button "Interrumpir" does, so the
# script saves the rows already processed.
for pid in "${pids[@]}"; do
  args="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  port="$(sed -n 's/.*--port \([0-9]*\).*/\1/p' <<<"$args")"
  host="$(sed -n 's/.*--host \([^ ]*\).*/\1/p' <<<"$args")"
  url="http://${host:-127.0.0.1}:${port:-8000}"
  current="$(curl -s --max-time 2 "$url/api/runs/current" || true)"
  if grep -q '"running": *true' <<<"$current"; then
    id="$(sed -n 's/.*"run_id": *"\([^"]*\)".*/\1/p' <<<"$current")"
    echo "Interrupting the run in progress ($id) on $url…"
    curl -s --max-time 2 -X POST "$url/api/runs/$id/interrupt" >/dev/null || true
    for _ in $(seq 20); do
      curl -s --max-time 2 "$url/api/runs/current" | grep -q '"running": *true' || break
      sleep 0.5
    done
  fi
done

echo "Stopping the front (PID ${pids[*]})…"
kill -TERM "${pids[@]}" 2>/dev/null || true
for _ in $(seq 20); do
  alive=0
  for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1; done
  [ $alive = 0 ] && break
  sleep 0.5
done
for pid in "${pids[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid" 2>/dev/null || true; fi
done
echo "Front stopped."
