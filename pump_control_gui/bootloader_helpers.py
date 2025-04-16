import os
import re
import json
import time
import base64
import serial
import hashlib
import logging
from tkinter_helpers import (
    non_blocking_messagebox,
    non_blocking_custom_messagebox,
    non_blocking_checklist,
    non_blocking_single_select,
    non_blocking_input_dialog,
)


# enter the bootloader by sending a json with set_mode as update_firmware and later rebooting the device
def enter_bootloader(serial_port_obj: serial.Serial):
    # set a "0:set_mode:update_firmware" command to the serial port
    if not serial_port_obj.is_open:
        return
    try:
        serial_port_obj.write(b"0:set_mode:update_firmware\n")
        # get the response from the serial port
        response = serial_port_obj.readline().decode().strip()
        logging.debug(f"Device -> PC: {response}")
        if "Success" in response:
            # set "0:reset" command to the serial port
            serial_port_obj.write(b"0:reset\n")
            # get the response from the serial port
            response = serial_port_obj.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
    except Exception as e:
        logging.error(f"Error: {e}")


# reboot the device by sending a json with reset as true, the device will reboot into the original state
def enter_controller(serial_port: serial.Serial) -> bool:
    header = {
        "reset": True,
    }
    message = (json.dumps(header) + "\n").encode()
    serial_port.write(message)
    while True:
        try:
            response = serial_port.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
            if "Info: Firmware update complete." in response:
                return True
            if "Error: " in response:
                return False
        except Exception as e:
            logging.error(f"Error: {e}")
            break
    return False


def reset_board(serial_port_obj: serial.Serial):
    if not serial_port_obj and not serial_port_obj.is_open:
        return
    """Reset the board by sending a soft reset command over serial. ONLY WORKS with MicroPython."""
    pythonInject = [
        "import machine",
        "machine.reset()",
    ]
    # interrupt the currently running code
    serial_port_obj.write(b"\x03")  # Ctrl+C
    # just consumed all the output until the prompt, try up to 10 seconds
    time_start = time.time()
    while time.time() - time_start < 10:
        line = serial_port_obj.readline().decode("utf-8").strip()
        if "MicroPython v" in line:
            break
    serial_port_obj.write(b"\x01")  # switch to raw REPL mode & inject code
    time.sleep(0.1)
    time_start = time.time()
    while time.time() - time_start < 10:
        line = serial_port_obj.readline().decode("utf-8").strip()
        if ">>>" in line:
            break
    for code in pythonInject:
        serial_port_obj.write(bytes(code + "\n", "utf-8"))
    serial_port_obj.write(b"\x04")  # exit raw REPL and run injected code
    serial_port_obj.close()
    time.sleep(1)


# request available space on the disk by sending a json with request_disc_available_space as true
def request_disc_available_space(serial_port: serial.Serial) -> tuple[int, int]:
    """Request the available space on the disk."""
    # send a json with request_disc_available_space as true
    header = {
        "request_disc_available_space": True,
    }
    message = (json.dumps(header) + "\n").encode()
    serial_port.write(message)
    while True:
        try:
            response = serial_port.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
            if "Info: Available space" in response:
                # return format "Device -> PC: Info: Available space on the disk: 1228800 bytes, total space: 1441792 bytes."
                match = re.search(r"(\d+) bytes, total space: (\d+) bytes", response)
                if match:
                    available_space = int(match.group(1))
                    total_space = int(match.group(2))
                    return available_space, total_space
        except Exception as e:
            logging.error(f"Error: {e}")
            break
    return 0, 0


# request all files stat on the disk by sending a json with request_dir_list as true
def request_dir_list(serial_port: serial.Serial) -> dict:
    header = {
        "request_dir_list": True,
    }
    message = (json.dumps(header) + "\n").encode()
    serial_port.write(message)
    while True:
        try:
            response = serial_port.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
            if "Info: Directory list" in response:
                # return format "Device -> PC: Info: Directory list: "start of a directory"
                match = re.search(r"Info: Directory list: (.*)$", response)
                if match:
                    output = json.loads(match.group(1))
                    return output
        except Exception as e:
            logging.error(f"Error: {e}")
            break
    return {}


# request available memory on the device by sending a json with request_memory as true
def request_memory(serial_port: serial.Serial) -> tuple[int, int]:
    header = {
        "request_memory": True,
    }
    message = (json.dumps(header) + "\n").encode()
    serial_port.write(message)
    while True:
        try:
            response = serial_port.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
            if "Info: free Memory" in response:
                # return format "Device -> PC: Info: free Memory 218864 bytes, total Memory 233024 bytes."
                match = re.search(r"(\d+) bytes, total Memory (\d+) bytes", response)
                if match:
                    free_memory = int(match.group(1))
                    total_memory = int(match.group(2))
                    return free_memory, total_memory
        except Exception as e:
            logging.error(f"Error: {e}")
            break
    return 0, 0


