import socket
import os

HOST = "0.0.0.0"
PORT = 5002
SAVE_FOLDER = "backup2"

os.makedirs(SAVE_FOLDER, exist_ok=True)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server.bind((HOST, PORT))
server.listen(5)

print("Backup Server 2 running on port 5002...")

while True:
    conn, addr = server.accept()
    print("Connected by:", addr)

    filename = conn.recv(1024).decode()

    filepath = os.path.join(SAVE_FOLDER, os.path.basename(filename))

    with open(filepath, "wb") as file:
        while True:
            data = conn.recv(4096)

            if not data:
                break

            file.write(data)

    print("File received:", filepath)

    conn.close()
