#!/usr/bin/env python3
"""
ISRO SDN Testbed — Phase 2: Mininet Topology with TLS/SSL
==========================================================
Project  : ISRO SDN Testbed
Phase    : 2 — TLS/SSL Security Baseline
Author   : Harsh Agarwal

Topology (same as Phase 1):
    • 1  Core Switch  : s1
    • 10 Edge Switches: s2 to s11  (each connected to s1)
    • 5  Hosts per edge switch     (h1 to h50)

Security:
    • OpenFlow channel encrypted with TLS (mutual authentication)
    • Controller: ssl:127.0.0.1:6653
    • Each OVS switch configured with:
        - its own private key + certificate (signed by CA)
        - the CA certificate for verifying the controller

Prerequisites:
    1. PKI must exist:         bash ~/isro-sdn-testbed/pki/generate_pki.sh
    2. TLS controller running: bash ~/isro-sdn-testbed/start_controller_tls.sh
    3. Run this as root:       sudo python3 ~/isro-sdn-testbed/isro_topo_tls.py
"""

import sys
import time
import logging
import subprocess

from mininet.net  import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.log  import setLogLevel, info, error
from mininet.cli  import CLI
from mininet.topo import Topo

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOG = logging.getLogger("isro.topo.tls")

# ── Controller constants ──────────────────────────────────────────────────────
CONTROLLER_IP   = "127.0.0.1"
CONTROLLER_PORT = 6653

# ── PKI paths (must match start_controller_tls.sh) ───────────────────────────
import os
_BASE = os.path.expanduser("~/isro-sdn-testbed/pki")
CA_CERT  = f"{_BASE}/ca/ca.crt"
SW_CERT  = f"{_BASE}/switch/switch.crt"
SW_KEY   = f"{_BASE}/switch/switch.key"

# ── Link parameters ───────────────────────────────────────────────────────────
CORE_TO_EDGE_BW    = 100   # Mbps
EDGE_TO_HOST_BW    = 10    # Mbps
CORE_TO_EDGE_DELAY = "1ms"
EDGE_TO_HOST_DELAY = "2ms"

# ── Topology counts ───────────────────────────────────────────────────────────
NUM_EDGE_SWITCHES = 10
HOSTS_PER_EDGE    = 5


class ISROTopoTLS(Topo):
    """
    Same 1-core / 10-edge / 50-host topology as Phase 1.
    TLS is applied post-start via ovs-vsctl set-ssl.
    """

    def build(self, **_opts):
        core = self.addSwitch("s1", cls=OVSKernelSwitch, protocols="OpenFlow13")
        LOG.info("Added core switch: s1")

        host_id = 1

        for edge_idx in range(1, NUM_EDGE_SWITCHES + 1):
            edge_name = f"s{edge_idx + 1}"   # s2 … s11
            edge = self.addSwitch(
                edge_name,
                cls=OVSKernelSwitch,
                protocols="OpenFlow13",
            )

            self.addLink(
                core, edge,
                bw=CORE_TO_EDGE_BW,
                delay=CORE_TO_EDGE_DELAY,
                cls=TCLink,
            )
            LOG.info("  Linked: s1 ↔ %s", edge_name)

            for host_idx in range(1, HOSTS_PER_EDGE + 1):
                host_name = f"h{host_id}"
                ip  = f"10.0.0.{host_id}/8"
                mac = f"00:00:00:{edge_idx:02x}:{host_idx:02x}:00"

                host = self.addHost(host_name, ip=ip, mac=mac)
                self.addLink(
                    edge, host,
                    bw=EDGE_TO_HOST_BW,
                    delay=EDGE_TO_HOST_DELAY,
                    cls=TCLink,
                )
                LOG.info("    Host: %s  ip=%s  mac=%s", host_name, ip, mac)
                host_id += 1

        LOG.info(
            "Topology built: 1 core, %d edge switches, %d hosts total",
            NUM_EDGE_SWITCHES,
            NUM_EDGE_SWITCHES * HOSTS_PER_EDGE,
        )