# request removal of a file by sending a json with remove_file_request as true
def remove_file(serial_port: serial.Serial, filename: str, messagebox_parent) -> bool:
    header = {
        "remove_file_request": True,
        "filename": filename,
    }
    message = (json.dumps(header) + "\n").encode()
    serial_port.write(message)
    while True:
        try:
            response = serial_port.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
            if "Success: Removed file" in response:
                non_blocking_messagebox(
                    parent=messagebox_parent,
                    title="Success",
                    message=f"File {filename} removed successfully.",
                )
                return True
            if "Error: " in response:
                non_blocking_messagebox(
                    parent=messagebox_parent,
                    title="Error",
                    message=f"Error removing file {filename}: {response}",
                )
                return False
        except Exception as e:
            logging.error(f"Error: {e}")
            break
    return False


# clear the remote controller file transfer buffer by sending a json with clear_file_transfer_buffer as true
def restart_file_transfer(serial_port: serial.Serial):
    header = {
        "restart": True,
    }
    message = (json.dumps(header) + "\n").encode()
    serial_port.write(message)
    while True:
        try:
            response = serial_port.readline().decode().strip()
            logging.debug(f"Device -> PC: {response}")
            if "Success: Restarting file transfer" in response:
                return True
            if "Error: " in response:
                return False
        except Exception as e:
            logging.error(f"Error: {e}")
            break
    return False


# send a file to the device by sending a json with send_file_request as true
# using 10% of the free memory as chunk size, cap to the nearest power of 2
# the file will be split into chunks and sent as base64 encoded json messages
# the device will respond with a success message or an error message for each chunk
# the device will also respond with a success message when the file transfer is complete
def upload_file(serial_port: serial.Serial, file_path, message_parent) -> bool:
    restart_file_transfer(serial_port)
    available_space, _ = request_disc_available_space(serial_port)
    free_memory, _ = request_memory(serial_port)
    CHUNK_SIZE = int(free_memory * 0.1)

    # Read the file to be transferred
    with open(file_path, "rb") as f:
        file_content = f.read()
    file_size = len(file_content)
    if file_size > available_space:
        message = f"Error: Not enough space on the device to transfer {file_path}"
        non_blocking_messagebox(
            parent=message_parent,
            title="Error",
            message=message,
        )
        logging.debug(message)
        return False
    # resize CHUNK_SIZE to the power of 2
    CHUNK_SIZE = 2 ** (CHUNK_SIZE.bit_length() - 1)
    if file_size < CHUNK_SIZE:
        CHUNK_SIZE = file_size
    # Split the file into chunks
    chunks = [file_content[i : i + CHUNK_SIZE] for i in range(0, file_size, CHUNK_SIZE)]
    logging.debug(
        f"file size {file_size} bytes, select chunk size of {CHUNK_SIZE} bytes, {len(chunks)} chunks total"
    )

    # Send header message with the filename
    default_header = {
        "filename": os.path.basename(file_path),
        "finish": False,
    }

    # Send each chunk as a JSON message
    for i, chunk in enumerate(chunks):
        # Encode the chunk in base64
        chunk_b64 = base64.b64encode(chunk).decode()
        # Create a JSON message with the chunk info
        chunk_msg = default_header.copy()
        chunk_msg["chunk_size"] = str(len(chunk))
        chunk_msg["chunk_data_b64"] = chunk_b64
        # if this is the last chunk, set finish to True
        if i == len(chunks) - 1:
            checksum = hashlib.sha256(file_content).hexdigest()
            chunk_msg["checksum"] = checksum
            chunk_msg["size"] = file_size
            chunk_msg["finish"] = True
        message = (json.dumps(chunk_msg) + "\n").encode()
        serial_port.write(message)
        logging.debug(f"PC -> Device: Sent chunk {i} of size {len(chunk)} bytes")
        # read the response from the device, block reading
        while True:
            try:
                response = serial_port.readline().decode().strip()
                logging.debug(f"Device -> PC: {response}")
                if "Success: finished receiving" in response:
                    message = (
                        f"File {os.path.basename(file_path)} uploaded successfully."
                    )
                    non_blocking_messagebox(
                        parent=message_parent,
                        title="Success",
                        message=message,
                    )
                    logging.debug(message)
                    return True
                if "Success: Received chunk" in response:
                    break
                if "Error: " in response:
                    message = f"Error: {response}"
                    non_blocking_messagebox(
                        parent=message_parent,
                        title="Error",
                        message=message,
                    )
                    logging.error(message)
                    return False
            except Exception as e:
                message = f"Error: {e}"
                non_blocking_messagebox(
                    parent=message_parent,
                    title="Error",
                    message=message,
                )
                logging.error(message)
                break
    return False
