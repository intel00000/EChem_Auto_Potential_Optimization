import sys
import json
import hashlib
import machine
import binascii
from bootloader_util import set_bootloader_mode

CONFIG_FILE = "bootloader_config.json"


def update_firmware():
    # update firmware
    sys.stdout.write("Info: Awaiting firmware update JSON payload...\n")

    filename = None
    file_handler = None
    file_checksum = hashlib.sha256()
    total_received = 0

    # define a function here to reset the instance field
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

    # the format will be in json
    # the other side will first send a json with the file name, checksum and size
    # e.g.
    # { filename: "pump_control_pico.py", size: "size of the file in bytes", chunk_index: 1, chunk_size: 1024, chunk_data_b64: file content in base64, checksum: "checksum using sha256", finish: "False", reset: "False" }
    # with chunks indicating the number of chunks and chunk_size indicating the size of each chunk
    # then the other side will send the gzipped file content in chunks
    # once received here, we will perform a checksum and size check
    # if the other side sends a json with "finish": "True", this mean the transfer for this file is complete, we will perform the checksum and size check, then write the file to flash, then send back a success message
    # if the checksum and size do not match, we will send back a failure message and request the file again
    # if the other side sends a json with "reset": "True", this mean the entire update is complete, we will perform machine.reset()
    while True:
        header_line = sys.stdin.readline().strip()
        if not header_line:
            continue
        try:
            payload = json.loads(header_line)
        except Exception as e:
            sys.stdout.write(f"Error: Invalid JSON payload received, error: {e}.\n")
            continue
        # If the sender indicates the entire update is complete, then reboot.
        if payload.get("reset", False):
            sys.stdout.write("Info: Firmware update complete. Rebooting...\n")
            reset_fields()
            set_bootloader_mode("pump")
            machine.reset()

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


def create_default_config() -> dict:
    default_config = {"enter_bootloader_setting": False, "mode": "pump"}
    with open(CONFIG_FILE, "w") as f:
        f.write(json.dumps(default_config))
    return default_config


def bootloader():
    # Try to read the config file
    try:
        with open(CONFIG_FILE, "r") as f:
            config_data = f.read()
    except OSError:
        # config file does not exist, create it with default values
        config_data = json.dumps(create_default_config())

    # Parse the config
    try:
        config = json.loads(config_data)
    except ValueError:
        # recreate the config file with default values
        config = create_default_config()

    # Check if the bootloader is active
    if not config.get("enter_bootloader_setting", False):
        mode = config.get("mode", "pump")
        if mode == "pump":
            import pump_control_pico

            pump_control_pico.main()
        elif mode == "autosampler":
            import autosampler_control_pico

            autosampler_control_pico.main()
        elif mode == "update_firmware":
            update_firmware()
        else:
            # Invalid mode, revert to default firmware
            import pump_control_pico

            pump_control_pico.main()


if __name__ == "__main__":
    bootloader()
