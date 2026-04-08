#!/usr/bin/env python3
"""
ISRO SDN Testbed — Phase 1: Mininet Topology
=============================================
Project  : ISRO SDN Testbed
Phase    : 1 — Raw TCP, no SSL
Author   : Harsh Agarwal

Topology:
    • 1  Core Switch  : s1
    • 10 Edge Switches: s2 to s11  (each connected to s1)
    • 5  Hosts per edge switch     (h1 to h50)

Controller:
    • RemoteController at 127.0.0.1:6653  (Ryu must be running first)
"""

import sys
import time
import logging

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
LOG = logging.getLogger("isro.topo")

# ── Controller constants (must match isro_controller.py) ─────────────────────
CONTROLLER_IP   = "127.0.0.1"
CONTROLLER_PORT = 6653

# ── Link parameters ──────────────────────────────────────────────────────────
CORE_TO_EDGE_BW    = 100   # Mbps
EDGE_TO_HOST_BW    = 10    # Mbps
CORE_TO_EDGE_DELAY = "1ms"
EDGE_TO_HOST_DELAY = "2ms"

# ── Topology counts ───────────────────────────────────────────────────────────
NUM_EDGE_SWITCHES = 10
HOSTS_PER_EDGE    = 5


class ISROTopo(Topo):
    """
    1 core switch → 10 edge switches → 5 hosts each = 50 hosts total.
    IP scheme: 10.0.<edge_idx>.<host_idx>/24
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
                # FLAT /8 subnet — all 50 hosts in 10.0.0.0/8 so they can
                # ARP for each other directly without needing a gateway.
                # Previous /24 per-edge scheme caused 91% drop because
                # cross-subnet pings require a router that doesn't exist.
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


def wait_for_controller(ip: str, port: int, retries: int = 10, delay: float = 2.0):
    """Block until the Ryu controller is reachable on TCP, or exit."""
    import socket
    LOG.info("Checking controller at %s:%d …", ip, port)
    for attempt in range(1, retries + 1):
        try:
            with socket.create_connection((ip, port), timeout=2):
                LOG.info("✔  Controller is reachable (attempt %d/%d).", attempt, retries)
                return
        except (ConnectionRefusedError, OSError):
            LOG.warning(
                "  Not up yet (attempt %d/%d). Retrying in %.1fs …",
                attempt, retries, delay,
            )
            time.sleep(delay)

    error(
        f"\n[FATAL] Cannot reach Ryu at {ip}:{port} after {retries} attempts.\n"
        f"  → Start controller first:  python3 ~/isro-sdn-testbed/isro_controller.py\n"
    )
    sys.exit(1)


def run():
    setLogLevel("info")

    # Pre-flight: make sure controller is up before Mininet tries to connect
    wait_for_controller(CONTROLLER_IP, CONTROLLER_PORT)

    topo = ISROTopo()

    net = Mininet(
        topo=topo,
        controller=None,       # Added manually below for full control
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=False,
        autoStaticArp=True,   # Pre-populate ARP caches → no ARP floods
                               # → controller not overwhelmed on first pingall
        waitConnected=True,
    )

    # Add remote controller with explicit IPv4 address and port
    net.addController(
        "c0",
        controller=RemoteController,
        ip=CONTROLLER_IP,
        port=CONTROLLER_PORT,
        protocol="tcp",
    )

    info("\n*** Starting network\n")
    net.start()

    # Force every OVS switch: OpenFlow 1.3 + explicit controller address
    info("*** Configuring OVS switches for OpenFlow 1.3\n")
    for sw in net.switches:
        sw.cmd(f"ovs-vsctl set bridge {sw.name} protocols=OpenFlow13")
        sw.cmd(
            f"ovs-vsctl set-controller {sw.name} "
            f"tcp:{CONTROLLER_IP}:{CONTROLLER_PORT}"
        )
        sw.cmd(f"ovs-vsctl set bridge {sw.name} fail-mode=secure")

    info("*** Waiting 3 s for OVS ↔ controller handshake …\n")
    time.sleep(3)

    info("*** Switch connection status:\n")
    for sw in net.switches:
        result = sw.cmd(f"ovs-vsctl get-controller {sw.name}")
        info(f"    {sw.name}: controller = {result.strip()}\n")

    info("\n*** ISRO SDN Testbed Phase 1 — network is UP\n")
    info("*** Type 'pingall' to test, 'exit' to quit.\n\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    run()
