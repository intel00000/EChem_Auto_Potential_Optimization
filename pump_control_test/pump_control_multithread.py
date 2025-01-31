import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
from datetime import datetime
import logging
import pandas as pd
import re
import threading
from queue import Queue
import sys


class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        # self.master.geometry("800x600")
        self.port_refresh_rate = 10000  # Refresh rate for COM ports when not connected
        self.timeout = 1  # Serial port timeout in seconds
        self.thread_sleep_interval = 0.001  # interval between sending commands

        # instance fields for the serial port and threads
        self.serial_port = None
        self.current_port = None

        # threads for reading serial
        self.read_serial_thread = None
        self.stop_read_serial_thread = threading.Event()

        # threads for sending commands
        self.send_command_thread = None
        self.stop_send_command_thread = threading.Event()
        # a queue to store commands to be sent to the Pico
        self.send_command_queue = Queue()
        

        # threads for running procedures
        self.procedure_thread = None
        self.stop_procedure_thread = threading.Event()

        # threads for updating progress bar
        self.update_progress_thread = None
        self.stop_update_progress_thread = threading.Event()

        # Dictionary to store pump information
        self.pumps = {}

        self.recipe_df = pd.DataFrame()
        self.recipe_rows = []

        # time stamp for the start of the procedure
        self.start_time = time.time()
        self.total_procedure_time = 0

        # Set up logging
        runtime = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"pico_controller_log_{runtime}.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s: %(message)s [%(funcName)s]",
            handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
        )

        # Create and place widgets
        # first row is for selecting COM port and connecting/disconnecting
        self.select_port_frame = ttk.Frame(master)
        self.select_port_frame.grid(
            row=0, column=0, columnspan=4, rowspan=2, padx=10, pady=10, sticky="NSEW"
        )

        self.port_label = ttk.Label(self.select_port_frame, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=10, pady=10)
        self.port_combobox = ttk.Combobox(self.select_port_frame, state="readonly")
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

        # second row is for loading recipe and starting the procedure
        # still inside the select_port_frame
        self.status_label = ttk.Label(
            self.select_port_frame, text="Status: Not connected"
        )
        self.status_label.grid(
            row=1, column=0, padx=10, pady=10, columnspan=2, sticky="W"
        )
        self.load_recipe_button = ttk.Button(
            self.select_port_frame, text="Load Recipe", command=self.load_recipe
        )
        self.load_recipe_button.grid(row=1, column=2, padx=10, pady=10)
        self.start_button = ttk.Button(
            self.select_port_frame, text="Start", command=self.start_procedure
        )
        self.start_button.grid(row=1, column=3, padx=10, pady=10)

        # Manual control title with box
        self.manual_control_frame = ttk.Labelframe(
            master, text="Manual Control", padding=(10, 10, 10, 10)
        )
        self.manual_control_frame.grid(
            row=2, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        # Moved inside the manual control frame
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )

        # recipe frame
        self.recipe_frame = ttk.Labelframe(
            master, text="Recipe", padding=(10, 10, 10, 10)
        )
        self.recipe_frame.grid(
            row=3, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )

        self.recipe_table = ttk.Frame(self.recipe_frame)
        self.recipe_table.grid(
            row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )

        # add a total progress bar and remaining time label below the recipe table
        self.progress_frame = ttk.Labelframe(
            master, text="Progress", padding=(10, 10, 10, 10)
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

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox["values"] = ports
        # if we are not connected, schedule a refresh every self.port_refresh_rate milliseconds
        if not self.serial_port:
            logging.info("Refreshing COM ports")
            self.master.after(self.port_refresh_rate, self.refresh_ports)

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
                self.serial_port = serial.Serial(selected_port, timeout=self.timeout)
                self.current_port = selected_port
                self.status_label.config(text=f"Status: Connected to {selected_port}")

                logging.info(f"Connected to {selected_port}")
                messagebox.showinfo(
                    "Connection Status", f"Successfully connected to {selected_port}"
                )

                # start read_serial thread
                self.stop_read_serial_thread.clear()
                self.read_serial_thread = threading.Thread(target=self.read_serial)
                self.read_serial_thread.start()
                # start send_command thread
                self.stop_send_command_thread.clear()
                self.send_command_thread = threading.Thread(target=self.send_command)
                self.send_command_thread.start()

                # issue a pump info query
                self.query_pump_info()
                # issue a status update
                self.update_status()

            except serial.SerialException:
                self.status_label.config(text="Status: Not connected")
                logging.error(f"Failed to connect to {selected_port}")
                messagebox.showerror(
                    "Connection Status", f"Failed to connect to {selected_port}"
                )

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            # stop all threads
            self.stop_procedure()
            # Stop the send command thread
            self.stop_send_command_thread.set()
            if self.send_command_thread:
                self.send_command_thread.join()
            # Stop the read thread
            self.stop_read_serial_thread.set()
            if self.read_serial_thread:
                self.read_serial_thread.join()
            # reset all threads
            self.send_command_thread = None
            self.read_serial_thread = None

            # close the serial port connection
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None

            # start the refresh ports polling again
            self.refresh_ports()

            # update UI
            self.status_label.config(text="Status: Not connected")
            self.pumps_frame.destroy()
            # Recreate pumps_frame inside the manual control frame
            self.pumps_frame = ttk.Frame(self.manual_control_frame)
            self.pumps_frame.grid(row=0, column=0, columnspan=4, padx=10, pady=10)

            # clear the recipe table
            self.recipe_df = None
            self.recipe_rows = []
            for widget in self.recipe_frame.winfo_children():
                widget.destroy()
            # recreate the recipe table
            self.recipe_table = ttk.Frame(self.recipe_frame)
            self.recipe_table.grid(
                row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
            )
            # clear the progress bar
            self.total_progress_bar["value"] = 0
            self.remaining_time_value.config(text="")

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

    # this send_command will run in a separate thread, removing the first item from the queue and sending it, each sending will be a sleep of 0.1s
    def send_command(self):
        try:
            while not self.stop_send_command_thread.is_set():
                if self.serial_port and not self.send_command_queue.empty():
                    command = self.send_command_queue.get(block=True, timeout=None)
                    self.serial_port.write(f"{command}\n".encode())
                    logging.info(f"PC -> Pico: {command}")
                # This will ensure some time interval between sending commands to avoid flooding the serial port
                time.sleep(self.thread_sleep_interval)
        except serial.SerialException as e:
            self.master.after(0, self.disconnect_pico, False)
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
            while not self.stop_read_serial_thread.is_set():
                if self.serial_port and self.serial_port.in_waiting:
                    response = self.serial_port.readline().decode("utf-8").strip()
                    logging.info(f"Pico -> PC: {response}")
                    self.process_response(response)
                # This will ensure some time interval between sending commands to avoid flooding the serial port
                time.sleep(self.thread_sleep_interval)
        except serial.SerialException as e:
            self.master.after(0, self.disconnect_pico, False)
            logging.error(f"Connection to Pico lost: {e}")
            messagebox.showerror(
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            messagebox.showerror("Error", f"Read_serial: An error occurred: {e}")
            logging.error(f"Read_serial: An error occurred: {e}")

    def process_response(self, response):
        if "Info" in response:
            self.create_pump_widgets(response)
        elif "Status" in response:
            self.update_pump_status(response)

    def create_pump_widgets(self, response):
        # clear existing widgets
        for widget in self.pumps_frame.winfo_children():
            widget.destroy()
        # clear the pumps dictionary
        self.pumps = {}

        info_pattern = re.compile(
            r"Pump(\d+) Info: Power Pin ID: (\d+), Direction Pin ID: (\d+), Initial Power Status: (ON|OFF), Initial Direction Status: (CW|CCW)"
        )
        matches = info_pattern.findall(response)

        # sort the matches by pump_id
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

            pump_frame = ttk.Labelframe(self.pumps_frame, text=f"Pump {pump_id}")
            pump_frame.grid(row=0, column=pump_id - 1, padx=10, pady=10, sticky="NS")

            pump_label = ttk.Label(
                pump_frame,
                text=f"Pump {pump_id}, power pin: {power_pin}, direction pin: {direction_pin}",
            )
            pump_label.grid(row=0, column=0, padx=10, pady=10, sticky="NS")

            power_label = ttk.Label(pump_frame, text=f"Power Status: {initial_power}")
            power_label.grid(row=1, column=0, padx=10, pady=10, sticky="NS")
            self.pumps[pump_id]["power_label"] = power_label

            direction_label = ttk.Label(
                pump_frame, text=f"Direction Status: {initial_direction}"
            )
            direction_label.grid(row=1, column=1, padx=10, pady=10, sticky="NS")
            self.pumps[pump_id]["direction_label"] = direction_label

            power_button = ttk.Button(
                pump_frame,
                text="Toggle Power",
                command=lambda pid=pump_id: self.toggle_power(pid),
            )
            power_button.grid(row=2, column=0, padx=10, pady=10, sticky="NS")

            direction_button = ttk.Button(
                pump_frame,
                text="Toggle Direction",
                command=lambda pid=pump_id: self.toggle_direction(pid),
            )
            direction_button.grid(row=2, column=1, padx=10, pady=10, sticky="NS")

    def update_pump_status(self, response):
        print("Update status being called")
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
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel/CSV files", "*.xlsx;*.xls;*.csv")]
        )
        if file_path:
            try:
                if file_path.endswith(".csv"):
                    self.recipe_df = pd.read_csv(file_path, keep_default_na=False)
                elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                    self.recipe_df = pd.read_excel(file_path, keep_default_na=False)
                else:
                    raise ValueError("Invalid file format.")

                self.display_recipe()
                logging.info(f"Recipe file loaded successfully: {file_path}")
                messagebox.showinfo(
                    "File Load", f"Recipe file loaded successfully: {file_path}"
                )
            except Exception as e:
                messagebox.showerror(
                    "File Load Error", f"Failed to load recipe file {file_path}: {e}"
                )
                logging.error(f"Failed to load recipe file {file_path}: {e}")

    def display_recipe(self):
        for widget in self.recipe_frame.winfo_children():
            widget.destroy()

        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to display.")
            return

        columns = list(self.recipe_df.columns) + ["Progress Bar", "Remaining Time"]
        self.recipe_table = ttk.Treeview(
            self.recipe_frame, columns=columns, show="headings"
        )
        for col in columns:
            self.recipe_table.heading(col, text=col)
            self.recipe_table.column(col, width=100, anchor="center")

        for index, row in self.recipe_df.iterrows():
            values = list(row)
            self.recipe_table.insert("", "end", values=values)
            self.recipe_rows.append((index, self.recipe_table.get_children()[-1]))

        # double width for the notes column
        self.recipe_table.column("Notes", width=200)

        self.recipe_table.grid(row=0, column=0, padx=10, pady=10)

    def start_procedure(self):
        if self.recipe_df is None:
            messagebox.showerror("Error", "No recipe file loaded.")
            return

        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        logging.info("Starting procedure...")

        # calculate the total procedure time
        self.total_procedure_time = self.recipe_df["Time point (min)"].max() * 60

        self.stop_procedure_thread.clear()
        self.stop_update_progress_thread.clear()
        # record high precision start time
        self.start_time = time.time()

        self.procedure_thread = threading.Thread(
            target=self.execute_procedure, args=(0,)
        )
        self.update_progress_thread = threading.Thread(
            target=self.update_progress, args=()
        )
        self.procedure_thread.start()
        self.update_progress_thread.start()

    def stop_procedure(self):
        # stop the procedure thread
        self.stop_procedure_thread.set()
        if self.procedure_thread:
            self.procedure_thread.join()
        # stop the update progress thread
        self.stop_update_progress_thread.set()
        if self.update_progress_thread:
            self.update_progress_thread.join()
        # reset the procedure thread
        self.procedure_thread = None
        self.update_progress_thread = None

    def execute_procedure(self, index=0):
        row = self.recipe_df.iloc[index]

        while index < len(self.recipe_df):
            if self.stop_procedure_thread.is_set():
                logging.info("Procedure terminated by user.")
                return

            row = self.recipe_df.iloc[index]
            target_time = float(row["Time point (min)"]) * 60

            while time.time() - self.start_time < target_time:
                if self.stop_procedure_thread.is_set():
                    logging.info("Procedure terminated by user.")
                    return
                time.sleep(0.1)

            logging.info(f"executing step at index {index}")

            # Parse pump and valve actions dynamically
            pump_actions = {
                col: row[col] for col in row.index if col.startswith("Pump")
            }
            valve_actions = {
                col: row[col] for col in row.index if col.startswith("Valve")
            }

            # issue a one-time status update
            self.update_status()
            time.sleep(0.1)  # Allow the status update to complete

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
                    and action.upper()
                    != self.pumps[valve_id]["direction_status"].upper()
                ):
                    logging.info(
                        f"At index {index}, valve_id {valve_id} status: {self.pumps[valve_id]['direction_status']}, intended status: {action}, toggling direction."
                    )
                    self.toggle_direction(valve_id)

            # issue a one-time status update
            self.update_status()
            time.sleep(0.1)  # Allow the status update to complete

            # do a check at this point to see if the intended actions have been completed
            # if not, log a error
            for pump, action in pump_actions.items():
                if pd.isna(action) or action == "":
                    continue
                pump_id = int(re.search(r"\d+", pump).group())
                if (
                    pump_id in self.pumps
                    and action.lower() != self.pumps[pump_id]["power_status"].lower()
                ):
                    logging.error(
                        f"At index {index}, pump_id {pump_id} status: {self.pumps[pump_id]['power_status']}, intended status: {action}, failed to toggle power."
                    )
                    self.toggle_power(pump_id)

            for valve, action in valve_actions.items():
                if pd.isna(action) or action == "":
                    continue
                valve_id = int(re.search(r"\d+", valve).group())
                if (
                    valve_id in self.pumps
                    and action.upper()
                    != self.pumps[valve_id]["direction_status"].upper()
                ):
                    logging.error(
                        f"At index {index}, valve_id {valve_id} status: {self.pumps[valve_id]['direction_status']}, intended status: {action}, failed to toggle direction."
                    )
                    self.toggle_direction(valve_id)

            logging.info(f"Step at index {index}/{len(self.recipe_df)} completed.")
            index += 1

        logging.info("Procedure completed.")
        messagebox.showinfo("Procedure Complete", "The procedure has been completed.")

    # this update_progress will update all field in the recipe table and the progress frame
    def update_progress(self):
        while not self.stop_update_progress_thread.is_set():
            elapsed_time = time.time() - self.start_time
            total_progress = int((elapsed_time / self.total_procedure_time) * 100)
            self.total_progress_bar["value"] = total_progress
            remaining_time = int(self.total_procedure_time - elapsed_time)
            self.remaining_time_value.config(text=f"{remaining_time}s")

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
                        row_progress = int(
                            ((elapsed_time - time_stamp) / time_interval) * 100
                        )
                        remaining_time_row = max(0, int(next_time_stamp - elapsed_time))
                    else:
                        row_progress = 100
                        remaining_time_row = 0
                    self.recipe_table.item(
                        child,
                        values=list(row)
                        + [f"{row_progress}%", f"{remaining_time_row}s"],
                    )

            time.sleep(1)


root = tk.Tk()
app = PicoController(root)
root.mainloop()