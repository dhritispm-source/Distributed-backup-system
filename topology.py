from mininet.topo import Topo


class BackupTopo(Topo):
    r
    def build(self):
        h1 = self.addHost('h1')   # 10.0.0.1  client
        h2 = self.addHost('h2')   # 10.0.0.2  backup server 1
        h3 = self.addHost('h3')   # 10.0.0.3  backup server 2

        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        self.addLink(h1, s1, port2=1, bw=100)
        self.addLink(s1, s2, port1=2, port2=1, bw=10)
        self.addLink(s1, s3, port1=3, port2=1, bw=10)
        self.addLink(s2, s4, port1=2, port2=1, bw=100)
        self.addLink(s3, s4, port1=2, port2=2, bw=100)
        self.addLink(h2, s4, port2=3, bw=100)
        self.addLink(h3, s4, port2=4, bw=100)


topos = {'backuptopo': (lambda: BackupTopo())}
