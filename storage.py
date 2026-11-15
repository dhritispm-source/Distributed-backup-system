import os
import json
import hashlib

class StorageManager:

    def __init__(self, folder):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def save_chunk(self, file_id, chunk_number, data):
        file_folder = os.path.join(self.folder, file_id)
        os.makedirs(file_folder, exist_ok=True)

        chunk_path = os.path.join(
            file_folder,
            f"chunk_{chunk_number}.dat"
        )

        with open(chunk_path, "wb") as file:
            file.write(data)

        checksum = hashlib.sha256(data).hexdigest()

        metadata_path = os.path.join(
            file_folder,
            "metadata.json"
        )

        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as file:
                metadata = json.load(file)
        else:
            metadata = {}

        metadata[str(chunk_number)] = {
            "filename": os.path.basename(chunk_path),
            "checksum": checksum,
            "size": len(data)
        }

        with open(metadata_path, "w") as file:
            json.dump(metadata, file, indent=4)

        print(f"Stored chunk {chunk_number}")
        print(f"SHA-256: {checksum}")

    def get_received_chunks(self, file_id):
        file_folder = os.path.join(self.folder, file_id)
        metadata_path = os.path.join(
            file_folder,
            "metadata.json"
        )

        if not os.path.exists(metadata_path):
            return []

        with open(metadata_path, "r") as file:
            metadata = json.load(file)

        return sorted(int(number) for number in metadata)
