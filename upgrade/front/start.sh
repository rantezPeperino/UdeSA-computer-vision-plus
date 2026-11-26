#!/usr/bin/env bash
# Starts the web front of scripts/publish_from_csv.py and opens it in the browser.
#
# Usage (from anywhere):
#   bash upgrade/front/start.sh
#   bash upgrade/front/start.sh --port 8080 --no-browser
#
# Then, in the browser, pick a CSV or a folder and start: the front runs
# scripts/publish_from_csv.py once per CSV and shows what it does, live.
#
# What it does:
#   1. Picks a Python: $PYTHON if set, else the active one if it already has the
#      dependencies, else upgrade/front/.venv (created on the first run with the
#      repo's requirements, deep-tagger-api's and the front's; the first time
#      takes several minutes because of torch and paddle).
#   2. Starts the server (upgrade/front/run.py) and opens the browser.
# The script reads its variables from this terminal, as when it runs by hand
# (export ... as in upgrade/MERCHANT_SETUP.md). Ctrl-C stops the server.
set -euo pipefail

FRONT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$FRONT/../.." && pwd)"
VENV="$FRONT/.venv"
HOST=127.0.0.1
PORT=8000
BROWSER=1

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --no-browser) BROWSER=0; shift ;;
    -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1m▸ %s\033[0m\n' "$*"; }

# ── 1. Python with everything the script and the front need ──────────────────
CHECK='import fastapi, uvicorn, multipart, torch, google.shopping.merchant_products_v1'
REQS=("$ROOT/requirements.txt" "$ROOT/deep-tagger-api/requirements.txt" "$FRONT/requirements.txt")

has_deps() { "$1" -c "$CHECK" >/dev/null 2>&1; }

if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
elif command -v python >/dev/null 2>&1 && has_deps python; then
  PY="$(command -v python)"
else
  PY="$VENV/bin/python"
  if [ ! -x "$PY" ]; then
    say "Creating the environment in upgrade/front/.venv (only the first time)"
    python3 -m venv "$VENV"
  fi
  STAMP="$VENV/.requirements.sha"
  SUM="$(cat "${REQS[@]}" | sha256sum | cut -d' ' -f1)"
  if [ "$(cat "$STAMP" 2>/dev/null)" != "$SUM" ] || ! has_deps "$PY"; then
    say "Installing dependencies (the first time takes several minutes: torch, paddle)"
    "$PY" -m pip install --upgrade pip >/dev/null
    for r in "${REQS[@]}"; do "$PY" -m pip install -r "$r"; done
    echo "$SUM" > "$STAMP"
  fi
fi
say "Python: $PY"

# ── 2. Variables of the script (keys, Merchant Center) ───────────────────────
# upgrade/front/.env (ignored by git) keeps them between restarts. Variables
# already exported in the terminal win.
if [ -f "$FRONT/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#export }"
    case "$line" in ''|\#*) continue ;; esac
    key="${line%%=*}"; value="${line#*=}"
    value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
    value="${value/#\~/$HOME}"
    if [ -z "${!key:-}" ]; then export "$key=$value"; fi
  done < "$FRONT/.env"
  say "Variables loaded from upgrade/front/.env"
fi

# ── 3. Server and browser ────────────────────────────────────────────────────
URL="http://$HOST:$PORT"
cd "$ROOT"
# Waits in the background for the server to answer, then opens the browser.
# The server runs in the foreground so that Ctrl-C reaches it.
(
  for _ in $(seq 120); do
    if "$PY" -c "import urllib.request; urllib.request.urlopen('$URL/api/runs/current', timeout=1)" 2>/dev/null; then
      say "Front ready at $URL  (Ctrl-C to stop)"
      if [ "$BROWSER" = 1 ]; then (xdg-open "$URL" || open "$URL") >/dev/null 2>&1 || true; fi
      exit 0
    fi
    sleep 0.5
  done
) &
exec "$PY" "$FRONT/run.py" --host "$HOST" --port "$PORT"
