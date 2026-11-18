# Distributed Backup over a Dynamic SDN (Mininet + OS-Ken)

A distributed file-backup system built on TCP sockets, running over a Mininet
network that is controlled by an OpenFlow 1.3 SDN controller. The controller
reacts to **application events** (a backup transfer starting or ending), to
**link load** and to **link failures**, and is compared against a **static**
baseline.

## Architecture

```
                 10 Mbps          100 Mbps
          +------ s2 ------+
 h1 ---- s1                 s4 ---- h2  backup server 1 (10.0.0.2)
(client)  +------ s3 ------+    \--- h3  backup server 2 (10.0.0.3)
 10.0.0.1         10 Mbps          100 Mbps

                 OpenFlow 1.3
 SDN controller (OS-Ken, 127.0.0.1:6653) <------> s1, s2, s3, s4
```

* **Application layer (sockets):** `backup_client.py` splits a file into
  chunks and sends them over TCP, in parallel, to two backup servers
  (`backup_server.py`, `backup_server2.py`). Each chunk is checksummed
  (SHA-256) and stored with metadata by `storage.py`. `recovery.py` /
  `restore.py` rebuild the file from the chunks held by either server.
* **Socket-SDN integration:** before each transfer the client sends a small UDP
  datagram `START <tcp_port>` to `<server_ip>:9999` (and `END` afterwards) via
  `sdn_notify.py`. A high-priority flow rule on every switch punts this packet
  to the controller (packet-in), which then selects a path for that TCP flow.
* **SDN controller (`controller_sdn.py`):**
  * `SDN_MODE=dynamic` - shortest-path base routing, port-statistics monitoring
    every second, per-flow load-balanced path selection on application
    signalling, and automatic rerouting of all flows when a link fails.
  * `SDN_MODE=static` - baseline: shortest-path rules are installed once and
    never change; no monitoring, no failure handling, signalling ignored.

Flow rule priorities: 10 = base routes, 20 = per-flow rules, 50 = signalling punt.

## Files

| File | Purpose |
|---|---|
| `topology.py` | Mininet topology (3 hosts, 4 switches, 10 Mbps bottleneck links) |
| `controller_sdn.py`, `run_controller_sdn.py` | OS-Ken controller (dynamic/static) and its launcher |
| `sdn_notify.py` | UDP START/END signalling helper used by the client |
| `backup_client.py` | Chunking backup client (one TCP flow per server) |
| `backup_server.py`, `backup_server2.py` | Chunk-aware TCP backup servers (ports 5001 / 5002) |
| `storage.py`, `recovery.py`, `restore.py` | Chunk storage, integrity check, file recovery |
| `experiment.py` | Automated experiments, writes `results.csv` |
| `failure_simulation.py` | Continuous-ping link-failure test (outage estimate) |
| `plot_results.py` | Builds the comparison table and `results.png` |
| `performance.py`, `test_client.py` | Early unit/smoke tests of storage and sockets |
| `results.csv`, `results.png` | Measured results |

## Requirements

Ubuntu/Debian (VM is fine), Python 3.8+.

```bash
sudo apt install mininet openvswitch-switch iperf
pip install os-ken matplotlib
```

## How to run

### 1. Automated experiments (static vs dynamic)

```bash
rm -f results.csv

# Terminal 1 (no sudo)
SDN_MODE=dynamic python3 run_controller_sdn.py
# Terminal 2
sudo mn -c
sudo python3 experiment.py dynamic
```
Stop the controller (Ctrl+C), then repeat with `SDN_MODE=static` and
`sudo python3 experiment.py static`. Finally:

```bash
python3 plot_results.py results.csv      # prints the table, saves results.png
```

### 2. Interactive demo with the real backup application

```bash
# Terminal 1
SDN_MODE=dynamic python3 run_controller_sdn.py
# Terminal 2
sudo mn -c
sudo mn --custom topology.py --topo backuptopo --controller remote \
        --switch ovs,protocols=OpenFlow13 --link tc --mac
mininet> xterm h1 h2 h3
```

```bash
# xterm h2
python3 backup_server.py 5001 backup1
# xterm h3
python3 backup_server2.py 5002 backup2
# xterm h1
head -c 30000000 /dev/urandom > big.bin
python3 backup_client.py big.bin        # watch the controller log: APP EVENT / Flow ... -> s1->s2->s4
```

Link failure during a transfer (run the client again and, while it is sending):
```
mininet> link s1 s2 down        # controller logs REROUTE; transfer continues via s3
mininet> link s1 s2 up
```

Restore and verify:
```bash
python3 restore.py big.bin 29 restored_big.bin big.bin     # prints VERIFIED
```
(The client prints the exact restore command with the right chunk count.)

Inspect the flow tables: `sudo ovs-ofctl -O OpenFlow13 dump-flows s1`

## Experiments and metrics

| Test | Metric |
|---|---|
| 2 and 3 concurrent flows | per-flow and aggregate throughput (iperf) |
| 20 MB backup via the real application | transfer time, throughput |
| Link failure during iperf | outage seconds, recovery, average throughput |
| Link failure during backup | completed or not, total time |
| Continuous ping (`failure_simulation.py`) | lost packets -> outage duration |

Results (fill in from your own `results.csv`): <!-- paste table / results.png -->

Expected behaviour: static routing puts all flows on one 10 Mbps path (aggregate
about 10 Mbps) and a link failure kills the transfer; dynamic routing spreads
flows over both paths (aggregate about 20 Mbps) and recovers from the failure
within about a second.

## Limitations

* Topology is hard-coded in the controller.
* Load is measured in 1 s windows; flows are not rebalanced mid-transfer except
  after a failure.
* The controller is a single point of failure.
* If a START datagram is lost, the flow simply uses the base route.

## Team

| Member | Contribution |
|---|---|
| (name) | SDN controller, Mininet topology, experiments |
| (name) | Socket client/servers |
| (name) | Storage, recovery, testing |
| (name) | Documentation, report |
