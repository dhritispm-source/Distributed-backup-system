"""
Dynamic SDN controller 

SDN_MODE=dynamic (default):
  - Base routes between all hosts (shortest path, recomputed on link failure)
  - Port-statistics monitoring every STATS_INTERVAL seconds (link load)
  - Application signalling: the backup client sends a small UDP datagram to
    <server_ip>:9999 with payload "START <tcp_port>" or "END <tcp_port>".
    s1 punts it to the controller (packet-in); the controller then picks the
    least-loaded path for that TCP flow and installs per-flow rules (both
    directions). On link failure every active flow is re-routed.
SDN_MODE=static (baseline):
  - Shortest-path routes installed once, never changed, no monitoring,
    no reaction to failures, application signalling ignored.

Run:  SDN_MODE=dynamic python3 run_controller_sdn.py
      SDN_MODE=static  python3 run_controller_sdn.py
"""
import os
import time
from collections import deque

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.lib.packet import packet, ipv4, udp
from os_ken.ofproto import ofproto_v1_3

BaseApp = getattr(app_manager, 'OSKenApp', None) or app_manager.RyuApp

MODE = os.environ.get('SDN_MODE', 'dynamic').lower()
NOTIFY_PORT = 9999
STATS_INTERVAL = 1.0

LINKS = {1: {2: 2, 3: 3}, 2: {1: 1, 4: 2}, 3: {1: 1, 4: 2}, 4: {2: 1, 3: 2}}
HOSTS = {'10.0.0.1': (1, 1), '10.0.0.2': (4, 3), '10.0.0.3': (4, 4)}


