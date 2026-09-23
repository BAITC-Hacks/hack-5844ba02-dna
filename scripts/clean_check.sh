#!/usr/bin/env bash
set -Eeuo pipefail

started=$(date +%s)
tmp=$(mktemp -d)
server_pid=""
cleanup() {
  if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; fi
  rm -rf "$tmp"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

git clone --quiet --local . "$tmp/repo"
cd "$tmp/repo"
python3 -m venv .venv
.venv/bin/python3 -m pip install --quiet --upgrade pip
.venv/bin/python3 -m pip install --quiet -r requirements.txt
make pipeline
for file in nodes_roles.csv clusters.csv top_nodes.csv; do
  [[ -f "out/$file" ]] || fail "missing out/$file"
done
.venv/bin/python3 -m uvicorn api.main:app --host 127.0.0.1 --port 18000 >/tmp/money-graph-clean-check.log 2>&1 &
server_pid=$!
for _ in $(seq 1 30); do
  if curl --silent --fail http://127.0.0.1:18000/api/health >/tmp/money-graph-health.json; then break; fi
  sleep 1
done
grep -q '"status":"ok"' /tmp/money-graph-health.json || fail "health check failed"
elapsed=$(( $(date +%s) - started ))
echo "elapsed_seconds=$elapsed"
