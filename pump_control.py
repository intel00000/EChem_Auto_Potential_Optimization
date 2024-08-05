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

# from decimal import Decimal
from datetime import datetime
from decimal import Decimal
from queue import Queue
import pandas as pd

# Define Pi Pico vendor ID
pico_vid = 0x2E8A

global_pad_x = 3
global_pad_y = 3

global_pad_N = 5
global_pad_S = 5
global_pad_W = 5
global_pad_E = 5


class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Control via Pi Pico")
        self.main_loop_interval = 20  # Main loop interval in milliseconds

        # port refresh timer
        self.port_refersh_interval = 5  # Refresh rate for COM ports when not connected
        self.last_port_refresh = -1
        self.timeout = 1  # Serial port timeout in seconds

        # instance fields for the serial port and queue
        self.serial_port = None
        self.current_port = None

        # a queue to store commands to be sent to the Pico
        self.send_command_queue = Queue()

        # Dictionary to store pump information
        self.pumps = {}

        # Dataframe to store the recipe
        self.recipe_df = pd.DataFrame()
        self.recipe_rows = []

        # time stamp for the start of the procedure
        self.start_time = -1
        self.total_procedure_time = -1
        self.current_index = -1
        self.pause_timepoint = -1
        self.pause_duration = 0
        self.scheduled_task = None

        # time stamp for the RTC time query
        self.last_time_query = time.monotonic_ns()

        # define pumps per row in the manual control frame
        self.pumps_per_row = 3

        # Set up logging
        runtime = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.mkdir("log")
        except FileExistsError:
            pass
        log_filename = os.path.join("log", f"pump_control_run_{runtime}.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s: %(message)s [%(funcName)s]",
            handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
        )

        self.create_widgets()
        self.master.after(self.main_loop_interval, self.main_loop)

    def create_widgets(self):
        # Select port frame
        self.select_port_frame = ttk.Labelframe(
            self.master,
            text="Select Port",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.select_port_frame.grid(
            row=0,
            column=0,
            columnspan=4,
            rowspan=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        # first row in the select_port_frame
        self.port_label = ttk.Label(self.select_port_frame, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=global_pad_x, pady=global_pad_y)
        self.port_combobox = ttk.Combobox(
            self.select_port_frame, state="readonly", width=30
        )
        self.port_combobox.grid(row=0, column=1, padx=global_pad_x, pady=global_pad_y)
        self.connect_button = ttk.Button(
            self.select_port_frame, text="Connect", command=self.connect_to_pico
        )
        self.connect_button.grid(row=0, column=2, padx=global_pad_x, pady=global_pad_y)
        self.disconnect_button = ttk.Button(
            self.select_port_frame, text="Disconnect", command=self.disconnect_pico
        )
        self.disconnect_button.grid(
            row=0, column=3, padx=global_pad_x, pady=global_pad_y
        )
        self.disconnect_button.config(state=tk.DISABLED)

        # second row in the select_port_frame
        self.status_label = ttk.Label(
            self.select_port_frame, text="Status: Not connected"
        )
        self.status_label.grid(
            row=1,
            column=0,
            padx=global_pad_x,
            pady=global_pad_y,
            columnspan=2,
            sticky="W",
        )
        self.reset_button = ttk.Button(
            self.select_port_frame, text="Hard reset", command=self.reset_pico
        )
        self.reset_button.grid(
            row=1, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.reset_button.config(state=tk.DISABLED)

        # Manual control frame
        self.manual_control_frame = ttk.Labelframe(
            self.master,
            text="Manual Control",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.manual_control_frame.grid(
            row=2,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        # first row in the manual control frame, containing all the buttons
        self.manual_control_frame_buttons = ttk.Frame(self.manual_control_frame)
        self.manual_control_frame_buttons.grid(
            row=0,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.add_pump_button = ttk.Button(
            self.manual_control_frame_buttons, text="Add Pump", command=self.add_pump
        )
        self.add_pump_button.grid(
            row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.add_pump_button.config(state=tk.DISABLED)
        self.clear_pumps_button = ttk.Button(
            self.manual_control_frame_buttons,
            text="Clear All Pumps",
            command=self.clear_pumps,
        )
        self.clear_pumps_button.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.clear_pumps_button.config(state=tk.DISABLED)
        self.save_pumps_button = ttk.Button(
            self.manual_control_frame_buttons,
            text="Save Config",
            command=lambda: self.save_pump_config(0),
        )
        self.save_pumps_button.grid(
            row=0, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.save_pumps_button.config(state=tk.DISABLED)
        self.emergency_shutdown_button = ttk.Button(
            self.manual_control_frame_buttons,
            text="Emergency Shutdown",
            command=lambda: self.emergency_shutdown(True),
        )
        self.emergency_shutdown_button.grid(
            row=0, column=3, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.emergency_shutdown_button.config(state=tk.DISABLED)

        # second row in the manual control frame, containing the pumps widgets
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=1,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        # Recipe frame
        self.recipe_frame = ttk.Labelframe(
            self.master,
            text="Recipe",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.recipe_frame.grid(
            row=3,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        # first row in the recipe frame, containing the buttons
        self.recipe_frame_buttons = ttk.Frame(self.recipe_frame)
        self.recipe_frame_buttons.grid(
            row=0,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.load_recipe_button = ttk.Button(
            self.recipe_frame_buttons, text="Load Recipe", command=self.load_recipe
        )
        self.load_recipe_button.grid(
            row=0, column=0, padx=global_pad_x, pady=global_pad_y
        )
        self.start_button = ttk.Button(
            self.recipe_frame_buttons, text="Start", command=self.start_procedure
        )
        self.start_button.grid(row=0, column=1, padx=global_pad_x, pady=global_pad_y)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button = ttk.Button(
            self.recipe_frame_buttons,
            text="Stop",
            command=lambda: self.stop_procedure(True),
        )
        self.stop_button.grid(row=0, column=2, padx=global_pad_x, pady=global_pad_y)
        self.stop_button.config(state=tk.DISABLED)
        self.pause_button = ttk.Button(
            self.recipe_frame_buttons, text="Pause", command=self.pause_procedure
        )
        self.pause_button.grid(row=0, column=3, padx=global_pad_x, pady=global_pad_y)
        self.pause_button.config(state=tk.DISABLED)
        self.continue_button = ttk.Button(
            self.recipe_frame_buttons, text="Continue", command=self.continue_procedure
        )
        self.continue_button.grid(row=0, column=4, padx=global_pad_x, pady=global_pad_y)
        self.continue_button.config(state=tk.DISABLED)

        # second row in the recipe frame, containing the recipe table
        self.recipe_table_frame = ttk.Frame(self.recipe_frame)
        self.recipe_table_frame.grid(
            row=1,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.recipe_table = ttk.Frame(self.recipe_table_frame)
        self.recipe_table.grid(
            row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="NSEW"
        )
        self.scrollbar = ttk.Scrollbar()

        # Progress frame
        self.progress_frame = ttk.Labelframe(
            self.master,
            text="Progress",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.progress_frame.grid(
            row=4,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        # first row in the progress frame, containing the progress bar
        self.total_progress_label = ttk.Label(
            self.progress_frame, text="Total Progress:"
        )
        self.total_progress_label.grid(
            row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.total_progress_bar = ttk.Progressbar(
            self.progress_frame, length=200, mode="determinate"
        )
        self.total_progress_bar.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # second row in the progress frame, containing the remaining time
        self.remaining_time_label = ttk.Label(
            self.progress_frame, text="Remaining Time:"
        )
        self.remaining_time_label.grid(
            row=1, column=0, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.remaining_time_value = ttk.Label(self.progress_frame, text="")
        self.remaining_time_value.grid(
            row=1, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )

        # RTC time frame
        self.rtc_time_frame = ttk.Labelframe(
            self.master,
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.rtc_time_frame.grid(
            row=5,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        # first row in the rtc_time_frame, containing the current rtc time from the Pico
        self.current_time_label = ttk.Label(
            self.rtc_time_frame, text="RTC Time: --:--:--"
        )
        self.current_time_label.grid(
            row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="NSW"
        )

    def main_loop(self):
        try:
            self.refresh_ports()
            self.read_serial()
            self.send_command()
            self.update_progress()
            self.query_rtc_time()
            self.master.after(self.main_loop_interval, self.main_loop)
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")
            # we will continue the main loop even if an error occurs
            self.master.after(self.main_loop_interval, self.main_loop)

    def refresh_ports(self):
        if not self.serial_port:
            if time.time() - self.last_port_refresh < self.port_refersh_interval:
                return
            # filter by vendor id
            ports = [
                port.device + " (SN:" + str(port.serial_number) + ")"
                for port in serial.tools.list_ports.comports()
                if port.vid == pico_vid
            ]
            # print detail information of the ports to the console
            for port in serial.tools.list_ports.comports():
                try:
                    # put these into one line
                    logging.info(
                        f"name: {port.name}, description: {port.description}, device: {port.device}, hwid: {port.hwid}, manufacturer: {port.manufacturer}, pid: {hex(port.pid)}, serial_number: {port.serial_number}, vid: {hex(port.vid)}"
                    )
                except Exception as e:
                    logging.error(f"Error: {e}")

            self.port_combobox["values"] = ports
            if len(ports) > 0:
                self.port_combobox.current(0)  # Default to the first returned port
            else:
                # clear the port combobox
                self.port_combobox.set("")
            self.last_port_refresh = time.time()

    def connect_to_pico(self):
        selected_port = self.port_combobox.get()
        if selected_port:
            parsed_port = selected_port.split("(")[0].strip()
            # Check if already connected
            if self.serial_port:
                # if already connected, pop a confirmation message before disconnecting
                if (
                    messagebox.askyesno(
                        "Disconnect",
                        f"Disconnect from current port {parsed_port}?",
                    )
                    == tk.YES
                ):
                    # suppress the message for the disconnect
                    self.disconnect_pico(show_message=False)
                else:
                    return

            # Attempt to connect to the selected port
            try:
                self.serial_port = serial.Serial(parsed_port, timeout=self.timeout)
                self.current_port = selected_port
                self.status_label.config(text=f"Status: Connected to {parsed_port}")

                logging.info(f"Connected to {selected_port}")
                messagebox.showinfo(
                    "Connection Status", f"Successfully connected to {parsed_port}"
                )

                # Sync the RTC time with the PC
                self.sync_rtc_with_pc_time()

                # issue a pump info query
                self.query_pump_info()

                # enable the buttons
                self.enable_disable_pumps_buttons(tk.NORMAL)

            except serial.SerialException as e:
                self.status_label.config(text="Status: Not connected")
                logging.error(f"Error: {e}")
                messagebox.showerror(
                    "Connection Status", f"Failed to connect to {selected_port}"
                )
            except Exception as e:
                self.status_label.config(text="Status: Not connected")
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def sync_rtc_with_pc_time(self):
        """Synchronize the Pico's RTC with the PC's time."""
        try:
            now = datetime.now()
            day_of_week = (
                now.weekday() + 1
            ) % 7  # Python's weekday: Mon=0, Pico: Sun=0
            sync_command = (
                f"0:stime:{now.year}:{now.month}:{now.day}:"
                f"{day_of_week}:{now.hour}:{now.minute}:{now.second}"
            )
            self.send_command_queue.put(sync_command)
        except Exception as e:
            logging.error(f"Error synchronizing RTC with PC time: {e}")

    def query_rtc_time(self):
        """Send a request to the Pico to get the current RTC time every second."""
        current_time = time.monotonic_ns()
        if current_time - self.last_time_query >= 1_000_000_000:
            if self.serial_port:
                self.send_command_queue.put("0:time")
                self.last_time_query = current_time

    def update_rtc_time_display(self, response):
        try:
            match = re.search(
                r"RTC Time: (\d+-\d+-\d+ \d+:\d+:\d+) \((\w+)\)", response
            )
            if match:
                rtc_time = match.group(1)
                day_name = match.group(2)
                self.current_time_label.config(
                    text=f"RTC Time: {rtc_time} ({day_name})"
                )
        except Exception as e:
            logging.error(f"Error updating RTC time display: {e}")

    # a helper function to enable/disable the buttons
    def enable_disable_pumps_buttons(self, state):
        self.disconnect_button.config(state=state)
        self.reset_button.config(state=state)
        self.add_pump_button.config(state=state)
        self.clear_pumps_button.config(state=state)
        self.save_pumps_button.config(state=state)
        self.emergency_shutdown_button.config(state=state)

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            try:
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

                # disable buttons
                self.enable_disable_pumps_buttons(tk.DISABLED)

                # empty the queue
                while not self.send_command_queue.empty():
                    self.send_command_queue.get()

                # refresh the port list immediately
                self.refresh_ports()

                logging.info("Disconnected from Pico")
                if show_message:
                    messagebox.showinfo("Connection Status", "Disconnected from Pico")
            except serial.SerialException as e:
                logging.error(f"Error: {e}")
                messagebox.showerror(
                    "Connection Status", "Failed to disconnect from Pico"
                )
            except Exception as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def query_pump_info(self):
        if self.serial_port:
            # put the command in the queue
            self.send_command_queue.put("0:info")

    def update_status(self):
        if self.serial_port:
            # put the command in the queue
            self.send_command_queue.put("0:st")

    def toggle_power(self, pump_id, update_status=True):
        if self.serial_port:
            self.send_command_queue.put(f"{pump_id}:pw")
            if update_status:
                self.update_status()

    def toggle_direction(self, pump_id, update_status=True):
        if self.serial_port:
            # put the command in the queue
            self.send_command_queue.put(f"{pump_id}:di")
            if update_status:
                self.update_status()

    def register_pump(
        self,
        pump_id,
        power_pin,
        direction_pin,
        initial_power_pin_value,
        initial_direction_pin_value,
        initial_power_status,
        initial_direction_status,
    ):
        if self.serial_port:
            try:
                command = f"{pump_id}:reg:{power_pin}:{direction_pin}:{initial_power_pin_value}:{initial_direction_pin_value}:{initial_power_status}:{initial_direction_status}"
                self.send_command_queue.put(command)
                self.update_status()
            except Exception as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def clear_pumps(self, pump_id=0):
        if self.serial_port:
            try:
                # pop a message to confirm the clear
                if pump_id == 0:
                    if messagebox.askyesno("Clear Pumps", "Clear all pumps?") == tk.YES:
                        self.send_command_queue.put("0:clr")
                        self.clear_pumps_widgets()
                        # issue a pump info query
                        self.query_pump_info()
                else:
                    if (
                        messagebox.askyesno("Clear Pump", f"Clear pump {pump_id}?")
                        == tk.YES
                    ):
                        self.send_command_queue.put(f"{pump_id}:clr")
                        self.clear_pumps_widgets()
                        # issue a pump info query
                        self.query_pump_info()
            except Exception as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def save_pump_config(self, pump_id=0):
        if self.serial_port:
            try:
                self.send_command_queue.put(f"{pump_id}:save")
                logging.info(f"Signal sent to save pump {pump_id} configuration.")
            except Exception as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def emergency_shutdown(self, confirmation=False):
        if self.serial_port:
            try:
                if not confirmation or messagebox.askyesno(
                    "Emergency Shutdown",
                    "Are you sure you want to perform an emergency shutdown?",
                ):
                    self.send_command_queue.put("0:shutdown")
                    # update the status
                    self.update_status()
                    logging.warning("Signal sent for emergency shutdown.")
            except Exception as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def reset_pico(self):
        if self.serial_port:
            try:
                if messagebox.askyesno(
                    "Reset", "Are you sure you want to reset the Pico?"
                ):
                    self.send_command_queue.put("0:reset")
                    logging.info("Signal sent for Pico reset.")
                    self.enable_disable_pumps_buttons(tk.DISABLED)
            except Exception as e:
                logging.error(f"Error: {e}")
                messagebox.showerror("Error", f"An error occurred: {e}")

    def stop_procedure(self, message=False):
        try:
            if self.scheduled_task:
                self.master.after_cancel(self.scheduled_task)
                self.scheduled_task = None
            self.start_time = -1
            self.total_procedure_time = -1
            self.current_index = -1
            self.pause_timepoint = -1
            self.pause_duration = 0
            # call a emergency shutdown in case the power is still on
            self.emergency_shutdown()
            # update the status
            self.update_status()
            # disable the buttons
            self.stop_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.continue_button.config(state=tk.DISABLED)
            # enable the disconnect button
            self.disconnect_button.config(state=tk.NORMAL)
            logging.info("Procedure stopped.")
            if message:
                messagebox.showinfo(
                    "Procedure Stopped", "The procedure has been stopped."
                )
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    def pause_procedure(self):
        try:
            if self.scheduled_task:
                self.master.after_cancel(self.scheduled_task)
                self.scheduled_task = None
            self.pause_timepoint = time.time()
            self.pause_button.config(state=tk.DISABLED)
            self.continue_button.config(state=tk.NORMAL)
            logging.info("Procedure paused.")
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    def continue_procedure(self):
        try:
            if self.pause_timepoint != -1:
                self.pause_duration += time.time() - self.pause_timepoint
                self.pause_timepoint = -1
            self.pause_button.config(state=tk.NORMAL)
            self.continue_button.config(state=tk.DISABLED)
            self.execute_procedure(self.current_index)
            logging.info("Procedure continued.")
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    # send_command will remove the first item from the queue and send it
    def send_command(self):
        try:
            if self.serial_port and not self.send_command_queue.empty():
                command = self.send_command_queue.get(block=False)
                self.serial_port.write(f"{command}\n".encode())
                logging.info(f"PC -> Pico: {command}")
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Error: {e}")
            messagebox.showerror(
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"Send_command: An error occurred: {e}")

    def read_serial(self):
        try:
            if self.serial_port and self.serial_port.in_waiting:
                response = self.serial_port.readline().decode("utf-8").strip()
                logging.info(f"Pico -> PC: {response}")
                if "Info" in response:
                    self.add_pump_widgets(response)
                elif "Status" in response:
                    self.update_pump_status(response)
                elif "RTC Time" in response:
                    self.update_rtc_time_display(response)
                elif "Success" in response:
                    # don't display the emergency shutdown success message or the RTC time sync success message
                    if (
                        "Emergency Shutdown" not in response
                        or "RTC Time" not in response
                    ):
                        messagebox.showinfo("Success", response)
                elif "Error" in response:
                    messagebox.showerror("Error", response)
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Error: {e}")
            messagebox.showerror(
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            self.disconnect_pico()
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"Read_serial: An error occurred: {e}")

    def add_pump_widgets(self, response):
        try:
            info_pattern = re.compile(
                r"Pump(\d+) Info: Power Pin: (-?\d+), Direction Pin: (-?\d+), Initial Power Pin Value: (\d+), Initial Direction Pin Value: (\d+), Current Power Status: (ON|OFF), Current Direction Status: (CW|CCW)"
            )
            matches = info_pattern.findall(response)
            # sort the matches by pump_id in ascending order
            matches = sorted(matches, key=lambda x: int(x[0]))

            for match in matches:
                (
                    pump_id,
                    power_pin,
                    direction_pin,
                    initial_power_pin_value,
                    initial_direction_pin_value,
                    power_status,
                    direction_status,
                ) = match
                pump_id = int(pump_id)
                if pump_id in self.pumps:
                    self.pumps[pump_id].update(
                        {
                            "power_pin": power_pin,
                            "direction_pin": direction_pin,
                            "initial_power_pin_value": initial_power_pin_value,
                            "initial_direction_pin_value": initial_direction_pin_value,
                            "power_status": power_status,
                            "direction_status": direction_status,
                        }
                    )

                    pump_frame = self.pumps[pump_id]["frame"]
                    pump_frame.grid(
                        row=(pump_id - 1) // self.pumps_per_row,
                        column=(pump_id - 1) % self.pumps_per_row,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NSWE",
                    )

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
                    self.pumps[pump_id]["frame"].config(
                        text=f"Pump {pump_id}, Power pin: {power_pin}, Direction pin: {direction_pin}"
                    )
                else:
                    # pump does not exist, create a new pump frame
                    pump_frame = ttk.Labelframe(
                        self.pumps_frame,
                        text=f"Pump {pump_id}, Power pin: {power_pin}, Direction pin: {direction_pin}",
                        labelanchor="n",
                    )
                    pump_frame.grid(
                        row=(pump_id - 1) // self.pumps_per_row,
                        column=(pump_id - 1) % self.pumps_per_row,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NSWE",
                    )

                    # first row in the pump frame
                    power_label = ttk.Label(
                        pump_frame, text=f"Power Status: {power_status}"
                    )
                    power_label.grid(
                        row=0,
                        column=0,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NS",
                    )
                    direction_label = ttk.Label(
                        pump_frame, text=f"Direction Status: {direction_status}"
                    )
                    direction_label.grid(
                        row=0,
                        column=1,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NS",
                    )

                    # second row in the pump frame
                    power_button = ttk.Button(
                        pump_frame,
                        text="Toggle Power",
                        command=lambda pid=pump_id: self.toggle_power(pid),
                        state="disabled" if power_pin == "-1" else "normal",
                    )
                    power_button.grid(
                        row=1,
                        column=0,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NS",
                    )
                    direction_button = ttk.Button(
                        pump_frame,
                        text="Toggle Direction",
                        command=lambda pid=pump_id: self.toggle_direction(pid),
                        state="disabled" if direction_pin == "-1" else "normal",
                    )
                    direction_button.grid(
                        row=1,
                        column=1,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NS",
                    )

                    # third row in the pump frame
                    remove_button = ttk.Button(
                        pump_frame,
                        text="Remove",
                        command=lambda pid=pump_id: self.clear_pumps(pid),
                    )
                    remove_button.grid(
                        row=2,
                        column=0,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NS",
                    )
                    edit_button = ttk.Button(
                        pump_frame,
                        text="Edit",
                        command=lambda pid=pump_id: self.edit_pump(pid),
                    )
                    edit_button.grid(
                        row=2,
                        column=1,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NS",
                    )

                    self.pumps[pump_id] = {
                        "power_pin": power_pin,
                        "direction_pin": direction_pin,
                        "initial_power_pin_value": initial_power_pin_value,
                        "initial_direction_pin_value": initial_direction_pin_value,
                        "power_status": power_status,
                        "direction_status": direction_status,
                        "frame": pump_frame,
                        "power_label": power_label,
                        "direction_label": direction_label,
                        "power_button": power_button,
                        "direction_button": direction_button,
                    }
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    # a function to clear all pumps
    def clear_pumps_widgets(self):
        for widget in self.pumps_frame.winfo_children():
            widget.destroy()
        # destroy the pumps frame
        self.pumps_frame.destroy()
        # recreate pumps frame inside the manual control frame
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=1,
            column=0,
            columnspan=4,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.pumps.clear()

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
            else:
                # This mean we somehow received a status update for a pump that does not exist
                # clear the pumps widgets and re-query the pump info
                self.clear_pumps_widgets()
                self.query_pump_info()
                logging.error(
                    f"We received a status update for a pump that does not exist: {pump_id}"
                )

    def load_recipe(self):
        file_path = filedialog.askopenfilename(
            initialdir=os.getcwd(),
            title="Select a Recipe File",
            filetypes=(("CSV/Excel files", "*.csv *.xlsx"), ("all files", "*.*")),
        )
        if file_path:
            try:
                # first shutdown the procedure if it is running
                self.stop_procedure()
                # clear the recipe table
                self.clear_recipe()
                if file_path.endswith(".csv"):
                    self.recipe_df = pd.read_csv(
                        file_path, header=None, keep_default_na=False, dtype=object
                    )
                elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                    self.recipe_df = pd.read_excel(
                        file_path, header=None, keep_default_na=False, dtype=object
                    )
                elif file_path.endswith(".pkl"):
                    self.recipe_df = pd.read_pickle(file_path, compression=None)
                elif file_path.endswith(".json"):
                    self.recipe_df = pd.read_json(file_path, dtype=False)
                else:
                    raise ValueError("Unsupported file format.")

                # Clean the data frame
                # Search for any cell containing the keyword "time"
                time_cells = [
                    (row_idx, col_idx, cell)
                    for row_idx, row in self.recipe_df.iterrows()
                    for col_idx, cell in enumerate(row)
                    if isinstance(cell, str) and "time" in cell.lower()
                ]
                # we need at least one "time" cell as the anchor
                if len(time_cells) == 0:
                    raise ValueError("No cell containing the keyword 'time'.")
                elif len(time_cells) == 1:
                    # if we only have one "time" cell, we use it as the anchor
                    time_row_idx, time_col_idx, _ = time_cells[0]
                elif len(time_cells) > 1:
                    # Filter to choose the most relevant "Time (min)" cell as the anchor
                    relevant_time_cells = [
                        cell
                        for cell in time_cells
                        if "time (min)" in cell[2].lower()
                        or "time point (min)" in cell[2].lower()
                    ]
                    if len(relevant_time_cells) == 0:
                        raise ValueError(
                            "Multiple cell containing the keyword 'time' found, but none of them contain 'Time (min)' or 'Time point (min)'."
                        )
                    elif len(relevant_time_cells) > 1:
                        raise ValueError(
                            "Multiple cell containing the keyword 'time' found, multiple of them contain 'Time (min)' or 'Time point (min)'."
                        )
                    # Choose the first relevant "Time (min)" cell as the primary one
                    time_row_idx, time_col_idx, _ = relevant_time_cells[0]

                # Trim the DataFrame
                self.recipe_df = self.recipe_df.iloc[time_row_idx:, time_col_idx:]
                # Set the first row as column names
                self.recipe_df.columns = self.recipe_df.iloc[0]
                # Remove the first row
                self.recipe_df = self.recipe_df[1:].reset_index(drop=True)

                # drop rows where "Time point (min)" column has NaN
                self.recipe_df.dropna(subset=[self.recipe_df.columns[0]], inplace=True)
                # drop rows where "Time point (min)" column is empty
                self.recipe_df = self.recipe_df[self.recipe_df.iloc[:, 0] != ""]

                self.recipe_df[self.recipe_df.columns[0]] = self.recipe_df[
                    self.recipe_df.columns[0]
                ].apply(float)

                # check if the time points are in ascending order
                if not self.recipe_df[
                    self.recipe_df.columns[0]
                ].is_monotonic_increasing:
                    raise ValueError(
                        "Time points are required in monotonically increasing order."
                    )

                # check if there is duplicate time points
                if self.recipe_df[self.recipe_df.columns[0]].duplicated().any():
                    raise ValueError("Duplicate time points are not allowed.")

                # Setup the table to display the data
                columns = list(self.recipe_df.columns) + [
                    "Progress Bar",
                    "Remaining Time",
                ]
                self.recipe_table = ttk.Treeview(
                    self.recipe_table_frame, columns=columns, show="headings"
                )

                # Create a scrollbar
                self.scrollbar = ttk.Scrollbar(
                    self.recipe_table_frame,
                    orient="vertical",
                    command=self.recipe_table.yview,
                )
                self.recipe_table.configure(yscrollcommand=self.scrollbar.set)
                self.scrollbar.grid(row=0, column=1, sticky="NS")

                self.recipe_table.grid(
                    row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="NSEW"
                )
                for col in columns:
                    self.recipe_table.heading(col, text=col)
                    self.recipe_table.column(col, width=100, anchor="center")

                for index, row in self.recipe_df.iterrows():
                    # Convert all cells to strings, preserving precision for numbers
                    values = [
                        (
                            f"{cell:.15g}"
                            if isinstance(cell, (float, Decimal))
                            else str(cell)
                        )
                        for cell in row
                    ]
                    self.recipe_table.insert("", "end", values=values)
                    self.recipe_rows.append(
                        (index, self.recipe_table.get_children()[-1])
                    )

                # Double width for the notes column if it exists
                if "Notes" in columns:
                    self.recipe_table.column("Notes", width=200, anchor="center")

                # Enable the start button
                self.start_button.config(state=tk.NORMAL)

                logging.info(f"Recipe file loaded successfully: {file_path}")
                messagebox.showinfo(
                    "File Load", f"Recipe file loaded successfully: {file_path}"
                )
            except Exception as e:
                # shutdown the procedure if it is running
                self.stop_procedure()
                messagebox.showerror(
                    "File Load Error", f"Failed to load recipe file {file_path}: {e}"
                )
                logging.error(f"Error: {e}")

    # a function to clear the recipe table
    def clear_recipe(self):
        try:
            # clear the recipe table
            self.recipe_df = None
            self.recipe_rows = []
            # destroy the recipe table
            self.recipe_table.destroy()
            # destroy the scrollbar
            self.scrollbar.destroy()
            # recreate the recipe table
            self.recipe_table = ttk.Frame(self.recipe_table_frame)
            self.recipe_table.grid(
                row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="NSEW"
            )
            # clear the progress bar
            self.total_progress_bar["value"] = 0
            self.remaining_time_value.config(text="")

            # disable all procedure buttons
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.continue_button.config(state=tk.DISABLED)
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    def start_procedure(self):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        logging.info("Starting procedure...")

        try:
            # enable the stop button
            self.stop_button.config(state=tk.NORMAL)
            # enable the pause button
            self.pause_button.config(state=tk.NORMAL)
            # disable the continue button
            self.continue_button.config(state=tk.DISABLED)
            # disable the disconnect button
            self.disconnect_button.config(state=tk.DISABLED)

            # clear the stop time and pause time
            self.pause_timepoint = -1

            # calculate the total procedure time
            self.total_procedure_time = (
                float(self.recipe_df["Time point (min)"].max()) * 60
            )

            # clear the "Progress Bar" and "Remaining Time" columns in the recipe table
            for i, child in self.recipe_rows:
                self.recipe_table.set(child, "Progress Bar", "")
                self.recipe_table.set(child, "Remaining Time", "")

            # record start time
            self.start_time = time.time() - self.pause_duration
            self.current_index = 0
            self.execute_procedure()
        except Exception as e:
            # stop the procedure if an error occurs
            self.stop_procedure()
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    def execute_procedure(self, index=0):
        if self.recipe_df is None or self.recipe_df.empty:
            messagebox.showerror("Error", "No recipe file loaded.")
            logging.error("No recipe data to execute.")
            return
        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        try:
            if index >= len(self.recipe_df):
                # update progress bar and remaining time
                self.update_progress()
                self.start_time = -1
                self.total_procedure_time = -1
                self.current_index = -1
                # call a emergency shutdown in case the power is still on
                self.emergency_shutdown()
                logging.info("Procedure completed.")
                messagebox.showinfo(
                    "Procedure Complete", "The procedure has been completed."
                )
                # disable the stop button
                self.stop_button.config(state=tk.DISABLED)
                self.pause_button.config(state=tk.DISABLED)
                self.continue_button.config(state=tk.DISABLED)
                return

            self.current_index = index
            row = self.recipe_df.iloc[index]
            target_time = float(row["Time point (min)"]) * 60

            elapsed_time = time.time() - self.start_time - self.pause_duration
            # calculate the remaining time for the current step
            current_step_remaining_time = target_time - elapsed_time

            # If there is time remaining, sleep for half of the remaining time
            if current_step_remaining_time > 0:
                intended_sleep_time = max(
                    100, int(current_step_remaining_time * 1000 / 2)
                )
                self.scheduled_task = self.master.after(
                    intended_sleep_time, self.execute_procedure, index
                )
                return

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
            self.execute_actions(index, pump_actions, valve_actions)
        except Exception as e:
            logging.error(f"Error: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

    def execute_actions(self, index, pump_actions, valve_actions):
        for pump, action in pump_actions.items():
            if pd.isna(action) or action == "":
                continue
            match = re.search(r"\d+", pump)
            if match:
                pump_id = int(match.group())
                if (
                    pump_id in self.pumps
                    and action.lower() != self.pumps[pump_id]["power_status"].lower()
                ):
                    logging.info(
                        f"At index {index}, pump_id {pump_id} status: {self.pumps[pump_id]['power_status']}, intended status: {action}, toggling power."
                    )
                    self.toggle_power(pump_id, update_status=False)

        for valve, action in valve_actions.items():
            if pd.isna(action) or action == "":
                continue
            match = re.search(r"\d+", valve)
            if match:
                valve_id = int(match.group())
                if (
                    valve_id in self.pumps
                    and action.upper()
                    != self.pumps[valve_id]["direction_status"].upper()
                ):
                    logging.info(
                        f"At index {index}, valve_id {valve_id} status: {self.pumps[valve_id]['direction_status']}, intended status: {action}, toggling direction."
                    )
                    self.toggle_direction(valve_id, update_status=False)

        # issue a one-time status update
        self.update_status()
        self.scheduled_task = self.master.after(100, self.execute_procedure, index + 1)

    def update_progress(self):
        if (
            self.total_procedure_time == -1  # Check if not started
            or self.recipe_df is None
            or self.recipe_df.empty
            or self.pause_timepoint != -1  # Check if paused
        ):
            return

        elapsed_time = time.time() - self.start_time - self.pause_duration
        # Handle total_procedure_time being zero
        if self.total_procedure_time == 0:
            total_progress = 100
            remaining_time = 0
        else:
            total_progress = min(
                100, int((elapsed_time / self.total_procedure_time) * 100)
            )
            remaining_time = max(0, int(self.total_procedure_time - elapsed_time))

        self.total_progress_bar["value"] = total_progress
        time_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))
        self.remaining_time_value.config(text=f"{time_str}")

        # Update the recipe table with individual progress and remaining time
        for i, child in self.recipe_rows:
            time_stamp = float(self.recipe_df.iloc[i]["Time point (min)"]) * 60

            # if the time stamp is in the future, break the loop
            if elapsed_time < time_stamp:
                break
            else:
                # Calculate progress for each step
                if i < len(self.recipe_df) - 1:
                    next_row = self.recipe_df.iloc[i + 1]
                    next_time_stamp = float(next_row["Time point (min)"]) * 60
                    time_interval = next_time_stamp - time_stamp
                    if time_interval > 0:
                        # handle the case where the next row has the same timestamp
                        row_progress = min(
                            100,
                            int(((elapsed_time - time_stamp) / time_interval) * 100),
                        )
                        remaining_time_row = max(0, int(next_time_stamp - elapsed_time))
                    else:
                        # If the next row has the same timestamp, mark the progress as 100%
                        row_progress = 100
                        remaining_time_row = 0
                else:
                    row_progress = 100
                    remaining_time_row = 0

                # Update only the "Progress Bar" and "Remaining Time" columns
                self.recipe_table.set(child, "Progress Bar", f"{row_progress}%")
                self.recipe_table.set(child, "Remaining Time", f"{remaining_time_row}s")

    def add_pump(self):
        # only add a pump if connected to Pico
        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        pump_id = len(self.pumps) + 1
        self.add_pump_widgets(
            f"Pump{pump_id} Info: Power Pin: -1, Direction Pin: -1, Initial Power Pin Value: 0, Initial Direction Pin Value: 0, Current Power Status: OFF, Current Direction Status: CCW"
        )

    def edit_pump(self, pump_id):
        pump = self.pumps[pump_id]
        power_pin = simpledialog.askinteger(
            "Power Pin", "Enter power pin ID:", initialvalue=int(pump["power_pin"])
        )
        direction_pin = simpledialog.askinteger(
            "Direction Pin",
            "Enter direction pin ID:",
            initialvalue=int(pump["direction_pin"]),
        )
        initial_power_pin_value = simpledialog.askinteger(
            "Initial Power Pin Value",
            "Enter initial power pin value (0/1):",
            initialvalue=int(pump["initial_power_pin_value"]),
            minvalue=0,
            maxvalue=1,
        )
        initial_direction_pin_value = simpledialog.askinteger(
            "Initial Direction Pin Value",
            "Enter initial direction pin value (0/1):",
            initialvalue=int(pump["initial_direction_pin_value"]),
            minvalue=0,
            maxvalue=1,
        )
        initial_power_status = simpledialog.askstring(
            "Initial Power Status",
            "Enter initial power status (ON/OFF):",
            initialvalue=pump["power_status"],
        )
        initial_direction_status = simpledialog.askstring(
            "Initial Direction Status",
            "Enter initial direction status (CW/CCW):",
            initialvalue=pump["direction_status"],
        )

        if (
            power_pin is not None
            and direction_pin is not None
            and initial_power_pin_value is not None
            and initial_direction_pin_value is not None
            and initial_power_status in ["ON", "OFF"]
            and initial_direction_status in ["CW", "CCW"]
        ):
            self.register_pump(
                pump_id,
                power_pin,
                direction_pin,
                initial_power_pin_value,
                initial_direction_pin_value,
                initial_power_status,
                initial_direction_status,
            )
        else:
            messagebox.showerror("Error", "Invalid input for pump registration.")
        # update the pump info
        self.query_pump_info()


root = tk.Tk()
app = PicoController(root)
root.mainloop()
