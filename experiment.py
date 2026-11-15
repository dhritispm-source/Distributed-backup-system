"""
Network-level experiments for project 24. Run once per controller mode.

  Terminal 1:  SDN_MODE=dynamic python3 run_controller_sdn.py    (or static)
  Terminal 2:  sudo python3 experiment.py dynamic                (same label)

Needs iperf (iperf2):  sudo apt install iperf
Run from the project folder (hosts import sdn_notify from the current dir).
Results are printed and appended to results.csv.
"""
import csv
import sys
import time
from functools import partial

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from topology import BackupTopo

LABEL = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
T_CONC = 10          # seconds, concurrent-transfer test
T_FAIL = 20          # seconds, failure test
FAIL_AT = 5          # second at which s1-s2 is brought down


def notify(h, ip, port, kind):
    h.cmd("python3 -c \"from sdn_notify import notify; notify('%s', %d, '%s')\"" % (ip, port, kind))


def parse(path, host):
    """iperf2 -y C output -> (per-interval Mbps list, whole-run Mbps)"""
    per, total = [], 0.0
    for line in host.cmd('cat ' + path).splitlines():
        f = line.strip().split(',')
        if len(f) < 9:
            continue
        try:
            a, b = [float(x) for x in f[6].split('-')]
            mbps = float(f[8]) / 1e6
        except ValueError:
            continue
        if b - a >= 1.5:
            total = mbps
        else:
            per.append(mbps)
    return per, total


def run():
    net = Mininet(topo=BackupTopo(),
                  switch=partial(OVSSwitch, protocols='OpenFlow13'),
                  controller=None, link=TCLink, autoSetMacs=True)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.start()
    time.sleep(3)
    h1, h2, h3 = net.get('h1'), net.get('h2'), net.get('h3')
    net.pingAll()
    h2.cmd('iperf -s -p 5001 > /dev/null 2>&1 &')
    h3.cmd('iperf -s -p 5002 > /dev/null 2>&1 &')
    time.sleep(1)
    rows = []

    # ---- Test 1: two concurrent transfers (h1->h2 and h1->h3) ----
    info('*** Test 1: two concurrent transfers\n')
    notify(h1, '10.0.0.2', 5001, 'START')
    notify(h1, '10.0.0.3', 5002, 'START')
    time.sleep(1)
    h1.cmd('iperf -c 10.0.0.2 -p 5001 -t %d -i 1 -y C > /tmp/e1.txt &' % T_CONC)
    h1.cmd('iperf -c 10.0.0.3 -p 5002 -t %d -i 1 -y C > /tmp/e2.txt &' % T_CONC)
    time.sleep(T_CONC + 3)
    _, a = parse('/tmp/e1.txt', h1)
    _, b = parse('/tmp/e2.txt', h1)
    notify(h1, '10.0.0.2', 5001, 'END')
    notify(h1, '10.0.0.3', 5002, 'END')
    info('    flow1 %.2f Mbps, flow2 %.2f Mbps, aggregate %.2f Mbps\n' % (a, b, a + b))
    rows.append([LABEL, 'concurrent_2_flows', round(a, 2), round(b, 2), round(a + b, 2), ''])
    time.sleep(2)

    # ---- Test 2: link failure during a transfer ----
    info('*** Test 2: fail s1-s2 at t=%ds during a transfer\n' % FAIL_AT)
    notify(h1, '10.0.0.2', 5001, 'START')
    time.sleep(1)
    h1.cmd('iperf -c 10.0.0.2 -p 5001 -t %d -i 1 -y C > /tmp/e3.txt &' % T_FAIL)
    time.sleep(FAIL_AT)
    net.configLinkStatus('s1', 's2', 'down')
    time.sleep(T_FAIL - FAIL_AT + 3)
    per, total = parse('/tmp/e3.txt', h1)
    after = per[FAIL_AT:]
    zero = sum(1 for x in after if x < 0.1)
    recovered = any(x >= 0.5 for x in after)
    info('    per-second Mbps: %s\n' % ' '.join('%.1f' % x for x in per))
    info('    avg %.2f Mbps, zero-throughput seconds after failure: %d, recovered: %s\n'
         % (total, zero, recovered))
    rows.append([LABEL, 'link_failure', round(total, 2), '', '', 'outage_s=%d recovered=%s' % (zero, recovered)])
    notify(h1, '10.0.0.2', 5001, 'END')

    with open('results.csv', 'a', newline='') as f:
        csv.writer(f).writerows(rows)
    info('*** Appended to results.csv\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
