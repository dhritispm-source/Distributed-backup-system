import re
import time
from functools import partial

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from topology import BackupTopo

PING_INTERVAL = 0.01
PING_COUNT = 1500


def run():
    net = Mininet(topo=BackupTopo(),
                  switch=partial(OVSSwitch, protocols='OpenFlow13'),
                  controller=None, link=TCLink, autoSetMacs=True)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.start()
    time.sleep(3)
    h1 = net.get('h1')

    info('*** Baseline connectivity\n')
    net.pingAll()

    info('*** Starting continuous ping h1 -> h2\n')
    h1.cmd('ping -i %s -c %d 10.0.0.2 > /tmp/ping_fail.txt &' % (PING_INTERVAL, PING_COUNT))
    time.sleep(3)

    info('*** FAILING link s1 <-> s2\n')
    net.configLinkStatus('s1', 's2', 'down')
    time.sleep(PING_COUNT * PING_INTERVAL - 2)
    time.sleep(3)

    out = h1.cmd('cat /tmp/ping_fail.txt')
    m = re.search(r'(\d+) packets transmitted, (\d+) received', out)
    if m:
        sent, got = int(m.group(1)), int(m.group(2))
        lost = sent - got
        info('*** Sent %d, received %d, lost %d\n' % (sent, got, lost))
        info('*** Approx. outage: %.0f ms\n' % (lost * PING_INTERVAL * 1000))
    else:
        info('*** Could not parse ping output:\n%s\n' % out)

    info('*** Post-failure connectivity (backup path)\n')
    net.pingAll()
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
