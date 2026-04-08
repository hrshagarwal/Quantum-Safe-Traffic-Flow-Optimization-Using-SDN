#!/usr/bin/env bash
# =============================================================================
# ISRO SDN Testbed — Phase 2: TLS Controller Launcher
# =============================================================================
# Starts the Ryu controller with mutual TLS (mTLS) using the PKI created by
# pki/generate_pki.sh.  The OpenFlow channel between Ryu and OVS switches is
# encrypted end-to-end — no plaintext OF traffic on port 6653.
#
# Prerequisites:
#   1. PKI must already exist:  bash ~/isro-sdn-testbed/pki/generate_pki.sh
#   2. Mininet must be stopped (run this first, then isro_topo_tls.py)
#   3. ~/ryu.conf must NOT exist (this script checks and aborts if it does)
#
# Usage:
#   bash ~/isro-sdn-testbed/start_controller_tls.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_FILE="$SCRIPT_DIR/isro_controller.py"
RYU_ENV="$HOME/ryu_env"
PKI_DIR="$SCRIPT_DIR/pki"

# ── Certificate paths ─────────────────────────────────────────────────────────
CA_CERT="$PKI_DIR/ca/ca.crt"
CTL_CERT="$PKI_DIR/controller/controller.crt"
CTL_KEY="$PKI_DIR/controller/controller.key"

# ── Network settings ──────────────────────────────────────────────────────────
OF_HOST="0.0.0.0"
OF_PORT=6653          # Ryu uses 6653 for both TCP and SSL by default

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[TLS-CTL]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[TLS-CTL]${NC}  $*"; }
fatal() { echo -e "${RED}[TLS-CTL]${NC}  $*"; exit 1; }
step()  { echo -e "${CYAN}[TLS-CTL]${NC}  $*"; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  ISRO SDN Testbed — Phase 2: TLS-Secured Ryu Controller${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ── Sanity checks ─────────────────────────────────────────────────────────────
step "Running pre-flight checks …"

[ -f "$CONTROLLER_FILE" ] || fatal "Controller not found: $CONTROLLER_FILE"
[ -d "$RYU_ENV"         ] || fatal "ryu_env not found at $RYU_ENV"

# CRITICAL: ryu.conf auto-loaded by oslo.config causes cert path conflicts.
# This script manages SSL flags explicitly via CLI — ryu.conf must not exist.
if [ -f "$HOME/ryu.conf" ]; then
    fatal "Found ~/ryu.conf — this file conflicts with explicit TLS flags.
       Remove it first:  rm ~/ryu.conf
       (or rename it: mv ~/ryu.conf ~/ryu.conf.bak)"
fi

# Verify all certificate files exist
for f in "$CA_CERT" "$CTL_CERT" "$CTL_KEY"; do
    [ -f "$f" ] || fatal "Certificate file not found: $f
       Run first:  bash $PKI_DIR/generate_pki.sh"
done
info "  ✔ All certificate files present"

# Verify cert chain integrity
openssl verify -CAfile "$CA_CERT" "$CTL_CERT" > /dev/null 2>&1 \
    || fatal "Controller certificate fails CA verification! Regenerate PKI."
info "  ✔ Controller certificate chain is valid"

# ── Activate virtual environment ──────────────────────────────────────────────
step "Activating virtual environment: $RYU_ENV"
# shellcheck disable=SC1091
source "$RYU_ENV/bin/activate"

RYU_BIN="$(command -v ryu-manager)" \
    || fatal "'ryu-manager' not found in $RYU_ENV"
info "  ryu-manager: $RYU_BIN"

# ── Free port if occupied ─────────────────────────────────────────────────────
if ss -tlnp 2>/dev/null | grep -q ":${OF_PORT}"; then
    warn "Port $OF_PORT is in use — killing occupant."
    sudo fuser -k "${OF_PORT}/tcp" 2>/dev/null || true
    sleep 1
fi
if ss -tlnp 2>/dev/null | grep -q ":${OF_PORT}"; then
    fatal "Port $OF_PORT is STILL in use. Run:  sudo fuser -k ${OF_PORT}/tcp"
fi
info "  ✔ Port $OF_PORT is free"

# ── Print cert summary ────────────────────────────────────────────────────────
echo ""
echo "  CA Certificate  : $CA_CERT"
echo "  Controller Cert : $CTL_CERT"
echo "  Controller Key  : $CTL_KEY"
echo "  Listening on    : $OF_HOST:$OF_PORT (SSL)"
echo ""
info "  ✔ TLS mutual-authentication: Ryu will accept ONLY switches with certs signed by the CA"
echo ""

# ── Launch Ryu with TLS ───────────────────────────────────────────────────────
step "Launching Ryu controller with TLS …"
echo ""
echo "   Watch for:  'LISTEN  0  ...  0.0.0.0:6653'  in the output"
echo "   Ctrl+C to stop."
echo ""

exec ryu-manager \
    --ofp-listen-host     "$OF_HOST" \
    --ofp-ssl-listen-port "$OF_PORT" \
    --ctl-privkey  "$CTL_KEY" \
    --ctl-cert     "$CTL_CERT" \
    --ca-certs     "$CA_CERT" \
    --verbose \
    "$CONTROLLER_FILE"
