#!/usr/bin/env bash
# =============================================================================
# ISRO SDN Testbed — Phase 1: Controller Launcher
# =============================================================================
# ALWAYS use this script to start Ryu — never call python3 isro_controller.py
# directly, as ryu-manager must be the entry point for correct eventlet patching.
#
# Usage:
#   bash ~/isro-sdn-testbed/start_controller.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_FILE="$SCRIPT_DIR/isro_controller.py"
RYU_ENV="$HOME/ryu_env"
OF_HOST="0.0.0.0"
OF_PORT=6653
RYU_CONF="$HOME/ryu.conf"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fatal() { echo -e "${RED}[FATAL]${NC} $*"; exit 1; }

# ── Sanity checks ─────────────────────────────────────────────────────────────
[ -f "$CONTROLLER_FILE" ] || fatal "Cannot find $CONTROLLER_FILE"
[ -d "$RYU_ENV"         ] || fatal "ryu_env not found at $RYU_ENV"

# ── CRITICAL: Disable stale ryu.conf from Phase 2 SSL experiments ─────────────
# ~/ryu.conf is auto-loaded by oslo.config and injects SSL cert paths
# that cause Ryu to enter SSL mode and crash silently (no port binding).
if [ -f "$RYU_CONF" ]; then
    warn "Found $RYU_CONF — backing it up to ${RYU_CONF}.phase2_backup"
    warn "This file contained Phase 2 SSL settings that prevent Phase 1 from working."
    mv "$RYU_CONF" "${RYU_CONF}.phase2_backup"
    info "Backup complete. Remove the backup before starting Phase 2."
fi

# ── Activate virtual environment ──────────────────────────────────────────────
info "Activating virtual environment: $RYU_ENV"
# shellcheck disable=SC1091
source "$RYU_ENV/bin/activate"

RYU_BIN="$(command -v ryu-manager)" \
    || fatal "'ryu-manager' not found in $RYU_ENV"
info "ryu-manager: $RYU_BIN"

# ── Free port 6653 if occupied ────────────────────────────────────────────────
if ss -tlnp 2>/dev/null | grep -q ":${OF_PORT}"; then
    warn "Port $OF_PORT is in use — killing occupant."
    sudo fuser -k "${OF_PORT}/tcp" 2>/dev/null || true
    sleep 1
fi

if ss -tlnp 2>/dev/null | grep -q ":${OF_PORT}"; then
    fatal "Port $OF_PORT is STILL in use. Run:  sudo fuser -k ${OF_PORT}/tcp"
fi
info "Port $OF_PORT is free."

# ── Launch Ryu ────────────────────────────────────────────────────────────────
info "Starting Ryu controller — binding to ${OF_HOST}:${OF_PORT} ..."
echo ""
echo "  Watch for:  LISTEN  0  ...  0.0.0.0:6653"
echo "  Verify with (new terminal):  sudo ss -tlnp | grep 6653"
echo ""

exec ryu-manager \
    --ofp-listen-host     "$OF_HOST" \
    --ofp-tcp-listen-port "$OF_PORT" \
    --verbose \
    "$CONTROLLER_FILE"
