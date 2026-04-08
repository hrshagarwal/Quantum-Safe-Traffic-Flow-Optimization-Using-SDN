# ISRO SDN Testbed — Phase 2: TLS/SSL Security Baseline

> **Status:** ✅ Complete  
> **Author:** Harsh Agarwal  
> **Date:** April 2026  
> **Builds on:** Phase 1 (11 switches, 50 hosts, 0% packet loss verified)  
> **Leads to:** Phase 3 — Post-Quantum Cryptography (Kyber-512)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [PKI: Certificates and Their Roles](#2-pki-certificates-and-their-roles)
3. [File Locations](#3-file-locations)
4. [How the TLS Handshake Works](#4-how-the-tls-handshake-works)
5. [Step-by-Step: Running Phase 2](#5-step-by-step-running-phase-2)
6. [Verification Checklist](#6-verification-checklist)
7. [Security Model](#7-security-model)
8. [Troubleshooting](#8-troubleshooting)
9. [Migration to Phase 3](#9-migration-to-phase-3)

---

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                    ISRO Ground Station Network              │
│                                                            │
│   ┌──────────────────────┐                                 │
│   │   Ryu Controller     │  ← TLS Server                  │
│   │  (isro_controller.py)│    cert: controller.crt         │
│   │   port 6653 (SSL)    │    key:  controller.key         │
│   └──────────┬───────────┘    CA:   ca.crt                 │
│              │  ▲  Encrypted OpenFlow 1.3 (TLS)            │
│              │  │  Mutual Authentication (mTLS)            │
│              ▼  │                                          │
│   ┌──────────────────────┐                                 │
│   │   OVS Core Switch s1 │  ← TLS Client                  │
│   └──┬───────────────────┘    cert: switch.crt             │
│      │                        key:  switch.key             │
│   ┌──┴──┬──┬──┬──┬──┬──┐      CA:   ca.crt                 │
│  s2   s3  s4 s5 s6 s7 …s11  (10 edge switches)            │
│   │    │  │  │                                             │
│  h1…h5 h6…h10  …        h46…h50  (50 hosts total)         │
└────────────────────────────────────────────────────────────┘
```

**What changed from Phase 1:**

| Aspect             | Phase 1 (TCP)            | Phase 2 (TLS)                             |
|--------------------|--------------------------|-------------------------------------------|
| Transport          | Raw TCP port 6653        | TLS 1.2/1.3 over port 6653               |
| Authentication     | None                     | Mutual TLS (both sides present certs)    |
| Eavesdropping risk | HIGH — plaintext OF msgs | NONE — all OF data AES-encrypted         |
| Rogue controller   | Any machine can connect  | Only cert-holder can connect             |
| Config files       | `isro_topo.py`           | `isro_topo_tls.py`                       |
| Launch script      | `start_controller.sh`    | `start_controller_tls.sh`               |

---

## 2. PKI: Certificates and Their Roles

### What is a CA (Certificate Authority)?

The **CA (Certificate Authority)** is the root of trust. It is a self-signed certificate that acts as the "authenticator" for all other certificates in the system. When Ryu (the controller) receives a connection from an OVS switch, it checks: *"Is this switch's certificate signed by our trusted CA?"* — if yes, the connection is allowed. If not, the TLS handshake fails and the connection is rejected.

This prevents **rogue controllers** (attacker injecting fake OF commands) and **rogue switches** (attacker intercepting traffic) from participating in the network.

### Certificate Hierarchy

```
ISRO-SDN-CA  (self-signed, 10 years)
├── ryu-controller  (signed by CA, 10 years)
│     Subject: CN=ryu-controller, OU=SDN-Controller, O=ISRO
│     Used by: Ryu controller to identify itself to switches
│
└── ovs-switch  (signed by CA, 10 years)
      Subject: CN=ovs-switch, OU=SDN-Switch, O=ISRO
      Used by: ALL OVS switches (shared cert for this testbed)
```

### Mutual TLS (mTLS)

Both sides present and verify certificates:

- **Controller → Switch validation:** Ryu verifies the switch's cert is CA-signed before accepting its OpenFlow connection.
- **Switch → Controller validation:** OVS verifies the controller's cert is CA-signed before sending OpenFlow messages.

This bidirectional validation is what makes it **mutual** TLS (mTLS), not just standard one-way TLS.

---

## 3. File Locations

```
~/isro-sdn-testbed/
├── pki/
│   ├── generate_pki.sh            ← Run ONCE to create all certs
│   │
│   ├── ca/
│   │   ├── ca.key                 ← CA private key  [chmod 600 — KEEP SECRET]
│   │   ├── ca.crt                 ← CA certificate  [shared with all parties]
│   │   └── ca.srl                 ← CA serial number file (auto-managed)
│   │
│   ├── controller/
│   │   ├── controller.key         ← Ryu's private key     [chmod 600]
│   │   ├── controller.csr         ← Certificate signing request (intermediate)
│   │   └── controller.crt         ← Ryu's signed certificate
│   │
│   └── switch/
│       ├── switch.key             ← OVS switches' private key  [chmod 600]
│       ├── switch.csr             ← Certificate signing request (intermediate)
│       └── switch.crt             ← OVS switches' signed certificate
│
├── start_controller_tls.sh        ← Phase 2 controller launcher (TLS)
├── start_controller.sh            ← Phase 1 controller launcher (TCP, unchanged)
├── isro_topo_tls.py               ← Phase 2 Mininet topology (TLS)
├── isro_topo.py                   ← Phase 1 Mininet topology (TCP, unchanged)
└── isro_controller.py             ← Ryu app (shared, unchanged — no SSL logic here)
```

**Key file permissions:**
```
-rw------- (600)  ca.key, controller.key, switch.key   (private keys — never share)
-rw-r--r-- (644)  ca.crt, controller.crt, switch.crt  (public certs — safe to share)
```

---

## 4. How the TLS Handshake Secures Traffic Management

When an OVS switch connects to the Ryu controller, a **TLS handshake** occurs before any OpenFlow message is exchanged:

```
OVS Switch                            Ryu Controller
    │                                       │
    │──── ClientHello (TLS 1.2/1.3) ───────►│
    │     (supported ciphers, random nonce) │
    │                                       │
    │◄─── ServerHello + controller.crt ─────│
    │     (selected cipher, server cert)    │
    │                                       │
    │  Switch verifies: Is controller.crt   │
    │  signed by our CA (ca.crt)? ✔         │
    │                                       │
    │──── switch.crt (client cert) ────────►│
    │                                       │
    │  Controller verifies: Is switch.crt   │
    │  signed by our CA (ca.crt)? ✔         │
    │                                       │
    │──── Key Exchange (ECDHE) ─────────────│
    │◄─── Session Keys derived ─────────────│
    │                                       │
    │═══════ Encrypted OpenFlow 1.3 ════════│
    │  (FlowMod, PacketIn, PacketOut…)      │
```

### What this protects against:

| Threat | Without TLS (Phase 1) | With TLS (Phase 2) |
|--------|----------------------|---------------------|
| **Eavesdropping** | Attacker can `tcpdump` and read all flow rules | All OF messages are AES-encrypted |
| **Rogue Controller** | Any process on port 6653 can control switches | Must present cert signed by ISRO-CA |
| **Rogue Switch** | Any OVS instance can register with controller | Must present cert signed by ISRO-CA |
| **Man-in-the-Middle** | Full interception possible | Certificate verification blocks MITM |
| **Replay Attacks** | OF messages can be captured and replayed | TLS session keys are ephemeral (ECDHE) |

> **Note on Perfect Forward Secrecy:** The key exchange uses ECDHE (Elliptic Curve Diffie-Hellman Ephemeral), meaning session keys are **never stored**. Even if the private key is later compromised, past recorded sessions cannot be decrypted.

---

## 5. Step-by-Step: Running Phase 2

### Terminal 1 — Generate PKI (once only)

```bash
cd ~/isro-sdn-testbed
bash pki/generate_pki.sh
```

Expected output:
```
[PKI]  ✔ Controller cert chain is VALID
[PKI]  ✔ Switch cert chain is VALID
```

### Terminal 1 — Start TLS Controller

```bash
bash ~/isro-sdn-testbed/start_controller_tls.sh
```

Wait for Ryu to print: `Listening on 0.0.0.0:6653`

### Terminal 2 — Start TLS Topology

```bash
sudo python3 ~/isro-sdn-testbed/isro_topo_tls.py
```

### Terminal 2 (Mininet CLI) — Verify

```
mininet> sh ovs-vsctl show
# Look for: is_connected: true  AND  target: "ssl:127.0.0.1:6653"

mininet> pingall
# Expected: 0% packet loss (same as Phase 1)
```

---

## 6. Verification Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Certs exist | `ls ~/isro-sdn-testbed/pki/**/*.crt` | 3 .crt files |
| Cert chain valid | `openssl verify -CAfile pki/ca/ca.crt pki/controller/controller.crt` | `OK` |
| Controller TLS port | `sudo ss -tlnp \| grep 6653` | `LISTEN 0 ... 0.0.0.0:6653` |
| Switch connected | `ovs-vsctl get controller s1 is_connected` | `true` |
| SSL target set | `ovs-vsctl get controller s1 target` | `"ssl:127.0.0.1:6653"` |
| Data plane OK | `pingall` (in Mininet CLI) | `Results: 0% dropped` |

---

## 7. Security Model

```
┌─────────────────────────────────────────────────────┐
│              TRUST HIERARCHY                        │
│                                                     │
│  ISRO-SDN-CA (Root of Trust)                        │
│  ├── Issues and signs all entity certificates       │
│  ├── ca.key MUST be kept offline/secure             │
│  └── ca.crt distributed to ALL parties             │
│                                                     │
│  Controller (ryu-controller)                        │
│  ├── Proves identity with controller.crt            │
│  └── controller.key never leaves the controller     │
│                                                     │
│  Switches (ovs-switch)                             │
│  ├── Prove identity with switch.crt                 │
│  └── switch.key never leaves the switches          │
└─────────────────────────────────────────────────────┘
```

**For production deployment (beyond testbed):**
- Issue a unique cert per switch (not one shared cert)
- Store `ca.key` on an air-gapped machine
- Set cert validity to ≤ 1 year with auto-renewal via ACME/EST
- Use Hardware Security Modules (HSM) for key storage

---

## 8. Troubleshooting

### `is_connected: false` after startup

```bash
# Check OVS logs for TLS errors
sudo journalctl -u openvswitch-switch --since "5 minutes ago" | grep -i ssl

# Check Ryu terminal for certificate errors
# Common cause: ryu.conf exists and overrides SSL settings
ls ~/ryu.conf   # Should NOT exist
```

### `ovs-vsctl: ovs-vswitchd: database connection failed`

```bash
# Restart OVS daemon (safe — does not delete switch configs in most cases)
sudo systemctl restart openvswitch-switch
sudo ovs-vsctl show   # Should return cleanly
```

### TLS handshake failing (`SSL routines:wrong version number`)

```bash
# Verify both sides use compatible TLS versions
openssl s_client -connect 127.0.0.1:6653 -CAfile pki/ca/ca.crt \
    -cert pki/switch/switch.crt -key pki/switch/switch.key
```

### Phase 1 still works after Phase 2 setup?

Yes — Phase 1 files are **untouched**. To run Phase 1:
```bash
# Terminal 1:
bash ~/isro-sdn-testbed/start_controller.sh

# Terminal 2:
sudo python3 ~/isro-sdn-testbed/isro_topo.py
```

---

## 9. Migration to Phase 3 (PQC — Kyber-512)

Phase 3 will replace the RSA-2048 keys in this PKI with **Post-Quantum Cryptography** using Kyber-512 (CRYSTALS-Kyber). The TLS infrastructure established here serves as the baseline:

| Component | Phase 2 (Current) | Phase 3 (Upcoming) |
|-----------|------------------|---------------------|
| Key Exchange | ECDHE (classical) | Kyber-512 KEM (quantum-safe) |
| Signature | RSA-2048 | Dilithium / SPHINCS+ |
| Cert Validity | 10 years | As specified by PQC policy |
| Implementation | OpenSSL 1.1.1 | liboqs + OpenSSL 3.x |
| Transport | TLS 1.3 | TLS 1.3 + PQC hybrid |

> **⚠ WARNING for Phase 3 implementors:** Do not modify `pki/` — Phase 3 will create its own `pki_pqc/` directory. The TLS baseline remains active as a fallback.

---

*Generated for ISRO SDN Testbed Project — Phase 2 TLS Security Baseline*  
*OpenSSL 1.1.1f | OVS 2.13.8 | Ryu 4.x | OpenFlow 1.3*
