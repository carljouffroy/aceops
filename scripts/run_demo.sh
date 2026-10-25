#!/usr/bin/env bash
# Start intake, the board, and the live BRD loop, then run the client agent.
# DEMO_MODE=scripted rehearses without a model. Any other mode uses LLM_BASE_URL
# and stops if that server cannot be reached.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PIDFILE="$ROOT/data/demo.pids"
LOG_DIR="$ROOT/data/logs"
OUT_DIR="$ROOT/data/out"

stop_demo() {
  if [[ ! -f "$PIDFILE" ]]; then
    return 0
  fi
  while read -r pid; do
    if [[ -n "${pid}" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done < "$PIDFILE"
  sleep 0.4
  while read -r pid; do
    if [[ -n "${pid}" ]]; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done < "$PIDFILE"
  rm -f "$PIDFILE"
}

if [[ "${1:-}" == "stop" ]]; then
  stop_demo
  echo "demo stopped"
  exit 0
fi

load_env() {
  if [[ ! -f "$ROOT/.env" ]]; then
    echo "No .env in $ROOT. Copy .env.example and set ADMIN_TOKEN." >&2
    exit 1
  fi
  eval "$("$PY" - <<'PY'
import shlex
from pathlib import Path
for raw in Path(".env").read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        continue
    print(f"export {key}={shlex.quote(value.strip())}")
PY
)"
}

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
load_env

: "${ADMIN_TOKEN:?ADMIN_TOKEN is required}"
PUBLIC_PORT="${PUBLIC_PORT:-8787}"
ADMIN_PORT="${ADMIN_PORT:-8788}"
INTAKE_ADMIN_URL="${INTAKE_ADMIN_URL:-http://127.0.0.1:${ADMIN_PORT}}"
export INTAKE_ADMIN_URL
MCP_URL="http://127.0.0.1:${PUBLIC_PORT}/mcp"
BOARD_URL="http://127.0.0.1:8790"

port_open() {
  "$PY" -c 'import socket,sys; s=socket.socket(); s.settimeout(0.3); rc=s.connect_ex(("127.0.0.1", int(sys.argv[1]))); s.close(); raise SystemExit(0 if rc==0 else 1)' "$1"
}

stop_demo
mkdir -p "$LOG_DIR" "$OUT_DIR"
rm -f "$OUT_DIR/brd.md" "$OUT_DIR/work_items.json" "$OUT_DIR/progress.json" \
  "$OUT_DIR/client.json" "$OUT_DIR/overrides.json"

for port in "$PUBLIC_PORT" "$ADMIN_PORT" 8790; do
  if port_open "$port"; then
    echo "port $port is already in use. Run: make demo-stop" >&2
    exit 1
  fi
done

start_bg() {
  local name="$1"
  shift
  # New session so the servers keep running after this script exits.
  "$PY" -c '
import os, sys
log = open(sys.argv[1], "w", encoding="utf-8", buffering=1)
os.dup2(log.fileno(), 1)
os.dup2(log.fileno(), 2)
os.setsid()
os.execvp(sys.argv[2], sys.argv[2:])
' "$LOG_DIR/${name}.log" "$@" &
  echo $! >> "$PIDFILE"
  echo "$name pid $!"
}

: > "$PIDFILE"
start_bg intake "$PY" -m intake.main
start_bg board "$PY" -m board

wait_http() {
  local url="$1"
  "$PY" - "$url" <<'PY'
import sys, time, urllib.request
url = sys.argv[1]
deadline = time.time() + 25
last = "not up"
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            if 200 <= response.status < 500:
                raise SystemExit(0)
            last = f"HTTP {response.status}"
    except Exception as exc:
        last = str(exc)
    time.sleep(0.2)
print(f"timed out waiting for {url}: {last}", file=sys.stderr)
raise SystemExit(1)
PY
}

wait_http "${INTAKE_ADMIN_URL}/openapi.json"
wait_http "${BOARD_URL}/"

token_file="$(mktemp "$ROOT/data/.invitation.XXXXXX")"
chmod 600 "$token_file"
cleanup_token() { rm -f "$token_file"; }
trap cleanup_token EXIT

client_id="$(DEMO_TOKEN_FILE="$token_file" "$PY" - <<'PY'
import json, os, urllib.request
from pathlib import Path
admin = os.environ["INTAKE_ADMIN_URL"].rstrip("/")
request = urllib.request.Request(
    admin + "/admin/clients",
    data=b"",
    method="POST",
    headers={
        "Authorization": f"Bearer {os.environ['ADMIN_TOKEN']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    },
)
with urllib.request.urlopen(request, timeout=10) as response:
    body = json.loads(response.read().decode("utf-8"))
out = Path("data/out")
out.mkdir(parents=True, exist_ok=True)
(out / "client.json").write_text(json.dumps({"id": body["id"]}) + "\n", encoding="utf-8")
Path(os.environ["DEMO_TOKEN_FILE"]).write_text(body["invitation_token"], encoding="utf-8")
print(body["id"])
PY
)"
TOKEN="$(cat "$token_file")"
rm -f "$token_file"
trap - EXIT
echo "intake client ${client_id}"

start_bg internal "$PY" -m internal.run --live

ready=0
for _ in $(seq 1 50); do
  if grep -q "mode: live" "$LOG_DIR/internal.log" 2>/dev/null; then
    ready=1
    break
  fi
  if grep -q "mode: offline" "$LOG_DIR/internal.log" 2>/dev/null; then
    echo "internal switched away from live. See data/logs/internal.log" >&2
    exit 1
  fi
  sleep 0.2
done
if [[ "$ready" -ne 1 ]]; then
  echo "internal.run --live did not report mode: live" >&2
  exit 1
fi

set +e
"$PY" -m intake.client_agent --url "$MCP_URL" --token "$TOKEN" | tee "$LOG_DIR/client.log"
client_status=${PIPESTATUS[0]}
set -e
unset TOKEN
if [[ "$client_status" -ne 0 ]]; then
  echo "client agent failed (exit ${client_status}) and did not switch to a scripted fallback." >&2
  exit "$client_status"
fi

mode="$(grep -E '^mode: ' "$LOG_DIR/client.log" | tail -1 | awk '{print $2}')"
if [[ "$mode" != "llm" && "$mode" != "scripted" ]]; then
  echo "client finished without printing mode: llm or mode: scripted" >&2
  exit 1
fi
echo "client mode: ${mode}"

"$PY" - "$BOARD_URL" <<'PY'
import json, sys, time, urllib.request
from pathlib import Path

board_url = sys.argv[1]
out = Path("data/out")
names = ("brd.md", "work_items.json", "progress.json")
deadline = time.time() + 20
progress = None
while time.time() < deadline:
    path = out / "progress.json"
    if path.is_file() and all((out / name).is_file() for name in names):
        progress = json.loads(path.read_text(encoding="utf-8"))
        if int(progress.get("answered", -1)) == int(progress.get("total", -2)):
            break
    time.sleep(0.5)
else:
    if progress is None:
        raise SystemExit("data/out never received brd.md, work_items.json, and progress.json")

with urllib.request.urlopen(board_url + "/api/board", timeout=5) as response:
    board = json.loads(response.read().decode("utf-8"))

file_gate = bool(progress["priority_gate"]["done"])
board_progress = board["progress"]
board_items = board.get("items") or []
roles = list(progress["by_role"])
rows = []

def add(metric, file_value, board_value):
    match = "yes" if str(file_value) == str(board_value) else "NO"
    rows.append((metric, str(file_value), str(board_value), match))

for name in names:
    add(name, "yes" if (out / name).is_file() else "no", "yes")
add("answered", progress["answered"], board_progress["answered"])
add("total", progress["total"], board_progress["total"])
add("priority_gate.done", file_gate, board_progress["priority_gate_done"])
for role in roles:
    file_blocked = progress["by_role"][role]["blocked"]
    board_blocked = sum(
        1 for item in board_items if item.get("role") == role and item.get("blocked_on_client")
    )
    add(f"blocked {role}", file_blocked, board_blocked)

width = max(len(row[0]) for row in rows)
print(f"{'metric':<{width}}  file  board  match")
failed = False
for metric, file_value, board_value, match in rows:
    print(f"{metric:<{width}}  {file_value:<4}  {board_value:<5}  {match}")
    if match != "yes":
        failed = True
if int(progress["answered"]) != int(progress["total"]):
    print(
        f"progress is {progress['answered']} / {progress['total']}; expected a finished checklist",
        file=sys.stderr,
    )
    failed = True
if failed:
    raise SystemExit(1)
PY
