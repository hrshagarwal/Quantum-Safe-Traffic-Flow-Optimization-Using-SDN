# 🛰️ ISRO SDN Testbed — Phase 1 Demo Guide
### Presenter: Harsh Agarwal | Project: Secure SDN for ISRO

---

## 📌 What This Project Is (Say This to Judges)

> *"We are building a Software-Defined Network testbed on an Ubuntu VM
> to simulate the control plane of a satellite ground station network.
> In traditional networks, every router/switch decides how to forward
> packets on its own — which is slow to update and hard to secure.
> In SDN, one central controller (Ryu) has a bird's-eye view of the
> entire network and programs every switch (via Open vSwitch) in real-time
> using the OpenFlow protocol. Phase 1 establishes this basic working
> network. Phase 3 will add Post-Quantum Cryptography to secure the
> controller-switch channel against quantum computer attacks."*

---

## 🏗️ Architecture at a Glance

```
         ┌─────────────────────────────┐
         │      Ryu SDN Controller     │  ← Our Python program
         │       127.0.0.1 : 6653      │    (the "brain" of the network)
         └──────────────┬──────────────┘
                        │  OpenFlow 1.3 over TCP
                        │  (controller tells switches what to do)
                 ┌──────┴──────┐
                 │  s1  CORE   │  ← Central OVS switch
                 └──┬──────┬───┘
           ┌────────┘      └────────┐   (×10 edge switches)
        ┌──┴──┐                 ┌───┴─┐
        │ s2  │   . . .         │ s11 │   ← Edge OVS switches
        └──┬──┘                 └──┬──┘
      h1–h5                   h46–h50     ← 50 virtual hosts total
  10.0.0.1–5               10.0.0.46–50
```

| Component | Tool Used | Simple Explanation |
|-----------|-----------|-------------------|
| Virtual Hosts (h1–h50) | Mininet | Fake computers in software |
| Virtual Switches (s1–s11) | Open vSwitch (OVS) | Fake network switches |
| Network Simulator | Mininet | Creates the fake network topology |
| SDN Controller | Ryu (Python) | The brain — tells switches where to send packets |
| Protocol | OpenFlow 1.3 | Language the controller uses to talk to switches |

---

## ⚡ DEMO — Step by Step

> ⚠️ **Setup rule:** Always start **controller FIRST**, then **topology**.

---

### ✅ STEP 0 — One-Time Reset (Run ONCE before your demo)

```bash
sudo mn -c
sudo ufw disable
sudo iptables -F
sudo fuser -k 6653/tcp 2>/dev/null || true
```

---

### ✅ STEP 1 — Terminal 1: Start the Ryu SDN Controller

```bash
bash ~/isro-sdn-testbed/start_controller.sh
```

**Verify controller is listening:**
```bash
sudo ss -tlnp | grep 6653
# Must show: LISTEN  0  50  0.0.0.0:6653
```

---

### ✅ STEP 2 — Terminal 2: Start the Network Topology

```bash
cd ~/isro-sdn-testbed
sudo python3 isro_topo.py
```

Wait for: `mininet>` prompt

---

### ✅ STEP 3 — Verify all switches connected

```bash
mininet> sh ovs-vsctl show
# Look for:  is_connected: true  on every switch
```

---

### ✅ STEP 4 — Same-switch ping

```bash
mininet> h1 ping -c 3 h2
# Expected: 0% packet loss
```

---

### ✅ STEP 5 — Cross-switch ping

```bash
mininet> h1 ping -c 3 h6
# h1 on s2, h6 on s3 — crosses s1 core
# Expected: 0% packet loss
```

---

### ✅ STEP 6 — Show the flow table

```bash
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
# Shows every forwarding rule Ryu installed
```

---

### ✅ STEP 7 — Full 50-host mesh test

```bash
mininet> pingall
# Expected: 0% dropped (2450/2450 received) ← THE MONEY SHOT
```

---

### ✅ STEP 8 — Cleanup

```bash
mininet> exit
# Terminal 1: Ctrl+C
```

---

## 🎓 Technical Terms — Simple Explanations

| Term | Simple English |
|------|----------------|
| **SDN** | One central program controls all switches. Like a traffic police officer vs every car deciding its own route. |
| **OpenFlow** | The language the controller uses to talk to switches. Like a manager giving orders to employees. |
| **OVS** | A software switch in Linux. Same job as a physical Cisco box but in code. |
| **Ryu** | Our Python controller. The brain of the network. |
| **Packet-In** | Switch asks controller: "I got a packet I don't know about — what do I do?" |
| **Flow Entry** | A rule in the switch: "if packet = THIS → send to PORT X". Executed at hardware speed. |
| **Table-Miss** | Priority=0 catch-all rule: "if nothing matches → send to controller". The safety net. |
| **MAC Learning** | Controller remembers "MAC X is reachable via port Y on switch Z". Like remembering which seat someone sits in. |
| **DPID** | Unique ID of each switch. Like an Aadhar number for a switch. |
| **fail-mode=secure** | If controller disconnects, switch drops unknown traffic — safe for high-security networks. |

---

## ❓ Likely Questions & Answers

**Q: Why SDN instead of traditional networking?**
> *"Traditional networks need manual config of every device. SDN lets
> you reprogram everything from one place in seconds. For ISRO, satellite
> links come up and down dynamically — SDN policies update via code,
> not manual CLI work."*

**Q: Why Ryu and not ONOS or OpenDaylight?**
> *"Ryu is lightweight, pure Python, perfect for research. For Phase 3,
> we need source-level access to plug in liboqs Kyber — Ryu gives us that
> without enterprise framework overhead."*

**Q: What if the controller crashes?**
> *"fail-mode=secure — switches drop unknown traffic instead of guessing.
> Existing flow entries survive controller restarts. Established connections
> continue uninterrupted. We will add controller HA in later phases."*

**Q: What is Phase 3 about?**
> *"We replace standard TLS on the OpenFlow channel with Kyber-512 — a
> Post-Quantum Key Encapsulation Mechanism standardized by NIST in 2024.
> Secures the controller-switch link against quantum computers that can
> break RSA and ECC used in today's TLS."*

**Q: What do the 50 hosts represent?**
> *"Ground station terminals, satellite modems, and internal LAN nodes.
> Edge switches are access-layer aggregation points. The core switch is
> the ground station backbone."*

---

## 🚀 Phase Roadmap

```
Phase 1 ✅  Raw TCP OpenFlow 1.3 | MAC-learning L2 | 0% packet loss
Phase 2 ⏳  TLS on OpenFlow channel | OVS PKI certs | Ryu --ctl-cert
Phase 3 🎯  Kyber-512 PQC via liboqs | Quantum-safe control plane
```

---
*ISRO SDN Testbed | Phase 1 Complete ✅ | Harsh Agarwal*
