import os
import hashlib
from storage import StorageManager


class RecoveryManager:

    def __init__(self):
        self.store1 = StorageManager("backup1")
        self.store2 = StorageManager("backup2")

    def find_missing_chunks(self, file_id, total_chunks):

        received1 = self.store1.get_received_chunks(file_id)
        received2 = self.store2.get_received_chunks(file_id)

        received = set(received1 + received2)
        all_chunks = set(range(total_chunks))

        return sorted(all_chunks - received)

    def recover_file(self, file_id, total_chunks, output_path):

        stores = [
            self.store1,
            self.store2
        ]

        missing = self.find_missing_chunks(file_id, total_chunks)

        if missing:
            print("Cannot recover. Missing chunks:", missing)
            return False

        with open(output_path, "wb") as output:

            for chunk_number in range(total_chunks):

                found = False

                for store in stores:

                    folder = os.path.join(store.folder, file_id)

                    chunk_path = os.path.join(
                        folder,
                        f"chunk_{chunk_number}.dat"
                    )

                    metadata_path = os.path.join(
                        folder,
                        "metadata.json"
                    )

                    if not os.path.exists(chunk_path):
                        continue

                    import json

                    with open(metadata_path, "r") as metadata_file:
                        metadata = json.load(metadata_file)

                    expected_hash = metadata[str(chunk_number)]["checksum"]

                    with open(chunk_path, "rb") as chunk_file:
                        data = chunk_file.read()

                    actual_hash = hashlib.sha256(data).hexdigest()

                    if actual_hash != expected_hash:
                        continue

                    output.write(data)
                    found = True
                    break

                if not found:
                    print("Chunk verification failed:", chunk_number)
                    return False

        print("File recovered successfully:", output_path)
        return True
