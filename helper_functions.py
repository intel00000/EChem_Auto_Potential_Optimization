# gui imports
from tkinter import messagebox

# other library
import os, sys
import psutil

LOCK_FILE = ".pico_controller.lock"  # Lock file path (to identify a running instance)

NANOSECONDS_PER_DAY = 24 * 60 * 60 * 1_000_000_000
NANOSECONDS_PER_HOUR = 60 * 60 * 1_000_000_000
NANOSECONDS_PER_MINUTE = 60 * 1_000_000_000
NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MILLISECOND = 1_000_000
NANOSECONDS_PER_MICROSECOND = 1_000

def check_lock_file() -> None:
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            # If the process exists, show a message box and exit
            messagebox.showwarning(
                "Already Running",
                "Another instance of this program is already running, check your taskbar!",
            )
            sys.exit(0)
        else:
            # If the process doesn't exist, the lock file is stale; remove it
            os.remove(LOCK_FILE)
    # If no valid lock file or stale lock file, create a new one
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_lock_file() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        print(f"Error removing lock file: {e}")


def resource_path(relative_path) -> str:
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def convert_minutes_to_ns(minutes: float) -> int:
    return int(minutes * 60 * NANOSECONDS_PER_SECOND)

def convert_ns_to_timestr(ns: int) -> str:
    days = ns // NANOSECONDS_PER_DAY
    ns %= NANOSECONDS_PER_DAY
    hours = ns // NANOSECONDS_PER_HOUR
    ns %= NANOSECONDS_PER_HOUR
    minutes = ns // NANOSECONDS_PER_MINUTE
    ns %= NANOSECONDS_PER_MINUTE
    seconds = ns / NANOSECONDS_PER_SECOND
    # Build the formatted time string, hiding fields with 0 values
    time_parts = []
    if days > 0:
        time_parts.append(f"{days} days")
    if hours > 0:
        time_parts.append(f"{hours} hours")
    if minutes > 0:
        time_parts.append(f"{minutes} minutes")
    if seconds > 0:
        time_parts.append(f"{seconds:.1f} seconds")
    return ", ".join(time_parts)