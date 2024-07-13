import serial
import serial.tools.list_ports
import logging
from datetime import datetime
from queue import Queue
import pandas as pd
import re
import time
import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit

# Define Pi Pico vendor ID
pico_vid = 0x2E8A

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')

class PicoControllerBackend:
    def __init__(self):
        self.timeout = 1  # Serial port timeout in seconds
        self.main_loop_interval = 100  # Main loop interval in milliseconds

        # Instance fields for the serial port and queue
        self.serial_port = None
        self.current_port = None

        # A queue to store commands to be sent to the Pico
        self.send_command_queue = Queue()

        # Dictionary to store pump information
        self.pumps = {}

        self.recipe_df = pd.DataFrame()
        self.recipe_rows = []

        # Time stamp for the start of the procedure
        self.start_time = -1
        self.total_procedure_time = -1

        # Set up logging
        runtime = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.mkdir("log")
        except FileExistsError:
            pass
        log_filename = os.path.join("log", f"pico_controller_run_{runtime}.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s: %(message)s [%(funcName)s]",
            handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
        )

    def refresh_ports(self):
        return [port.device for port in serial.tools.list_ports.comports() if port.vid == pico_vid]

    def connect_to_pico(self, selected_port):
        if selected_port:
            if self.serial_port:
                self.disconnect_pico(show_message=False)
            try:
                self.serial_port = serial.Serial(selected_port, timeout=self.timeout)
                self.current_port = selected_port
                logging.info(f"Connected to {selected_port}")
                self.query_pump_info()
                self.update_status()
                return True
            except serial.SerialException:
                logging.error(f"Failed to connect to {selected_port}")
                return False

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None
            logging.info("Disconnected from Pico")

    def query_pump_info(self):
        if self.serial_port:
            self.send_command_queue.put("0:info")

    def update_status(self):
        if self.serial_port:
            self.send_command_queue.put("0:st")

    def toggle_power(self, pump_id):
        if self.serial_port:
            self.send_command_queue.put(f"{pump_id}:pw")
            self.update_status()

    def toggle_direction(self, pump_id):
        if self.serial_port:
            self.send_command_queue.put(f"{pump_id}:di")
            self.update_status()

    def send_command(self):
        try:
            if self.serial_port and not self.send_command_queue.empty():
                command = self.send_command_queue.get(block=True, timeout=None)
                self.serial_port.write(f"{command}\n".encode())
                logging.info(f"PC -> Pico: {command}")
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Connection to Pico lost: {e}")
        except Exception as e:
            logging.error(f"Send_command: An error occurred: {e}")

    def read_serial(self):
        try:
            if self.serial_port and self.serial_port.in_waiting:
                response = self.serial_port.readline().decode("utf-8").strip()
                logging.info(f"Pico -> PC: {response}")
                if "Info" in response:
                    return self.create_pump_widgets(response)
                elif "Status" in response:
                    return self.update_pump_status(response)
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Connection to Pico lost: {e}")
        except Exception as e:
            logging.error(f"Read_serial: An error occurred: {e}")

    def create_pump_widgets(self, response):
        self.pumps = {}
        info_pattern = re.compile(
            r"Pump(\d+) Info: Power Pin ID: (\d+), Direction Pin ID: (\d+), Initial Power Status: (ON|OFF), Initial Direction Status: (CW|CCW)"
        )
        matches = info_pattern.findall(response)
        matches = sorted(matches, key=lambda x: int(x[0]))

        for match in matches:
            pump_id, power_pin, direction_pin, initial_power, initial_direction = match
            pump_id = int(pump_id)
            self.pumps[pump_id] = {
                "power_pin": power_pin,
                "direction_pin": direction_pin,
                "power_status": initial_power,
                "direction_status": initial_direction,
            }
        return self.pumps

    def update_pump_status(self, response):
        status_pattern = re.compile(
            r"Pump(\d+) Status: Power: (ON|OFF), Direction: (CW|CCW)"
        )
        matches = status_pattern.findall(response)
        for match in matches:
            pump_id, power_status, direction_status = match
            pump_id = int(pump_id)
            if pump_id in self.pumps:
                self.pumps[pump_id]["power_status"] = power_status
                self.pumps[pump_id]["direction_status"] = direction_status
        return self.pumps

    def load_recipe(self, file_path):
        try:
            if file_path.endswith(".csv"):
                self.recipe_df = pd.read_csv(file_path, keep_default_na=False, engine="python")
            elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                self.recipe_df = pd.read_excel(file_path, keep_default_na=False, engine="openpyxl")
            else:
                raise ValueError("Invalid file format.")
            logging.info(f"Recipe file loaded successfully: {file_path}")
            return self.recipe_df
        except Exception as e:
            logging.error(f"Failed to load recipe file {file_path}: {e}")
            return None

    def start_procedure(self):
        if self.recipe_df is None:
            return False
        if not self.serial_port:
            return False
        logging.info("Starting procedure...")
        self.total_procedure_time = self.recipe_df["Time point (min)"].max() * 60
        self.start_time = time.time()
        self.execute_procedure()
        return True

    def execute_procedure(self, index=0):
        if index >= len(self.recipe_df):
            self.start_time = -1
            self.total_procedure_time = -1
            logging.info("Procedure completed.")
            return "Procedure Complete"

        row = self.recipe_df.iloc[index]
        target_time = float(row["Time point (min)"]) * 60

        elapsed_time = time.time() - self.start_time
        current_step_remaining_time = target_time - elapsed_time
        intended_sleep_time = max(100, int(current_step_remaining_time * 1000 / 2))
        if elapsed_time < target_time:
            time.sleep(intended_sleep_time / 1000)
            self.execute_procedure(index)
            return

        logging.info(f"executing step at index {index}")
        pump_actions = {col: row[col] for col in row.index if col.startswith("Pump")}
        valve_actions = {col: row[col] for col in row.index if col.startswith("Valve")}
        self.update_status()
        self.execute_actions(index, pump_actions, valve_actions)
        self.execute_procedure(index + 1)

    def execute_actions(self, index, pump_actions, valve_actions):
        for pump, action in pump_actions.items():
            if pd.isna(action) or action == "":
                continue
            pump_id = int(re.search(r"\d+", pump).group())
            if (
                pump_id in self.pumps
                and action.lower() != self.pumps[pump_id]["power_status"].lower()
            ):
                logging.info(
                    f"At index {index}, pump_id {pump_id} status: {self.pumps[pump_id]['power_status']}, intended status: {action}, toggling power."
                )
                self.toggle_power(pump_id)

        for valve, action in valve_actions.items():
            if pd.isna(action) or action == "":
                continue
            valve_id = int(re.search(r"\d+", valve).group())
            if (
                valve_id in self.pumps
                and action.upper() != self.pumps[valve_id]["direction_status"].upper()
            ):
                logging.info(
                    f"At index {index}, valve_id {valve_id} status: {self.pumps[valve_id]['direction_status']}, intended status: {action}, toggling direction."
                )
                self.toggle_direction(valve_id)

        self.update_status()

    def update_progress(self):
        if (
            self.total_procedure_time == -1
            or self.recipe_df is None
            or self.recipe_df.empty
        ):
            return {"total_progress": 0, "remaining_time": 0}
        elapsed_time = time.time() - self.start_time
        total_progress = int((elapsed_time / self.total_procedure_time) * 100)
        remaining_time = int(self.total_procedure_time - elapsed_time)

        progress_info = {
            "total_progress": total_progress,
            "remaining_time": remaining_time,
            "recipe_progress": []
        }

        for i in range(len(self.recipe_df)):
            row = self.recipe_df.iloc[i]
            time_stamp = float(row["Time point (min)"]) * 60
            if elapsed_time < time_stamp:
                break
            if i < len(self.recipe_df) - 1:
                next_row = self.recipe_df.iloc[i + 1]
                next_time_stamp = float(next_row["Time point (min)"]) * 60
                time_interval = next_time_stamp - time_stamp
                row_progress = min(
                    100, int(((elapsed_time - time_stamp) / time_interval) * 100)
                )
                remaining_time_row = max(0, int(next_time_stamp - elapsed_time))
            else:
                row_progress = 100
                remaining_time_row = 0
            progress_info["recipe_progress"].append(
                {
                    "index": i,
                    "progress": row_progress,
                    "remaining_time": remaining_time_row,
                    "data": row.to_dict(),
                }
            )
        return progress_info


