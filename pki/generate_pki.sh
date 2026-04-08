#!/usr/bin/env bash
# =============================================================================
# ISRO SDN Testbed — Phase 2: PKI Generation Script
# =============================================================================
# Creates a self-signed CA and issues signed certs for:
#   • The Ryu Controller
#   • The OVS Switches (one shared cert for all switches)
#
# Output layout:
#   pki/ca/         — CA key + self-signed cert
#   pki/controller/ — controller key + CSR + signed cert
#   pki/switch/     — switch key + CSR + signed cert
#
# Usage:
#   bash ~/isro-sdn-testbed/pki/generate_pki.sh
# =============================================================================

set -euo pipefail

PKI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CA_DIR="$PKI_DIR/ca"
CTL_DIR="$PKI_DIR/controller"
SW_DIR="$PKI_DIR/switch"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[PKI]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[PKI]${NC}  $*"; }
fatal() { echo -e "${RED}[PKI]${NC}  $*"; exit 1; }

# ── Safety: abort if certs already exist (prevents accidents) ─────────────────
if [ -f "$CA_DIR/ca.crt" ]; then
    warn "PKI already exists at $PKI_DIR."
    warn "Remove the pki/ directory and re-run to regenerate."
    exit 0
fi

info "=========================================="
info "  ISRO SDN Testbed — Phase 2 PKI Setup"
info "=========================================="

# ── 1. Certificate Authority (CA) ────────────────────────────────────────────
info "Step 1/3: Generating CA key and self-signed certificate …"
openssl genrsa -out "$CA_DIR/ca.key" 2048 2>/dev/null
openssl req -new -x509 -days 3650 \
    -key   "$CA_DIR/ca.key" \
    -out   "$CA_DIR/ca.crt" \
    -subj  "/C=IN/ST=Karnataka/L=Bengaluru/O=ISRO/OU=SDN-Testbed-CA/CN=ISRO-SDN-CA" \
    2>/dev/null
info "  ✔ CA cert: $CA_DIR/ca.crt"

# ── 2. Ryu Controller Certificate ────────────────────────────────────────────
info "Step 2/3: Generating controller key and signed certificate …"
openssl genrsa -out "$CTL_DIR/controller.key" 2048 2>/dev/null
openssl req -new \
    -key  "$CTL_DIR/controller.key" \
    -out  "$CTL_DIR/controller.csr" \
    -subj "/C=IN/ST=Karnataka/L=Bengaluru/O=ISRO/OU=SDN-Controller/CN=ryu-controller" \
    2>/dev/null
openssl x509 -req -days 3650 \
    -in      "$CTL_DIR/controller.csr" \
    -CA      "$CA_DIR/ca.crt" \
    -CAkey   "$CA_DIR/ca.key" \
    -CAcreateserial \
    -out     "$CTL_DIR/controller.crt" \
    2>/dev/null
info "  ✔ Controller cert: $CTL_DIR/controller.crt"

# ── 3. OVS Switch Certificate ─────────────────────────────────────────────────
info "Step 3/3: Generating switch key and signed certificate …"
openssl genrsa -out "$SW_DIR/switch.key" 2048 2>/dev/null
openssl req -new \
    -key  "$SW_DIR/switch.key" \
    -out  "$SW_DIR/switch.csr" \
    -subj "/C=IN/ST=Karnataka/L=Bengaluru/O=ISRO/OU=SDN-Switch/CN=ovs-switch" \
    2>/dev/null
openssl x509 -req -days 3650 \
    -in      "$SW_DIR/switch.csr" \
    -CA      "$CA_DIR/ca.crt" \
    -CAkey   "$CA_DIR/ca.key" \
    -CAcreateserial \
    -out     "$SW_DIR/switch.crt" \
    2>/dev/null
info "  ✔ Switch cert: $SW_DIR/switch.crt"

# ── Set strict permissions ────────────────────────────────────────────────────
chmod 600 "$CA_DIR/ca.key" "$CTL_DIR/controller.key" "$SW_DIR/switch.key"
chmod 644 "$CA_DIR/ca.crt" "$CTL_DIR/controller.crt" "$SW_DIR/switch.crt"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
info "=========================================="
info "  PKI Generation Complete!"
info "=========================================="
echo ""
echo "  CA Certificate   : $CA_DIR/ca.crt"
echo "  CA Private Key   : $CA_DIR/ca.key"
echo ""
echo "  Controller Cert  : $CTL_DIR/controller.crt"
echo "  Controller Key   : $CTL_DIR/controller.key"
echo ""
echo "  Switch Cert      : $SW_DIR/switch.crt"
echo "  Switch Key       : $SW_DIR/switch.key"
echo ""
info "Verifying certificate chain …"
openssl verify -CAfile "$CA_DIR/ca.crt" "$CTL_DIR/controller.crt" && \
    info "  ✔ Controller cert chain is VALID"
openssl verify -CAfile "$CA_DIR/ca.crt" "$SW_DIR/switch.crt" && \
    info "  ✔ Switch cert chain is VALID"
echo ""
info "Next step: bash ~/isro-sdn-testbed/start_controller_tls.sh"
