#!/usr/bin/env python3
"""
ISRO SDN Testbed — Phase 1: Ryu Controller (SimpleSwitch13)
============================================================
Project  : ISRO SDN Testbed
Phase    : 1 — Raw TCP, no SSL
Author   : Harsh Agarwal

NOTE: Do NOT run this file directly with python3.
      Use the provided shell script instead:

        bash ~/isro-sdn-testbed/start_controller.sh

      The ryu-manager binary MUST be the entry point so that
      eventlet.monkey_patch() fires before any stdlib socket
      imports — otherwise the OF server silently never binds.
"""

import logging

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types

LOG = logging.getLogger("isro.controller")


class ISROSimpleSwitch13(app_manager.RyuApp):
    """
    Layer-2 MAC-learning switch using OpenFlow 1.3.

    Behaviour:
        • Packet-in for unknown destination  → flood + learn source MAC
        • Packet-in for known destination    → install bi-directional flow
        • Table-miss flow (priority 0)       → send all unmatched to controller
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mac_table[dpid][mac_addr] = port_no
        self.mac_table: dict = {}
        LOG.info("ISROSimpleSwitch13 — initialised, waiting for switches to connect.")

    # ── Switch Handshake ─────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install the table-miss entry on every newly connected switch."""
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        LOG.info("Switch connected: DPID=%016x", datapath.id)

        # priority=0, match-all → send to controller (table-miss)
        match   = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

    # ── Packet-In Handler ─────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        in_port  = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Drop LLDP / topology discovery frames
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst  = eth.dst
        src  = eth.src
        dpid = datapath.id

        self.mac_table.setdefault(dpid, {})
        self.mac_table[dpid][src] = in_port   # learn source

        out_port = self.mac_table[dpid].get(dst, ofproto.OFPP_FLOOD)

        LOG.debug(
            "DPID=%016x  in_port=%s  src=%s  dst=%s  → out_port=%s",
            dpid, in_port, src, dst, out_port,
        )

        actions = [parser.OFPActionOutput(out_port)]

        # Only install a flow when we know the exact egress port
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self._add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            self._add_flow(datapath, 1, match, actions)

        # Always send Packet-Out so the very first frame is delivered
        data = None if msg.buffer_id != ofproto.OFP_NO_BUFFER else msg.data
        out  = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    # ── Helper ───────────────────────────────────────────────────────────────

    def _add_flow(self, datapath, priority, match, actions,
                  buffer_id=None, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser

        inst   = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        kwargs = dict(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id

        datapath.send_msg(parser.OFPFlowMod(**kwargs))
        LOG.debug("Flow installed — DPID=%016x  priority=%d", datapath.id, priority)