class BackupControllerSDN(BaseApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dps = {}
        self.port_down = set()
        self.last = {}        # (dpid, port) -> (tx_bytes, timestamp)
        self.rate = {}        # (dpid, port) -> Mbps
        self.flows = {}       # (src_ip, dst_ip, tcp_port) -> path (list of switches)
        self.assigned = {}    # frozenset({a, b}) -> number of app flows on that link
        self.logger.info("Controller mode: %s", MODE.upper())
        if MODE == 'dynamic':
            hub.spawn(self._monitor)

    # ---------------- topology helpers ----------------
    def link_up(self, a, b):
        return (a, LINKS[a][b]) not in self.port_down and \
               (b, LINKS[b][a]) not in self.port_down

    def shortest_path(self, src, dst):
        queue = deque([[src]])
        seen = {src}
        while queue:
            path = queue.popleft()
            if path[-1] == dst:
                return path
            for n in sorted(LINKS[path[-1]]):
                if n not in seen and self.link_up(path[-1], n):
                    seen.add(n)
                    queue.append(path + [n])
        return None

    def all_paths(self, src, dst):
        """All loop-free paths using only links that are up."""
        result, stack = [], [[src]]
        while stack:
            path = stack.pop()
            if path[-1] == dst:
                result.append(path)
                continue
            for n in sorted(LINKS[path[-1]]):
                if n not in path and self.link_up(path[-1], n):
                    stack.append(path + [n])
        return result

    def link_rate(self, a, b):
        return max(self.rate.get((a, LINKS[a][b]), 0.0),
                   self.rate.get((b, LINKS[b][a]), 0.0))

    def choose_path(self, key):
        src_sw, dst_sw = HOSTS[key[0]][0], HOSTS[key[1]][0]
        best = None
        for path in self.all_paths(src_sw, dst_sw):
            links = list(zip(path, path[1:]))
            cost = (max([self.assigned.get(frozenset(l), 0) for l in links] or [0]),
                    round(max([self.link_rate(*l) for l in links] or [0.0]), 1),
                    len(path), path)   # path last = deterministic tie-break (prefers s2 route)
            if best is None or cost < best[0]:
                best = (cost, path)
        return best[1] if best else None

    # ---------------- OpenFlow helpers ----------------
    def add_flow(self, dp, match, out_port, priority=10):
        p, o = dp.ofproto_parser, dp.ofproto
        actions = [p.OFPActionOutput(out_port, o.OFPCML_NO_BUFFER)]
        inst = [p.OFPInstructionActions(o.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=priority,
                                 match=match, instructions=inst))

    def del_flow(self, dp, match):
        p, o = dp.ofproto_parser, dp.ofproto
        dp.send_msg(p.OFPFlowMod(datapath=dp, table_id=o.OFPTT_ALL,
                                 command=o.OFPFC_DELETE,
                                 out_port=o.OFPP_ANY, out_group=o.OFPG_ANY,
                                 match=match))

    def clear_flows(self, dp):
        self.del_flow(dp, dp.ofproto_parser.OFPMatch())

    def path_ports(self, path, host_port):
        return [(sw, host_port if i == len(path) - 1 else LINKS[sw][path[i + 1]])
                for i, sw in enumerate(path)]

    def flow_matches(self, key, p):
        src, dst, tport = key
        fwd = p.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=src, ipv4_dst=dst, tcp_dst=tport)
        rev = p.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=dst, ipv4_dst=src, tcp_src=tport)
        return fwd, rev

    def install_flow_path(self, key, path):
        src, dst, _ = key
        for hops, host_port, which in ((self.path_ports(path, HOSTS[dst][1]), None, 0),
                                       (self.path_ports(path[::-1], HOSTS[src][1]), None, 1)):
            for sw, out in hops:
                dp = self.dps.get(sw)
                if dp is None:
                    continue
                match = self.flow_matches(key, dp.ofproto_parser)[which]
                self.add_flow(dp, match, out, priority=20)

    def remove_flow_path(self, key):
        for dp in self.dps.values():
            for m in self.flow_matches(key, dp.ofproto_parser):
                self.del_flow(dp, m)

    def bump(self, path, delta):
        for l in zip(path, path[1:]):
            k = frozenset(l)
            self.assigned[k] = max(0, self.assigned.get(k, 0) + delta)

    # ---------------- route installation ----------------
    def install_all(self):
        for dp in self.dps.values():
            self.clear_flows(dp)
        for ip, (dst_sw, dst_port) in HOSTS.items():
            for sw, dp in self.dps.items():
                if sw == dst_sw:
                    out = dst_port
                else:
                    path = self.shortest_path(sw, dst_sw)
                    if path is None:
                        continue
                    out = LINKS[sw][path[1]]
                p = dp.ofproto_parser
                self.add_flow(dp, p.OFPMatch(eth_type=0x0800, ipv4_dst=ip), out)
                self.add_flow(dp, p.OFPMatch(eth_type=0x0806, arp_tpa=ip), out)
        if MODE == 'dynamic':
            for dp in self.dps.values():
                p, o = dp.ofproto_parser, dp.ofproto
                self.add_flow(dp, p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=NOTIFY_PORT),
                              o.OFPP_CONTROLLER, priority=50)
            self.reroute_flows()
        p1 = self.shortest_path(1, 4)
        self.logger.info("Base path s1 -> s4 : %s",
                         '->'.join('s%d' % s for s in p1) if p1 else 'NONE')

    def reroute_flows(self):
        self.assigned.clear()
        for key in list(self.flows):
            path = self.choose_path(key)
            self.flows[key] = path
            if path is None:
                self.logger.info("Flow %s: no path available", key)
                continue
            self.bump(path, +1)
            self.install_flow_path(key, path)
            self.logger.info("Flow %s -> %s", key, '->'.join('s%d' % s for s in path))

    # ---------------- events ----------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch(self, ev):
        dp = ev.msg.datapath
        self.dps[dp.id] = dp
        self.logger.info("Switch s%d connected", dp.id)
        self.install_all()

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def on_port_status(self, ev):
        t0 = time.time()
        msg = ev.msg
        dp = msg.datapath
        o = dp.ofproto
        port = msg.desc.port_no
        if port > o.OFPP_MAX:
            return
        down = bool(msg.desc.state & o.OFPPS_LINK_DOWN) or \
               bool(msg.desc.config & o.OFPPC_PORT_DOWN)
        self.logger.info("s%d port %d is now %s", dp.id, port, 'DOWN' if down else 'UP')
        if MODE != 'dynamic':
            return                      # static baseline: do nothing
        key = (dp.id, port)
        if down == (key in self.port_down):
            return
        if down:
            self.port_down.add(key)
        else:
            self.port_down.discard(key)
        self.install_all()
        self.logger.info("REROUTE completed in %.2f ms", (time.time() - t0) * 1000)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, ev):
        if MODE != 'dynamic':
            return
        pkt = packet.Packet(ev.msg.data)
        ip, u = pkt.get_protocol(ipv4.ipv4), pkt.get_protocol(udp.udp)
        if not ip or not u or u.dst_port != NOTIFY_PORT:
            return
        payload = pkt.protocols[-1]
        try:
            kind, tport = bytes(payload).decode().split()[:2]
            tport = int(tport)
        except Exception:
            self.logger.warning("Bad app notification from %s", ip.src)
            return
        if ip.src not in HOSTS or ip.dst not in HOSTS:
            return
        key = (ip.src, ip.dst, tport)
        self.logger.info("APP EVENT %s %s", kind, key)
        if kind == 'START' and key not in self.flows:
            path = self.choose_path(key)
            self.flows[key] = path
            if path:
                self.bump(path, +1)
                self.install_flow_path(key, path)
                self.logger.info("Flow %s -> %s", key, '->'.join('s%d' % s for s in path))
        elif kind == 'END' and key in self.flows:
            path = self.flows.pop(key)
            if path:
                self.bump(path, -1)
            self.remove_flow_path(key)

    # ---------------- monitoring ----------------
    def _monitor(self):
        while True:
            for dp in list(self.dps.values()):
                p = dp.ofproto_parser
                dp.send_msg(p.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
            hub.sleep(STATS_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def on_port_stats(self, ev):
        now, dpid = time.time(), ev.msg.datapath.id
        for st in ev.msg.body:
            k = (dpid, st.port_no)
            prev = self.last.get(k)
            if prev and now > prev[1]:
                self.rate[k] = (st.tx_bytes - prev[0]) * 8 / (now - prev[1]) / 1e6
            self.last[k] = (st.tx_bytes, now)