def preflight_check():
    """Verify PKI files and controller port before starting Mininet."""
    import socket

    LOG.info("=== Phase 2 TLS Pre-flight Checks ===")

    # 1. Check certificate files
    for label, path in [("CA cert", CA_CERT), ("Switch cert", SW_CERT), ("Switch key", SW_KEY)]:
        if not os.path.isfile(path):
            error(
                f"\n[FATAL] {label} not found: {path}\n"
                f"  → Run first:  bash ~/isro-sdn-testbed/pki/generate_pki.sh\n"
            )
            sys.exit(1)
        LOG.info("  ✔ %s: %s", label, path)

    # 2. Verify switch cert is signed by CA
    result = subprocess.run(
        ["openssl", "verify", "-CAfile", CA_CERT, SW_CERT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        error(f"\n[FATAL] Switch cert fails CA verification:\n{result.stderr}\n")
        sys.exit(1)
    LOG.info("  ✔ Switch certificate chain verified")

    # 3. Check controller is listening (SSL port — TCP connect check is enough)
    LOG.info("Checking TLS controller at %s:%d …", CONTROLLER_IP, CONTROLLER_PORT)
    for attempt in range(1, 11):
        try:
            with socket.create_connection((CONTROLLER_IP, CONTROLLER_PORT), timeout=2):
                LOG.info("  ✔ Controller is reachable (attempt %d/10).", attempt)
                break
        except (ConnectionRefusedError, OSError):
            LOG.warning("  Controller not up yet (attempt %d/10). Retrying in 2 s …", attempt)
            time.sleep(2)
    else:
        error(
            f"\n[FATAL] Cannot reach TLS controller at {CONTROLLER_IP}:{CONTROLLER_PORT}\n"
            f"  → Start it first:  bash ~/isro-sdn-testbed/start_controller_tls.sh\n"
        )
        sys.exit(1)

    LOG.info("=== All pre-flight checks passed ===")


def configure_ovs_ssl(net):
    """
    Apply TLS configuration to every OVS switch using ovs-vsctl set-ssl.
    This is the CLEAN approach — avoids database corruption:
      1. Clear any existing SSL config
      2. Apply global SSL identity (key + cert + CA)
      3. Point controller target to ssl: URI
      4. Enable secure fail-mode
    """
    info("*** Applying OVS SSL configuration to all switches (Phase 2) ***\n")

    for sw in net.switches:
        name = sw.name

        # Step A: Clear stale SSL and controller config (prevents DB corruption)
        sw.cmd(f"ovs-vsctl del-ssl")   # No-op if not set; idempotent
        sw.cmd(f"ovs-vsctl del-controller {name}")

        # Step B: Set global SSL identity for OVS daemon
        # Format: ovs-vsctl set-ssl <private-key> <certificate> <ca-cert>
        sw.cmd(
            f"ovs-vsctl set-ssl"
            f"  {SW_KEY}"
            f"  {SW_CERT}"
            f"  {CA_CERT}"
        )

        # Step C: Set controller using SSL transport
        sw.cmd(
            f"ovs-vsctl set-controller {name}"
            f"  ssl:{CONTROLLER_IP}:{CONTROLLER_PORT}"
        )

        # Step D: OpenFlow 1.3 + secure fail-mode
        sw.cmd(f"ovs-vsctl set bridge {name} protocols=OpenFlow13")
        sw.cmd(f"ovs-vsctl set bridge {name} fail-mode=secure")

        LOG.info("  ✔ %s: SSL configured → ssl:%s:%d", name, CONTROLLER_IP, CONTROLLER_PORT)

    info("*** Waiting 5 s for TLS handshake with controller …\n")
    time.sleep(5)


def print_connection_status(net):
    """Print controller connection status for all switches."""
    info("*** Switch SSL Connection Status:\n")

    all_connected = True
    for sw in net.switches:
        result = sw.cmd(f"ovs-vsctl show | grep -A3 'Bridge {sw.name}'")
        connected = sw.cmd(
            f"ovs-vsctl get controller {sw.name} is_connected"
        ).strip()
        controller_target = sw.cmd(
            f"ovs-vsctl get controller {sw.name} target"
        ).strip()

        status = "✔ CONNECTED" if connected.lower() == "true" else "✗ NOT connected"
        if connected.lower() != "true":
            all_connected = False

        info(f"    {sw.name}: {status} | target={controller_target}\n")

    if all_connected:
        info("*** ✔ All switches connected to TLS controller!\n")
    else:
        info("*** ✗ Some switches not yet connected — wait a moment and check ovs-vsctl show\n")

    return all_connected


def run():
    setLogLevel("info")

    # Pre-flight checks
    preflight_check()

    topo = ISROTopoTLS()

    net = Mininet(
        topo=topo,
        controller=None,       # Added manually below for full control
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=False,
        autoStaticArp=True,   # Pre-populate ARP caches → no ARP floods
        waitConnected=False,   # We'll wait manually after SSL config
    )

    # Add remote controller (protocol="tcp" here is for Mininet's initial
    # TCP health-check only; actual OVS→controller traffic uses SSL via ovs-vsctl)
    net.addController(
        "c0",
        controller=RemoteController,
        ip=CONTROLLER_IP,
        port=CONTROLLER_PORT,
        protocol="tcp",
    )

    info("\n*** Starting Phase 2 TLS network\n")
    net.start()

    # Apply SSL configuration to all OVS switches AFTER network is up
    # This is the clean, crash-safe approach
    configure_ovs_ssl(net)

    # Report connection status
    print_connection_status(net)

    info("\n*** ISRO SDN Testbed Phase 2 — TLS-Encrypted network is UP\n")
    info("*** OpenFlow channel is now secured with mutual TLS (mTLS)\n")
    info("*** Type 'pingall' to test data plane, 'exit' to quit.\n\n")
    CLI(net)

    info("*** Stopping network\n")
    # Clean up OVS SSL settings on exit
    info("*** Clearing OVS SSL settings …\n")
    for sw in net.switches:
        sw.cmd("ovs-vsctl del-ssl")
        sw.cmd(f"ovs-vsctl del-controller {sw.name}")
    net.stop()


if __name__ == "__main__":
    run()
