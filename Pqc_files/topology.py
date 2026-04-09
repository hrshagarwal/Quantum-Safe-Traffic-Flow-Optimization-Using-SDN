from mininet.topo import Topo

class PQCTopo(Topo):

    def build(self):

        # Hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')

        # Switch
        s1 = self.addSwitch('s1')

        # Links
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s1)

# Required for Mininet to detect
topos = {'pqctopo': (lambda: PQCTopo())}