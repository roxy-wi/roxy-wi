import os
import time
import atexit
import psutil

LOCK_FILE = "/tmp/roxy-wi.lock"


def acquire_file_lock() -> bool:
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid_str, ts_str = f.read().strip().split(",")
                old_pid = int(pid_str)
                old_time = float(ts_str)
        except Exception as e:
            print(f"[LOCK] Corrupt lock file. Removing. ({e})")
            os.remove(LOCK_FILE)
            _create_lock()
            return False

        if psutil.pid_exists(old_pid):
            print( f"[LOCK] Lock held by live process PID {old_pid} (started {time.ctime(old_time)}).")
            return True
        else:
            print( f"[LOCK] Detected dead PID {old_pid}. Lock is stale. Taking ownership.")
            os.remove(LOCK_FILE)
            _create_lock()
            return False
    else:
        _create_lock()
        return False


def _create_lock():
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(f"{os.getpid()},{time.time()}")
        print( f"[LOCK] Lock acquired by PID {os.getpid()}")
    except Exception as e:
        print( f"error: [LOCK] Failed to write lock file: {e}")
        raise e

    # Register cleanup on normal exit
    atexit.register(release_file_lock)


def release_file_lock():
    if not os.path.exists(LOCK_FILE):
        return
    try:
        with open(LOCK_FILE, "r") as f:
            pid_str, _ = f.read().strip().split(",")
        if int(pid_str) == os.getpid():
            os.remove(LOCK_FILE)
            print( f"[LOCK] Lock released by PID {os.getpid()}")
    except Exception as e:
        print( f"[LOCK] Error releasing lock: {e}")
