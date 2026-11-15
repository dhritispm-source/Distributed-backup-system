import socket

HOST = "127.0.0.1"
PORT = 5001

filename = "hello.txt"
data = b"Hello from the distributed backup client!"

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

client.connect((HOST, PORT))

client.sendall(filename.encode())
client.sendall(data)

client.close()

print("File sent successfully!")