controller = PicoControllerBackend()

@app.route('/refresh_ports')
def refresh_ports():
    ports = controller.refresh_ports()
    return jsonify({"ports": ports})

@app.route('/connect', methods=['POST'])
def connect():
    data = request.json
    selected_port = data.get("port")
    success = controller.connect_to_pico(selected_port)
    return jsonify({"success": success})

@app.route('/disconnect', methods=['POST'])
def disconnect():
    controller.disconnect_pico()
    return jsonify({"success": True})

@app.route('/toggle_power', methods=['POST'])
def toggle_power():
    data = request.json
    pump_id = data.get("pump_id")
    controller.toggle_power(pump_id)
    return jsonify({"success": True})

@app.route('/toggle_direction', methods=['POST'])
def toggle_direction():
    data = request.json
    pump_id = data.get("pump_id")
    controller.toggle_direction(pump_id)
    return jsonify({"success": True})

@app.route('/load_recipe', methods=['POST'])
def load_recipe():
    data = request.json
    file_path = data.get("file_path")
    recipe_df = controller.load_recipe(file_path)
    if recipe_df is not None:
        return jsonify({"success": True, "recipe": recipe_df.to_dict()})
    return jsonify({"success": False})

@app.route('/start_procedure', methods=['POST'])
def start_procedure():
    success = controller.start_procedure()
    return jsonify({"success": success})

@app.route('/progress')
def progress():
    progress_info = controller.update_progress()
    return jsonify(progress_info)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, async_mode='eventlet', use_reloader=False, log_output=True)