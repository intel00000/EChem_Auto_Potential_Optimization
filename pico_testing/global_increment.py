import _thread
import time

# Global variable to be incremented by both threads
global_counter = 0
# Lock to ensure thread-safe operations
counter_lock = _thread.allocate_lock()


# Function to increment the global counter
def increment_global_counter_with_lock():
    global global_counter
    for _ in range(100000):
        # this is a critical section
        with counter_lock:
            global_counter += 1


def increment_global_counter_no_lock():
    global global_counter
    for _ in range(100000):
        global_counter += 1


def main():
    global global_counter

    # Start another thread to increment the global counter
    _thread.start_new_thread(increment_global_counter_with_lock, ())
    increment_global_counter_with_lock()
    # Print the final value of the global counter
    print(f"Final value of increment_global_counter_with_lock: {global_counter}")

    global_counter = 0
    _thread.start_new_thread(increment_global_counter_no_lock, ())
    increment_global_counter_no_lock()
    print(f"Final value of increment_global_counter_no_lock: {global_counter}")


if __name__ == "__main__":
    main()
