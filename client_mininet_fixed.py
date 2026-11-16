import socket
import os
import hashlib
import json
import struct

SERVER_IP = "10.0.0.1"
PORT = 5000
CHUNK_SIZE = 4096


def calculate_checksum(filename):
    sha256 = hashlib.sha256()

    with open(filename, "rb") as file:
        while True:
            data = file.read(4096)

            if not data:
                break

            sha256.update(data)

    return sha256.hexdigest()


def receive_exact(sock, size):
    data = b""

    while len(data) < size:
        part = sock.recv(size - len(data))

        if not part:
            return None

        data += part

    return data


def receive_line(sock):
    data = b""

    while not data.endswith(b"\n"):
        part = sock.recv(1)

        if not part:
            return None

        data += part

    return data[:-1]


filename = input("Enter file path: ")

if not os.path.isfile(filename):
    print("File not found!")
    exit()

filesize = os.path.getsize(filename)
checksum = calculate_checksum(filename)

total_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    client.settimeout(30)
    client.connect((SERVER_IP, PORT))

    metadata = {
        "filename": os.path.basename(filename),
        "filesize": filesize,
        "checksum": checksum
    }

    client.sendall(json.dumps(metadata).encode() + b"\n")

    response = receive_exact(client, 4)

    if response is None:
        raise ConnectionError("Server did not respond")

    resume_chunk = struct.unpack("!I", response)[0]

    if resume_chunk > total_chunks:
        raise ValueError("Invalid resume position")

    print("Server requested resume from chunk:", resume_chunk)

    with open(filename, "rb") as file:

        file.seek(resume_chunk * CHUNK_SIZE)

        for chunk_no in range(resume_chunk, total_chunks):

            data = file.read(CHUNK_SIZE)

            header = struct.pack("!II", chunk_no, len(data))

            client.sendall(header + data)

            acknowledgement = receive_exact(client, 4)

            if acknowledgement is None:
                raise ConnectionError("Acknowledgement missing")

            received_no = struct.unpack(
                "!I", acknowledgement
            )[0]

            if received_no != chunk_no:
                raise ValueError("Incorrect acknowledgement")

            print("Chunk acknowledged:", chunk_no)

    client.shutdown(socket.SHUT_WR)

    result = receive_line(client)

    if result is None:
        raise ConnectionError("Server response missing")

    result = result.decode()

    if result == "OK:" + checksum:
        print("\nSUCCESS: File transferred!")
        print("SHA-256 verified!")
        print("Total chunks:", total_chunks)
    else:
        print("Transfer failed:", result)

except Exception as error:
    print("Transfer error:", error)

finally:
    client.close()
