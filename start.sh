#!/usr/bin/env bash
# start.sh — Launch the Emerge simulation server + UI in one command.
#
# Usage:
#   ./start.sh [options]
#
# All options are forwarded to the Python server:
#   --agents N       Number of agents (default: 3)
#   --ticks N|infinite  Max ticks (default: infinite)
#   --seed N         World seed
#   --no-llm         Disable LLM, use rule-based fallback
#   --port N         Server port (default: 8001)
#   --tick-delay F   Seconds between ticks
#
# Examples:
#   ./start.sh
#   ./start.sh --no-llm --agents 5 --seed 42
#   ./start.sh --tick-delay 0.2

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$ROOT/UI"
SERVER_PID=""

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[emerge]${RESET} $*"; }
ok()   { echo -e "${GREEN}[emerge]${RESET} $*"; }
warn() { echo -e "${YELLOW}[emerge]${RESET} $*"; }
err()  { echo -e "${RED}[emerge]${RESET} $*" >&2; }

# ── Cleanup on exit ─────────────────────────────────────────────────────────
cleanup() {
  echo ""
  log "Shutting down…"
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null && ok "Server stopped (PID $SERVER_PID)"
  fi
  exit 0
}
trap cleanup INT TERM

# ── Preflight checks ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  Emerge — Life Simulation${RESET}"
echo -e "  ─────────────────────────"
echo ""

# Check uv
if ! command -v uv &>/dev/null; then
  err "uv not found. Install it from https://docs.astral.sh/uv/"
  exit 1
fi

# Check node / npm
if ! command -v npm &>/dev/null; then
  err "npm not found. Install Node.js from https://nodejs.org/"
  exit 1
fi

# Install UI dependencies if node_modules is missing
if [[ ! -d "$UI_DIR/node_modules" ]]; then
  log "Installing UI dependencies…"
  npm --prefix "$UI_DIR" install --silent
  ok "UI dependencies installed"
fi

# ── Start Python server ──────────────────────────────────────────────────────
log "Starting simulation server…  (args: $*)"
uv run python "$ROOT/server/run_server.py" "$@" &
SERVER_PID=$!

# Wait until the server is accepting connections (max 15 s)
log "Waiting for server on port 8001…"
for i in $(seq 1 30); do
  if curl -sf http://localhost:8001/api/health >/dev/null 2>&1; then
    ok "Server ready"
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    err "Server process exited unexpectedly. Check output above."
    exit 1
  fi
  sleep 0.5
done

if ! curl -sf http://localhost:8001/api/health >/dev/null 2>&1; then
  warn "Server didn't respond in time — starting UI anyway"
fi

# ── Start React dev server (foreground) ──────────────────────────────────────
echo ""
ok "Opening UI at http://localhost:5173"
echo -e "  ${CYAN}Press Ctrl+C to stop both processes.${RESET}"
echo ""

npm --prefix "$UI_DIR" run dev
