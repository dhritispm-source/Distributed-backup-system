import socket
import os
import hashlib
import json
import struct
import threading

HOST = "0.0.0.0"
PORT = 5000
CHUNK_SIZE = 4096


def receive_exact(conn, size):
    data = b""

    while len(data) < size:
        part = conn.recv(size - len(data))

        if not part:
            return None

        data += part

    return data


def receive_line(conn):
    data = b""

    while not data.endswith(b"\n"):
        part = conn.recv(1)

        if not part:
            return None

        data += part

    return data[:-1]


def calculate_checksum(filename):
    sha256 = hashlib.sha256()

    with open(filename, "rb") as file:
        while True:
            data = file.read(4096)

            if not data:
                break

            sha256.update(data)

    return sha256.hexdigest()


def handle_client(conn, addr):

    print("\nConnected client:", addr)

    try:
        metadata = receive_line(conn)

        if metadata is None:
            return

        info = json.loads(metadata.decode())

        filename = os.path.basename(info["filename"])
        filesize = int(info["filesize"])
        expected_checksum = info["checksum"]

        if (not filename or filesize < 0 or
                len(expected_checksum) != 64 or
                any(c not in "0123456789abcdef"
                    for c in expected_checksum.lower())):
            raise ValueError("Invalid file information")

        filepath = os.path.join("received_files", filename)

        partial_path = filepath + "." + expected_checksum + ".part"

        total_chunks = (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE

        if os.path.exists(partial_path):
            partial_size = os.path.getsize(partial_path)
        else:
            partial_size = 0

        resume_chunk = min(
            partial_size // CHUNK_SIZE,
            total_chunks
        )

        resume_position = resume_chunk * CHUNK_SIZE

        with open(partial_path, "a+b") as file:

            file.truncate(resume_position)
            file.seek(resume_position)

            conn.sendall(struct.pack("!I", resume_chunk))

            print("Resuming from chunk:", resume_chunk)

            for chunk_no in range(resume_chunk, total_chunks):

                header = receive_exact(conn, 8)

                if header is None:
                    raise ConnectionError("Chunk header missing")

                received_no, length = struct.unpack("!II", header)

                expected_length = min(
                    CHUNK_SIZE,
                    filesize - chunk_no * CHUNK_SIZE
                )

                if received_no != chunk_no or length != expected_length:
                    raise ValueError("Invalid chunk")

                data = receive_exact(conn, length)

                if data is None:
                    raise ConnectionError("Incomplete chunk")

                file.write(data)
                file.flush()

                conn.sendall(struct.pack("!I", chunk_no))

                print("Client", addr, "- Chunk:", chunk_no)

        received_checksum = calculate_checksum(partial_path)

        if received_checksum == expected_checksum:

            os.replace(partial_path, filepath)

            conn.sendall(
                ("OK:" + received_checksum + "\n").encode()
            )

            print("File restored:", filename)
            print("Checksum verified!")

        else:
            conn.sendall(b"ERROR:CHECKSUM\n")
            print("Checksum verification failed!")

    except Exception as error:
        print("Client error:", addr, error)

    finally:
        conn.close()
        print("Connection closed:", addr)


os.makedirs("received_files", exist_ok=True)

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen(5)

print("Multithreaded Backup Server running...")
print("Waiting for clients...")

while True:

    conn, addr = server.accept()

    client_thread = threading.Thread(
        target=handle_client,
        args=(conn, addr)
    )

    client_thread.start()
