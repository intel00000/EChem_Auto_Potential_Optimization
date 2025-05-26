# bootloader_util.py
import os
import gc
import sys
import json
import hashlib
import machine
import binascii

CONFIG_FILE = "bootloader_config.json"


def set_bootloader_mode(mode: str):
    # Read current config (or use defaults)
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except OSError:
        config = {"mode": "pump"}

    # Update the mode
    # mode has to be either "pump" or "autosampler" or "update_firmware"
    if mode not in ["pump", "autosampler", "update_firmware", "potentiostat"]:
        raise ValueError(
            "Invalid mode. Must be 'pump', 'autosampler', 'potentiostat', or 'update_firmware'."
        )
    if mode == "update_firmware":
        config["mode_before"] = config.get("mode", "pump")
    config["mode"] = mode
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def exit_bootloader_settings():
    # Read current config (or use defaults)
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except OSError:
        config = {"mode": "pump"}

    # Update the flag to exit bootloader settings mode
    config["mode"] = config.get("mode_before", "pump")
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

    # Reset the board to start the main application
    machine.reset()


def update_firmware():
    def blink_led():
        led = machine.Pin("LED", machine.Pin.OUT)
        led.toggle()

    # update firmware
    sys.stdout.write("Info: Awaiting firmware update JSON payload...\n")
    timer = machine.Timer()
    timer.init(period=500, mode=machine.Timer.PERIODIC, callback=lambda t: blink_led())

    filename = None
    file_handler = None
    file_checksum = hashlib.sha256()
    total_received = 0

    # function to reset the instance field
    def reset_fields():
        nonlocal filename, file_handler, file_checksum, total_received
        filename = None
        if file_handler:
            try:
                file_handler.close()
            except Exception:
                pass
            file_handler = None
        file_checksum = hashlib.sha256()
        total_received = 0

    while True:
        gc.collect()
        header_line = sys.stdin.readline().strip()
        if not header_line:
            continue
        try:
            payload = json.loads(header_line)
        except Exception as e:
            sys.stdout.write(f"Error: Invalid JSON payload received, error: {e}.\n")
            continue
        # Report available space on the disk if request_disc_available_space is True
        if payload.get("request_disc_available_space", False):
            stat = os.statvfs(os.getcwd())
            total = stat[0] * stat[2]
            free = stat[1] * stat[3]
            sys.stdout.write(
                f"Info: Available space on the disk: {free} bytes, total space: {total} bytes.\n"
            )
            continue
        # Report all files state as dict, with filename as key and os.stat as value
        if payload.get("request_dir_list", False):
            sys.stdout.write("Info: Requesting directory list...\n")
            files = os.listdir(os.getcwd())
            file_list = {}
            for file in files:
                file_list[file] = os.stat(file)
            sys.stdout.write(f"Info: Directory list: {json.dumps(file_list)}\n")
            continue
        # Report current available memory if request_memory is True
        if payload.get("request_memory", False):
            # perform a gc.collect() to free up memory
            gc.collect()
            free_memory = gc.mem_free()
            allocated_memory = gc.mem_alloc()
            sys.stdout.write(
                f"Info: free Memory {free_memory} bytes, total Memory {allocated_memory + free_memory} bytes.\n"
            )
            continue
        # Remove a file if remove_file_request is True
        if payload.get("remove_file_request", False):
            filename = payload.get("filename", None)
            if filename:
                try:
                    os.remove(filename)
                    sys.stdout.write(f"Success: Removed file {filename}.\n")
                except Exception as e:
                    sys.stdout.write(f"Error: Failed to remove file {filename}: {e}.\n")
            continue
        # Restart the file transfer if restart is True
        if payload.get("restart", False):
            reset_fields()
            sys.stdout.write("Success: Restarting file transfer...\n")
            continue
        # If the sender indicates the entire update is complete, then reboot.
        if payload.get("reset", False):
            sys.stdout.write("Info: Firmware update complete. Rebooting...\n")
            reset_fields()
            exit_bootloader_settings()

        # If a new file update is starting, update the filename, reset the buffer.
        if "filename" in payload and payload["filename"] != filename:
            reset_fields()
            filename = payload["filename"]
            file_handler = open(filename, "wb")
            sys.stdout.write(f"Info: Starting a new file update: {filename}\n")

        # get the chunk data
        chunk_size = int(payload.get("chunk_size", 0))
        chunk_data_b64 = payload.get("chunk_data_b64", None)
        if chunk_data_b64:
            # first decode the base64 data
            try:
                chunk_data = binascii.a2b_base64(chunk_data_b64)
            except Exception as e:
                sys.stdout.write(
                    f"Error: Failed to decode base64 chunk data for {filename}, error: {e}.\n"
                )
                continue
            try:
                # append the data to the file
                file_handler.write(chunk_data)
                file_handler.flush()
                file_checksum.update(chunk_data)
                total_received += len(chunk_data)
            except Exception as e:
                sys.stdout.write(
                    f"Error: Failed to write chunk data for {filename}, error: {e}.\n"
                )
            # check if the transfer is complete
            if not payload.get("finish", False):
                sys.stdout.write(
                    f"Success: Received chunk of size {chunk_size}, total received {total_received} bytes.\n"
                )
                continue

        expected_size = int(payload.get("size", 0))
        # Check if the received file size matches the expected size.
        if total_received != expected_size:
            sys.stdout.write(
                f"Error: Size mismatch for {filename}, received {total_received}, expected {expected_size} bytes.\n"
            )
            reset_fields()
            continue
        # Compute the SHA-256 checksum of the received file content.
        computed_checksum = binascii.hexlify(file_checksum.digest()).decode()
        expected_checksum = payload.get("checksum", None)
        if computed_checksum != expected_checksum:
            sys.stdout.write(
                f"Error: Checksum mismatch for {filename}: computed {computed_checksum} vs expected {expected_checksum}.\n"
            )
            reset_fields()
            continue
        sys.stdout.write(
            f"Success: finished receiving {filename} of size {total_received} bytes.\n"
        )
        reset_fields()
        continue


if __name__ == "__main__":
    update_firmware()
