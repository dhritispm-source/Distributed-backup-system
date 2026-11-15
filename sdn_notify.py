"""Helper for the backup client (runs on h1). Tells the SDN controller about
transfer start/end by sending one UDP datagram to the server's IP, port 9999.
The switch intercepts it (packet-in); the server never needs to listen on it."""
import socket

NOTIFY_PORT = 9999


def notify(server_ip, tcp_port, kind='START'):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(('%s %d' % (kind, tcp_port)).encode(), (server_ip, NOTIFY_PORT))
    finally:
        s.close()

# usage in the client:
#   notify('10.0.0.2', 5001, 'START')   # before connecting / sending chunks
#   ... TCP transfer ...
#   notify('10.0.0.2', 5001, 'END')     # when finished
