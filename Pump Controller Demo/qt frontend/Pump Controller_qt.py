# pyserial imports
import serial

# weird that I have to import serial again here, wtf
import serial.tools.list_ports

# gui imports
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

# other library
import os
import re
import time
import logging
from datetime import datetime
from queue import Queue
import pandas as pd

# Define Pi Pico vendor ID
pico_vid = 0x2E8A

class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        # port refresh timer
        self.last_port_refresh = -1
        self.port_refersh_interval = 5  # Refresh rate for COM ports when not connected
        self.timeout = 1  # Serial port timeout in seconds
        self.main_loop_interval = 50  # Main loop interval in milliseconds

        # instance fields for the serial port and queue
        self.serial_port = None
        self.current_port = None

        # a queue to store commands to be sent to the Pico
        self.send_command_queue = Queue()

        # Dictionary to store pump information
        self.pumps = {}

        self.recipe_df = pd.DataFrame()
        self.recipe_rows = []

        # time stamp for the start of the procedure
        self.start_time = -1
        self.total_procedure_time = -1
        self.current_index = -1
        self.pause_timepoint = -1
        self.pause_duration = 0
        self.scheduled_task = None

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

        self.create_widgets()
        self.master.after(self.main_loop_interval, self.main_loop)

    def create_widgets(self):
        # First frame for selecting the port
        self.select_port_frame = ttk.Labelframe(self.master, text="Select Port", padding=(10, 10, 10, 10))
        self.select_port_frame.grid(
            row=0, column=0, columnspan=4, rowspan=2, padx=10, pady=10, sticky="NSEW"
        )

        # first row is for select_port_frame
        self.port_label = ttk.Label(self.select_port_frame, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=10, pady=10)
        self.port_combobox = ttk.Combobox(self.select_port_frame, state="readonly", width=50)
        self.port_combobox.grid(row=0, column=1, padx=10, pady=10)
        self.refresh_ports()
        if len(self.port_combobox["values"]) > 0:
            self.port_combobox.current(0)  # Default to the first port
        self.connect_button = ttk.Button(
            self.select_port_frame, text="Connect", command=self.connect_to_pico
        )
        self.connect_button.grid(row=0, column=2, padx=10, pady=10)
        self.disconnect_button = ttk.Button(
            self.select_port_frame, text="Disconnect", command=self.disconnect_pico
        )
        self.disconnect_button.grid(row=0, column=3, padx=10, pady=10)
        # disable the disconnect button
        self.disconnect_button.config(state=tk.DISABLED)

        # second row for select_port_frame
        self.status_label = ttk.Label(
            self.select_port_frame, text="Status: Not connected"
        )
        self.status_label.grid(
            row=1, column=0, padx=10, pady=10, columnspan=2, sticky="W"
        )

        # Second frame for manual control
        self.manual_control_frame = ttk.Labelframe(
            self.master, text="Manual Control", padding=(10, 10, 10, 10)
        )
        self.manual_control_frame.grid(
            row=2, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.manual_control_frame_buttons = ttk.Frame(self.manual_control_frame)
        self.manual_control_frame_buttons.grid(
            row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.add_pump_button = ttk.Button(
            self.manual_control_frame_buttons, text="Add Pump", command=self.add_pump
        )
        self.add_pump_button.grid(row=0, column=0, padx=10, pady=10, sticky="W")
        self.clear_pumps_button = ttk.Button(
            self.manual_control_frame_buttons, text="Clear All Pumps", command=self.clear_pumps
        )
        self.clear_pumps_button.grid(row=0, column=1, padx=10, pady=10, sticky="W")
        # Moved inside the manual control frame
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=1, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )

        # Third frame for the recipe and procedure execution
        self.recipe_frame = ttk.Labelframe(
            self.master, text="Recipe", padding=(10, 10, 10, 10)
        )
        self.recipe_frame.grid(
            row=3, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )

        # create a frame for the buttons
        self.recipe_frame_buttons = ttk.Frame(self.recipe_frame)
        self.recipe_frame_buttons.grid(
            row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.load_recipe_button = ttk.Button(
            self.recipe_frame_buttons, text="Load Recipe", command=self.load_recipe
        )
        self.load_recipe_button.grid(row=0, column=0, padx=10, pady=10)
        self.start_button = ttk.Button(
            self.recipe_frame_buttons, text="Start", command=self.start_procedure
        )
        self.start_button.grid(row=0, column=1, padx=10, pady=10)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button = ttk.Button(self.recipe_frame_buttons, text="Stop", command=self.stop_procedure)
        self.stop_button.grid(row=0, column=2, padx=10, pady=10)
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button = ttk.Button(self.recipe_frame_buttons, text="Pause", command=self.pause_procedure)
        self.pause_button.grid(row=0, column=3, padx=10, pady=10)
        self.pause_button.config(state=tk.DISABLED)
        self.continue_button = ttk.Button(self.recipe_frame_buttons, text="Continue", command=self.continue_procedure)
        self.continue_button.grid(row=0, column=4, padx=10, pady=10)
        self.continue_button.config(state=tk.DISABLED)
        # frame for the recipe table
        self.recipe_table_frame = ttk.Frame(self.recipe_frame)
        self.recipe_table_frame.grid(
            row=1, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.recipe_table = ttk.Frame(self.recipe_table_frame)
        self.recipe_table.grid(row=0, column=0, padx=10, pady=10, sticky="NSEW")
        self.scrollbar = ttk.Scrollbar()

        # Fourth frame for total progress bar and remaining time label
        self.progress_frame = ttk.Labelframe(
            self.master, text="Progress", padding=(10, 10, 10, 10)
        )
        self.progress_frame.grid(
            row=4, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.total_progress_label = ttk.Label(
            self.progress_frame, text="Total Progress:"
        )
        self.total_progress_label.grid(row=0, column=0, padx=10, pady=10, sticky="W")
        self.total_progress_bar = ttk.Progressbar(
            self.progress_frame, length=200, mode="determinate"
        )
        self.total_progress_bar.grid(row=0, column=1, padx=10, pady=10, sticky="W")
        self.remaining_time_label = ttk.Label(
            self.progress_frame, text="Remaining Time:"
        )
        self.remaining_time_label.grid(row=1, column=0, padx=10, pady=10, sticky="W")
        self.remaining_time_value = ttk.Label(self.progress_frame, text="")
        self.remaining_time_value.grid(row=1, column=1, padx=10, pady=10, sticky="W")

    def main_loop(self):
        self.refresh_ports()
        self.read_serial()
        self.send_command()
        self.update_progress()
        self.master.after(self.main_loop_interval, self.main_loop)

    def refresh_ports(self):
        if not self.serial_port:
            if time.time() - self.last_port_refresh < self.port_refersh_interval:
                return
            # filter by vendor id
            ports = [ port.device + " (" + str(port.serial_number) + ")" for port in serial.tools.list_ports.comports() if port.vid == pico_vid]
            # print detail information of the ports to the console
            for port in serial.tools.list_ports.comports():
                # put these into one line
                logging.info(f"name: {port.name}, description: {port.description}, device: {port.device}, hwid: {port.hwid}, manufacturer: {port.manufacturer}, pid: {hex(port.pid)}, serial_number: {port.serial_number}, vid: {hex(port.vid)}")

            self.port_combobox["values"] = ports
            self.last_port_refresh = time.time()

    def connect_to_pico(self):
        selected_port = self.port_combobox.get()
        if selected_port:

            # Check if already connected
            if self.serial_port:
                # if already connected, pop a confirmation message before disconnecting
                if (
                    messagebox.askyesno("Disconnect", "Disconnect from current port?")
                    == tk.YES
                ):
                    # suppress the message for the disconnect
                    self.disconnect_pico(show_message=False)
                else:
                    return

            # Attempt to connect to the selected port
            try:
                self.serial_port = serial.Serial(selected_port.split("(")[0], timeout=self.timeout)
                self.current_port = selected_port
                self.status_label.config(text=f"Status: Connected to {selected_port}")

                logging.info(f"Connected to {selected_port}")
                messagebox.showinfo(
                    "Connection Status", f"Successfully connected to {selected_port}"
                )

                # issue a pump info query
                self.query_pump_info()

                # enable the disconnect button
                self.disconnect_button.config(state=tk.NORMAL)

            except serial.SerialException:
                self.status_label.config(text="Status: Not connected")
                logging.error(f"Failed to connect to {selected_port}")
                messagebox.showerror(
                    "Connection Status", f"Failed to connect to {selected_port}"
                )

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            # close the serial port connection
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None

            # update UI
            self.status_label.config(text="Status: Not connected")

            # clear the pumps widgets
            self.clear_pumps_widgets()
            # clear the recipe table
            self.clear_recipe()

            # disable the disconnect button
            self.disconnect_button.config(state=tk.DISABLED)

            logging.info("Disconnected from Pico")
            if show_message:
                messagebox.showinfo(
                    "Disconnection Status", "Successfully disconnected from Pico"
                )

    def query_pump_info(self):
        if self.serial_port:
            # put the command in the queue
            self.send_command_queue.put("0:info")

    def update_status(self):
        if self.serial_port:
            # put the command in the queue
            self.send_command_queue.put("0:st")

    def toggle_power(self, pump_id):
        if self.serial_port:
            self.send_command_queue.put(f"{pump_id}:pw")
            self.update_status()

    def toggle_direction(self, pump_id):
        if self.serial_port:
            # put the command in the queue
            self.send_command_queue.put(f"{pump_id}:di")
            self.update_status()

    def register_pump(self, pump_id, power_pin, direction_pin, initial_power_pin_value, initial_direction_pin_value, initial_power_status, initial_direction_status):
        if self.serial_port:
            command = f"{pump_id}:reg:{power_pin}:{direction_pin}:{initial_power_pin_value}:{initial_direction_pin_value}:{initial_power_status}:{initial_direction_status}"
            self.send_command_queue.put(command)
            self.update_status()

    def clear_pumps(self):
        if self.serial_port:
            # pop a message to confirm the clear
            if messagebox.askyesno("Clear Pumps", "Clear all pumps?") == tk.YES:
                self.send_command_queue.put("0:clr")
                self.clear_pumps_widgets()

    def stop_procedure(self):
        if self.scheduled_task:
            self.master.after_cancel(self.scheduled_task)
            self.scheduled_task = None
        self.start_time = -1
        self.total_procedure_time = -1
        self.current_index = -1
        self.pause_timepoint = -1
        self.pause_duration = 0
        # disable the stop button
        self.stop_button.config(state=tk.DISABLED)
        # disable the pause button
        self.pause_button.config(state=tk.DISABLED)
        # disable the continue button
        self.continue_button.config(state=tk.DISABLED)
        logging.info("Procedure stopped.")
        messagebox.showinfo(
            "Procedure Stopped", "The procedure has been stopped."
        )

    def pause_procedure(self):
        if self.scheduled_task:
            self.master.after_cancel(self.scheduled_task)
            self.scheduled_task = None
        self.pause_timepoint = time.time()
        self.pause_button.config(state=tk.DISABLED)
        self.continue_button.config(state=tk.NORMAL)
        """ logging.info("Procedure paused.") """

    def continue_procedure(self):
        if self.pause_timepoint != -1:
            self.pause_duration += time.time() - self.pause_timepoint
            self.pause_timepoint = -1
        self.pause_button.config(state=tk.NORMAL)
        self.continue_button.config(state=tk.DISABLED)
        self.execute_procedure(self.current_index)
        logging.info("Procedure continued.")
        """ messagebox.showinfo(
            "Procedure Continued", "The procedure has been continued."
        ) """

    # this send_command will run in a loop, removing the first item from the queue and sending it, each sending will be a sleep of 0.1s
    def send_command(self):
        try:
            if self.serial_port and not self.send_command_queue.empty():
                command = self.send_command_queue.get(block=True, timeout=None)
                self.serial_port.write(f"{command}\n".encode())
                logging.info(f"PC -> Pico: {command}")
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Connection to Pico lost: {e}")
            messagebox.showerror(
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            messagebox.showerror("Error", f"Send_command: An error occurred: {e}")
            logging.error(f"Send_command: An error occurred: {e}")

    def read_serial(self):
        try:
            if self.serial_port and self.serial_port.in_waiting:
                response = self.serial_port.readline().decode("utf-8").strip()
                logging.info(f"Pico -> PC: {response}")
                if "Info" in response:
                    self.update_pump_widgets(response)
                elif "Status" in response:
                    self.update_pump_status(response)
                elif "Error" in response:
                    messagebox.showerror("Error", response)
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Connection to Pico lost: {e}")
            messagebox.showerror(
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            messagebox.showerror("Error", f"Read_serial: An error occurred: {e}")
            logging.error(f"Read_serial: An error occurred: {e}")

    def update_pump_widgets(self, response):
        info_pattern = re.compile(
            r"Pump(\d+) Info: Power Pin: (-?\d+), Direction Pin: (-?\d+), Initial Power Pin Value: (\d+), Initial Direction Pin Value: (\d+), Current Power Status: (ON|OFF), Current Direction Status: (CW|CCW)"
        )
        matches = info_pattern.findall(response)

        for match in matches:
            pump_id, power_pin, direction_pin, initial_power_pin_value, initial_direction_pin_value, power_status, direction_status = match
            pump_id = int(pump_id)
            if pump_id in self.pumps:
                self.pumps[pump_id].update({
                    "power_pin": power_pin,
                    "direction_pin": direction_pin,
                    "initial_power_pin_value": initial_power_pin_value,
                    "initial_direction_pin_value": initial_direction_pin_value,
                    "power_status": power_status,
                    "direction_status": direction_status,
                })

                pump_frame = self.pumps[pump_id]["frame"]
                pump_frame.grid(row=0, column=pump_id - 1, padx=10, pady=10, sticky="NS")

                self.pumps[pump_id]["power_label"].config(
                    text=f"Power Status: {power_status}"
                )
                self.pumps[pump_id]["direction_label"].config(
                    text=f"Direction Status: {direction_status}"
                )
                self.pumps[pump_id]["power_button"].config(
                    state="normal" if power_pin != "-1" else "disabled"
                )
                self.pumps[pump_id]["direction_button"].config(
                    state="normal" if direction_pin != "-1" else "disabled"
                )
                self.pumps[pump_id]["pump_label"].config(
                    text=f"Pump {pump_id}, Power pin: {power_pin}, Direction pin: {direction_pin}"
                )
            else:
                pump_frame = ttk.Labelframe(self.pumps_frame, text=f"Pump {pump_id}")
                pump_frame.grid(row=0, column=pump_id - 1, padx=10, pady=10, sticky="NS")

                pump_label = ttk.Label(
                    pump_frame,
                    text=f"Pump {pump_id}, Power pin: {'N/A' if power_pin == '-1' else power_pin}, Direction pin: {'N/A' if direction_pin == '-1' else direction_pin}",
                )
                pump_label.grid(row=0, column=0, padx=10, pady=10, sticky="NS")

                edit_button = ttk.Button(
                    pump_frame,
                    text="Edit",
                    command=lambda pid=pump_id: self.edit_pump(pid)
                )
                edit_button.grid(row=0, column=1, padx=10, pady=10, sticky="NS")

                power_label = ttk.Label(pump_frame, text=f"Power Status: {power_status}")
                power_label.grid(row=1, column=0, padx=10, pady=10, sticky="NS")

                direction_label = ttk.Label(
                    pump_frame, text=f"Direction Status: {direction_status}"
                )
                direction_label.grid(row=1, column=1, padx=10, pady=10, sticky="NS")

                power_button = ttk.Button(
                    pump_frame,
                    text="Toggle Power",
                    command=lambda pid=pump_id: self.toggle_power(pid),
                    state="disabled" if power_pin == "-1" else "normal"
                )
                power_button.grid(row=2, column=0, padx=10, pady=10, sticky="NS")

                direction_button = ttk.Button(
                    pump_frame,
                    text="Toggle Direction",
                    command=lambda pid=pump_id: self.toggle_direction(pid),
                    state="disabled" if direction_pin == "-1" else "normal"
                )
                direction_button.grid(row=2, column=1, padx=10, pady=10, sticky="NS")

                self.pumps[pump_id] = {
                    "power_pin": power_pin,
                    "direction_pin": direction_pin,
                    "initial_power_pin_value": initial_power_pin_value,
                    "initial_direction_pin_value": initial_direction_pin_value,
                    "power_status": power_status,
                    "direction_status": direction_status,

                    "frame": pump_frame,
                    "pump_label": pump_label,
                    "power_label": power_label,
                    "direction_label": direction_label,
                    "power_button": power_button,
                    "direction_button": direction_button,
                }

    # a function to clear all pumps
    def clear_pumps_widgets(self):
        for widget in self.pumps_frame.winfo_children():
            widget.destroy()
        # destroy the pumps frame
        self.pumps_frame.destroy()
        # recreate pumps frame inside the manual control frame
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=1, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.pumps = {}

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
                self.pumps[pump_id]["power_label"].config(
                    text=f"Power Status: {power_status}"
                )
                self.pumps[pump_id]["direction_label"].config(
                    text=f"Direction Status: {direction_status}"
                )

    def load_recipe(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            try:
                # clear the recipe table
                self.clear_recipe()
                if file_path.endswith(".csv"):
                    self.recipe_df = pd.read_csv(file_path, keep_default_na=False, engine="python")
                elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                    self.recipe_df = pd.read_excel(file_path, keep_default_na=False, engine="openpyxl")
                else:
                    raise ValueError("Invalid file format.")

                # display_recipe
                if self.recipe_df is None or self.recipe_df.empty:
                    logging.error("No recipe data to display.")
                    return

                columns = list(self.recipe_df.columns) + ["Progress Bar", "Remaining Time"]
                self.recipe_table = ttk.Treeview(
                    self.recipe_table_frame, columns=columns, show="headings"
                )

                # create a scrollbar
                self.scrollbar = ttk.Scrollbar(
                    self.recipe_table_frame,
                    orient="vertical",
                    command=self.recipe_table.yview
                )
                self.recipe_table.configure(yscrollcommand=self.scrollbar.set)
                self.scrollbar.grid(row=0, column=1, sticky="NS")

                self.recipe_table.grid(row=0, column=0, padx=10, pady=10, sticky="NSEW")
                for col in columns:
                    self.recipe_table.heading(col, text=col)
                    self.recipe_table.column(col, width=100, anchor="center")

                for index, row in self.recipe_df.iterrows():
                    values = list(row)
                    self.recipe_table.insert("", "end", values=values)
                    self.recipe_rows.append((index, self.recipe_table.get_children()[-1]))

                # double width for the notes column
                self.recipe_table.column("Notes", width=200, anchor="center")

                # enable the start button
                self.start_button.config(state=tk.NORMAL)

                logging.info(f"Recipe file loaded successfully: {file_path}")
                messagebox.showinfo(
                    "File Load", f"Recipe file loaded successfully: {file_path}"
                )
            except Exception as e:
                messagebox.showerror(
                    "File Load Error", f"Failed to load recipe file {file_path}: {e}"
                )
                logging.error(f"Failed to load recipe file {file_path}: {e}")

    # a function to clear the recipe table
    def clear_recipe(self):
        # clear the recipe table
        self.recipe_df = None
        self.recipe_rows = []
        # destroy the recipe table
        self.recipe_table.destroy()
        # destroy the scrollbar
        self.scrollbar.destroy()
        # recreate the recipe table
        self.recipe_table = ttk.Frame(self.recipe_table_frame)
        self.recipe_table.grid(row=0, column=0, padx=10, pady=10, sticky="NSEW")
        # clear the progress bar
        self.total_progress_bar["value"] = 0
        self.remaining_time_value.config(text="")

        # disable all procedure buttons
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)
        self.continue_button.config(state=tk.DISABLED)

    def start_procedure(self):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        if self.recipe_df is None:
            messagebox.showerror("Error", "No recipe file loaded.")
            return

        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        logging.info("Starting procedure...")

        # enable the stop button
        self.stop_button.config(state=tk.NORMAL)
        # enable the pause button
        self.pause_button.config(state=tk.NORMAL)
        # disable the continue button
        self.continue_button.config(state=tk.DISABLED)

        # clear the stop time and pause time
        self.pause_timepoint = -1

        # calculate the total procedure time
        self.total_procedure_time = self.recipe_df["Time point (min)"].max() * 60

        # clear the recipe table progress and remaining time
        for i, child in self.recipe_rows:
            self.recipe_table.item(child, values=list(self.recipe_df.iloc[i]))

        # record high precision start time
        self.start_time = time.time() - self.pause_duration
        self.current_index = 0
        self.execute_procedure()

    def execute_procedure(self, index=0):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        if index >= len(self.recipe_df):
            self.start_time = -1
            self.total_procedure_time = -1
            self.current_index = -1
            logging.info("Procedure completed.")
            messagebox.showinfo(
                "Procedure Complete", "The procedure has been completed."
            )
            # disable the stop button
            self.stop_button.config(state=tk.DISABLED)
            # disable the pause button
            self.pause_button.config(state=tk.DISABLED)
            # disable the continue button
            self.continue_button.config(state=tk.DISABLED)
            return

        self.current_index = index
        row = self.recipe_df.iloc[index]
        target_time = float(row["Time point (min)"]) * 60

        elapsed_time = time.time() - self.start_time - self.pause_duration
        # calculate the remaining time for the current step
        current_step_remaining_time = target_time - elapsed_time
        intended_sleep_time = max(100, int(current_step_remaining_time * 1000 / 2))
        if elapsed_time < target_time:
            self.scheduled_task = self.master.after(intended_sleep_time, self.execute_procedure, index)
            return

        logging.info(f"executing step at index {index}")

        # Parse pump and valve actions dynamically
        pump_actions = {col: row[col] for col in row.index if col.startswith("Pump")}
        valve_actions = {col: row[col] for col in row.index if col.startswith("Valve")}

        # issue a one-time status update
        self.update_status()
        self.execute_actions(index, pump_actions, valve_actions)

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

        # issue a one-time status update
        self.update_status()
        self.scheduled_task = self.master.after(100, self.execute_procedure, index + 1)

    # this update_progress will update all field in the recipe table and the progress frame
    def update_progress(self):
        if (
            self.total_procedure_time == -1 # Check if not started
            or self.recipe_df is None
            or self.recipe_df.empty
            or self.pause_timepoint != -1 # Check if paused
        ):
            return
        elapsed_time = time.time() - self.start_time - self.pause_duration
        total_progress = int((elapsed_time / self.total_procedure_time) * 100)
        self.total_progress_bar["value"] = total_progress
        remaining_time = int(self.total_procedure_time - elapsed_time)
        # convert this time to using function in time module
        time_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))
        self.remaining_time_value.config(text=f"{time_str}")

        # update the recipe table with individual progress of each row and remaining time
        for i, child in self.recipe_rows:
            row = self.recipe_df.iloc[i]
            time_stamp = float(row["Time point (min)"]) * 60
            # if the time stamp is in the future, break the loop
            if elapsed_time < time_stamp:
                break
            else:
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
                self.recipe_table.item(
                    child,
                    values=list(row) + [f"{row_progress}%", f"{remaining_time_row}s"],
                )

    def add_pump(self):
        # only add a pump if connected to Pico
        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        pump_id = len(self.pumps) + 1
        self.update_pump_widgets(f"Pump{pump_id} Info: Power Pin: -1, Direction Pin: -1, Initial Power Pin Value: 0, Initial Direction Pin Value: 0, Current Power Status: OFF, Current Direction Status: CCW")

    def edit_pump(self, pump_id):
        pump = self.pumps[pump_id]
        power_pin = simpledialog.askinteger("Power Pin", "Enter power pin ID:", initialvalue=int(pump["power_pin"]))
        direction_pin = simpledialog.askinteger("Direction Pin", "Enter direction pin ID:", initialvalue=int(pump["direction_pin"]))
        initial_power_pin_value = simpledialog.askinteger("Initial Power Pin Value", "Enter initial power pin value (0/1):", initialvalue=int(pump["initial_power_pin_value"]), minvalue=0, maxvalue=1)
        initial_direction_pin_value = simpledialog.askinteger("Initial Direction Pin Value", "Enter initial direction pin value (0/1):", initialvalue=int(pump["initial_direction_pin_value"]), minvalue=0, maxvalue=1)
        initial_power_status = simpledialog.askstring("Initial Power Status", "Enter initial power status (ON/OFF):", initialvalue=pump["power_status"])
        initial_direction_status = simpledialog.askstring("Initial Direction Status", "Enter initial direction status (CW/CCW):", initialvalue=pump["direction_status"])

        if (power_pin is not None and direction_pin is not None and initial_power_pin_value is not None and initial_direction_pin_value is not None and initial_power_status in ["ON", "OFF"] and initial_direction_status in ["CW", "CCW"]):
            self.register_pump(pump_id, power_pin, direction_pin, initial_power_pin_value, initial_direction_pin_value, initial_power_status, initial_direction_status)
        else:
            messagebox.showerror("Error", "Invalid input for pump registration.")
        # update the pump info
        self.query_pump_info()

root = tk.Tk()
app = PicoController(root)
root.mainloop()