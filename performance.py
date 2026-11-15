import time
import os
from storage import StorageManager

def test_backup():

    store = StorageManager("backup1")

    data = os.urandom(1024 * 1024)

    start_time = time.time()

    store.save_chunk("performance_test", 1, data)

    end_time = time.time()

    elapsed_time = end_time - start_time

    throughput = (len(data) / (1024 * 1024)) / elapsed_time

    print("Backup Performance Test")
    print("Data size: 1 MB")
    print("Time taken:", round(elapsed_time, 4), "seconds")
    print("Throughput:", round(throughput, 2), "MB/s")


if __name__ == "__main__":
    test_backup()
