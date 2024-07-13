# backend.py

import serial
import serial.tools.list_ports
import os
import re
import time
import logging
from datetime import datetime
from queue import Queue
import pandas as pd

# Define Pi Pico vendor ID
pico_vid = 0x2E8A

class PicoControllerBackend:
    def __init__(self, update_pump_widgets_callback, update_pump_status_callback):
        self.serial_port = None
        self.current_port = None
        self.send_command_queue = Queue()
        self.pumps = {}
        self.recipe_df = pd.DataFrame()
        self.recipe_rows = []
        self.start_time = -1
        self.total_procedure_time = -1
        self.main_loop_interval = 100
        self.last_port_refresh = -1
        self.port_refresh_interval = 5
        self.update_pump_widgets_callback = update_pump_widgets_callback
        self.update_pump_status_callback = update_pump_status_callback

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

    def main_loop(self):
        self.refresh_ports()
        self.read_serial()
        self.send_command()
        self.update_progress()

    def refresh_ports(self):
        if not self.serial_port:
            if time.time() - self.last_port_refresh < self.port_refresh_interval:
                return
            ports = [port.device + "(" + str(port.serial_number) + ")" for port in serial.tools.list_ports.comports() if port.vid == pico_vid]
            for port in serial.tools.list_ports.comports():
                logging.info(f"name: {port.name}, description: {port.description}, device: {port.device}, hwid: {port.hwid}, manufacturer: {port.manufacturer}, pid: {hex(port.pid)}, serial_number: {port.serial_number}, vid: {hex(port.vid)}")
            self.ports = ports
            self.last_port_refresh = time.time()

    def get_ports(self):
        return self.ports

    def connect_to_pico(self, selected_port):
        if self.serial_port:
            self.disconnect_pico(False)

        try:
            self.serial_port = serial.Serial(selected_port.split("(")[0], timeout=1)
            self.current_port = selected_port
            logging.info(f"Connected to {selected_port}")
            self.query_pump_info()
            self.update_status()
        except serial.SerialException:
            logging.error(f"Failed to connect to {selected_port}")

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None
            self.pumps = {}
            self.recipe_df = pd.DataFrame()
            self.recipe_rows = []
            if show_message:
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
                    self.update_pump_widgets_callback(response)
                elif "Status" in response:
                    self.update_pump_status_callback(response)
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Connection to Pico lost: {e}")
        except Exception as e:
            logging.error(f"Read_serial: An error occurred: {e}")

    def load_recipe(self, file_path):
        try:
            if file_path.endswith(".csv"):
                self.recipe_df = pd.read_csv(file_path, keep_default_na=False, engine="python")
            elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                self.recipe_df = pd.read_excel(file_path, keep_default_na=False, engine="openpyxl")
            else:
                raise ValueError("Invalid file format.")
            logging.info(f"Recipe file loaded successfully: {file_path}")
        except Exception as e:
            logging.error(f"Failed to load recipe file {file_path}: {e}")

    def start_procedure(self):
        if self.recipe_df is None or self.recipe_df.empty:
            return
        self.total_procedure_time = self.recipe_df["Time point (min)"].max() * 60
        self.start_time = time.time()
        self.execute_procedure()

    def execute_procedure(self, index=0):
        if index >= len(self.recipe_df):
            self.start_time = -1
            self.total_procedure_time = -1
            logging.info("Procedure completed.")
            return

        row = self.recipe_df.iloc[index]
        target_time = float(row["Time point (min)"]) * 60

        elapsed_time = time.time() - self.start_time
        current_step_remaining_time = target_time - elapsed_time
        intended_sleep_time = max(100, int(current_step_remaining_time * 1000 / 2))
        if elapsed_time < target_time:
            self.master.after(intended_sleep_time, self.execute_procedure, index)
            return

        logging.info(f"Executing step at index {index}")

        pump_actions = {col: row[col] for col in row.index if col.startswith("Pump")}
        valve_actions = {col: row[col] for col in row.index if col.startswith("Valve")}

        self.update_status()
        self.execute_actions(index, pump_actions, valve_actions)

    def execute_actions(self, index, pump_actions, valve_actions):
        for pump, action in pump_actions.items():
            if pd.isna(action) or action == "":
                continue
            pump_id = int(re.search(r"\d+", pump).group())
            if pump_id in self.pumps and action.lower() != self.pumps[pump_id]["power_status"].lower():
                logging.info(f"At index {index}, pump_id {pump_id} status: {self.pumps[pump_id]['power_status']}, intended status: {action}, toggling power.")
                self.toggle_power(pump_id)

        for valve, action in valve_actions.items():
            if pd.isna(action) or action == "":
                continue
            valve_id = int(re.search(r"\d+", valve).group())
            if valve_id in self.pumps and action.upper() != self.pumps[valve_id]["direction_status"].upper():
                logging.info(f"At index {index}, valve_id {valve_id} status: {self.pumps[valve_id]['direction_status']}, intended status: {action}, toggling direction.")
                self.toggle_direction(valve_id)

        self.update_status()
        self.execute_procedure(index + 1)

    def update_progress(self):
        if self.total_procedure_time == -1 or self.recipe_df is None or self.recipe_df.empty:
            return
        elapsed_time = time.time() - self.start_time
        total_progress = int((elapsed_time / self.total_procedure_time) * 100)

        remaining_time = int(self.total_procedure_time - elapsed_time)
        self.update_progress_bar(total_progress, remaining_time)

        for i, child in self.recipe_rows:
            row = self.recipe_df.iloc[i]
            time_stamp = float(row["Time point (min)"]) * 60
            if elapsed_time < time_stamp:
                break
            else:
                if i < len(self.recipe_df) - 1:
                    next_row = self.recipe_df.iloc[i + 1]
                    next_time_stamp = float(next_row["Time point (min)"]) * 60
                    time_interval = next_time_stamp - time_stamp
                    row_progress = min(100, int(((elapsed_time - time_stamp) / time_interval) * 100))
                    remaining_time_row = max(0, int(next_time_stamp - elapsed_time))
                else:
                    row_progress = 100
                    remaining_time_row = 0
                self.update_recipe_row(child, list(row), row_progress, remaining_time_row)

    def update_progress_bar(self, total_progress, remaining_time):
        # This method should be implemented in the frontend class to update the progress bar
        pass

    def update_recipe_row(self, child, row, row_progress, remaining_time_row):
        # This method should be implemented in the frontend class to update the recipe table
        pass