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


class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        # self.master.geometry("800x600")
        self.port_refresh_rate = 10000  # Refresh rate for COM ports when not connected
        self.timeout = 1  # Serial port timeout in seconds

        self.serial_port = None
        self.current_port = None
        self.read_thread = None
        self.stop_read_thread = threading.Event()
        self.pumps = {}  # Dictionary to store pump information and widgets

        self.recipe_df = None
        self.recipe_rows = []
        self.start_time = None

        # Set up logging
        runtime = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f'pico_controller_log_{runtime}.log'
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s: %(message)s [%(funcName)s]', handlers=[
                            logging.FileHandler(log_filename), logging.StreamHandler()])

        # Create and place widgets
        # first row is for selecting COM port and connecting/disconnecting
        self.select_port_frame = ttk.Frame(master)
        self.select_port_frame.grid(
            row=0, column=0, columnspan=4, rowspan=2, padx=10, pady=10, sticky='NSEW')

        self.port_label = ttk.Label(
            self.select_port_frame, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=10, pady=10)
        self.port_combobox = ttk.Combobox(
            self.select_port_frame, state='readonly')
        self.port_combobox.grid(row=0, column=1, padx=10, pady=10)
        self.refresh_ports()
        if len(self.port_combobox['values']) > 0:
            self.port_combobox.current(0)  # Default to the first port
        self.connect_button = ttk.Button(
            self.select_port_frame, text="Connect", command=self.connect_to_pico)
        self.connect_button.grid(row=0, column=2, padx=10, pady=10)
        self.disconnect_button = ttk.Button(
            self.select_port_frame, text="Disconnect", command=self.disconnect_pico)
        self.disconnect_button.grid(row=0, column=3, padx=10, pady=10)

        # second row is for loading recipe and starting the procedure
        # still inside the select_port_frame
        self.status_label = ttk.Label(
            self.select_port_frame, text="Status: Not connected")
        self.status_label.grid(row=1, column=0, padx=10,
                               pady=10, columnspan=2, sticky='W')
        self.load_recipe_button = ttk.Button(
            self.select_port_frame, text="Load Recipe", command=self.load_recipe)
        self.load_recipe_button.grid(row=1, column=2, padx=10, pady=10)
        self.start_button = ttk.Button(
            self.select_port_frame, text="Start", command=self.start_procedure)
        self.start_button.grid(row=1, column=3, padx=10, pady=10)

        # Manual control title with box
        self.manual_control_frame = ttk.Labelframe(
            master, text="Manual Control", padding=(10, 10, 10, 10))
        self.manual_control_frame.grid(
            row=2, column=0, columnspan=4, padx=10, pady=10, sticky='NSEW')
        # Moved inside the manual control frame
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(row=0, column=0, columnspan=4,
                              padx=10, pady=10, sticky='NSEW')

        # recipe frame
        self.recipe_frame = ttk.Labelframe(
            master, text="Recipe", padding=(10, 10, 10, 10))
        self.recipe_frame.grid(row=3, column=0, columnspan=4, padx=10,
                               pady=10, sticky='NSEW')

        self.recipe_table = ttk.Frame(self.recipe_frame)
        self.recipe_table.grid(row=0, column=0, columnspan=4,
                               padx=10, pady=10, sticky='NSEW')

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox['values'] = ports
        # if we are not connected, schedule a refresh every self.port_refresh_rate milliseconds
        if not self.serial_port:
            logging.info("Refreshing COM ports")
            self.master.after(self.port_refresh_rate, self.refresh_ports)

    def connect_to_pico(self):
        selected_port = self.port_combobox.get()
        if selected_port:
            # Check if already connected
            if self.serial_port:
                # suppress the message for the disconnect
                self.disconnect_pico(show_message=False)
            # Attempt to connect to the selected port
            try:
                self.serial_port = serial.Serial(
                    selected_port, timeout=self.timeout)
                self.current_port = selected_port
                self.status_label.config(
                    text=f"Status: Connected to {selected_port}")

                logging.info(f"Connected to {selected_port}")
                messagebox.showinfo(
                    "Connection Status", f"Successfully connected to {selected_port}")

                # Start reading serial data in a separate thread
                self.stop_read_thread.clear()
                self.read_thread = threading.Thread(target=self.read_serial)
                self.read_thread.start()

                # issue a pump info query
                self.query_pump_info()
                # issue a status update
                self.update_status()

            except serial.SerialException:
                self.status_label.config(text="Status: Not connected")
                logging.error(f"Failed to connect to {selected_port}")
                messagebox.showerror("Connection Status",
                                     f"Failed to connect to {selected_port}")

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            # Stop the read thread
            self.stop_read_thread.set()
            if self.read_thread:
                self.read_thread.join()

            self.serial_port.close()
            self.serial_port = None
            self.current_port = None

            # Refresh the COM ports list once disconnected
            self.refresh_ports()

            # update UI
            self.status_label.config(text="Status: Not connected")
            self.pumps_frame.destroy()
            # Recreate inside the manual control frame
            self.pumps_frame = ttk.Frame(self.manual_control_frame)
            self.pumps_frame.grid(
                row=0, column=0, columnspan=4, padx=10, pady=10)

            logging.info("Disconnected from Pico")
            if show_message:
                messagebox.showinfo(
                    "Disconnection Status", "Successfully disconnected from Pico")

    def query_pump_info(self):
        if self.serial_port:
            self.send_command('0:info')

    def toggle_power(self, pump_id):
        if self.serial_port:
            self.send_command(f'{pump_id}:pw')
            self.update_status()

    def toggle_direction(self, pump_id):
        if self.serial_port:
            self.send_command(f'{pump_id}:di')
            self.update_status()

    def send_command(self, command):
        if self.serial_port:
            self.serial_port.write(f'{command}\n'.encode())
            logging.debug(f"PC -> Pico: {command}")

    def update_status(self):
        if self.serial_port:
            self.send_command('0:st')

    def read_serial(self):
        while not self.stop_read_thread.is_set():
            try:
                if self.serial_port.in_waiting:
                    response = self.serial_port.readline().decode('utf-8').strip()
                    logging.info(f"Received: {response}")
                    self.master.after(0, self.process_response, response)
            except serial.SerialException as e:
                self.master.after(0, self.disconnect_pico, False)
                messagebox.showerror(
                    "Connection Error", "Connection to Pico lost. Please reconnect to continue.")
                logging.error(f"Connection to Pico lost: {e}")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Read_serial: An error occurred: {e}")
                logging.error(f"Read_serial: An error occurred: {e}")

    def process_response(self, response):
        if "Info" in response:
            self.create_pump_widgets(response)
        elif "Status" in response:
            self.update_pump_status(response)

    def create_pump_widgets(self, response):
        # Clear existing widgets
        for widget in self.pumps_frame.winfo_children():
            widget.destroy()

        self.pumps = {}
        info_pattern = re.compile(
            r'Pump(\d+) Info: Power Pin ID: (\d+), Direction Pin ID: (\d+), Initial Power Status: (ON|OFF), Initial Direction Status: (CW|CCW)')
        matches = info_pattern.findall(response)

        # sort the matches by pump_id
        matches = sorted(matches, key=lambda x: int(x[0]), reverse=True)

        for match in matches:
            print(match)
            pump_id, power_pin, direction_pin, initial_power, initial_direction = match
            pump_id = int(pump_id)
            self.pumps[pump_id] = {
                "power_pin": power_pin,
                "direction_pin": direction_pin,
                "power_status": initial_power,
                "direction_status": initial_direction,
            }

            pump_frame = ttk.Labelframe(
                self.pumps_frame, text=f"Pump {pump_id}")
            pump_frame.grid(row=0, column=pump_id-1,
                            padx=10, pady=10, sticky='NS')

            pump_label = ttk.Label(
                pump_frame, text=f"Pump {pump_id}, power pin: {power_pin}, direction pin: {direction_pin}")
            pump_label.grid(row=0, column=0, padx=10, pady=10, sticky='NS')

            power_label = ttk.Label(
                pump_frame, text=f"Power Status: {initial_power}")
            power_label.grid(row=1, column=0, padx=10, pady=10, sticky='NS')
            self.pumps[pump_id]['power_label'] = power_label

            direction_label = ttk.Label(
                pump_frame, text=f"Direction Status: {initial_direction}")
            direction_label.grid(row=1, column=1, padx=10,
                                 pady=10, sticky='NS')
            self.pumps[pump_id]['direction_label'] = direction_label

            power_button = ttk.Button(
                pump_frame, text="Toggle Power", command=lambda pid=pump_id: self.toggle_power(pid))
            power_button.grid(row=2, column=0, padx=10, pady=10, sticky='NS')

            direction_button = ttk.Button(
                pump_frame, text="Toggle Direction", command=lambda pid=pump_id: self.toggle_direction(pid))
            direction_button.grid(
                row=2, column=1, padx=10, pady=10, sticky='NS')

    def update_pump_status(self, response):
        status_pattern = re.compile(
            r'Pump(\d+) Status: Power: (ON|OFF), Direction: (CW|CCW)')
        matches = status_pattern.findall(response)

        for match in matches:
            pump_id, power_status, direction_status = match
            pump_id = int(pump_id)
            if pump_id in self.pumps:
                self.pumps[pump_id]['power_status'] = power_status
                self.pumps[pump_id]['direction_status'] = direction_status
                self.pumps[pump_id]['power_label'].config(
                    text=f"Power Status: {power_status}")
                self.pumps[pump_id]['direction_label'].config(
                    text=f"Direction Status: {direction_status}")

    def load_recipe(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel/CSV files", "*.xlsx;*.xls;*.csv")])
        if file_path:
            try:
                if file_path.endswith('.csv'):
                    self.recipe_df = pd.read_csv(file_path)
                else:
                    self.recipe_df = pd.read_excel(file_path)
                self.display_recipe()
                messagebox.showinfo(
                    "File Load", "Recipe file loaded successfully.")
                logging.info("Recipe file loaded successfully.")
            except Exception as e:
                messagebox.showerror(
                    "File Load Error", f"Failed to load recipe file: {e}")
                logging.error(f"Failed to load recipe file: {e}")

    def display_recipe(self):
        for widget in self.recipe_frame.winfo_children():
            widget.destroy()

        columns = list(self.recipe_df.columns) + \
            ["Progress Bar", "Remaining Time"]
        self.recipe_table = ttk.Treeview(
            self.recipe_frame, columns=columns, show='headings')
        for col in columns:
            self.recipe_table.heading(col, text=col)
            self.recipe_table.column(col, width=100, anchor='center')

        for index, row in self.recipe_df.iterrows():
            values = list(row) + [float('nan'), float('nan')]
            self.recipe_table.insert('', 'end', values=values)
            self.recipe_rows.append(
                (index, self.recipe_table.get_children()[-1]))

        self.recipe_table.grid(row=0, column=0, padx=10, pady=10)

    def start_procedure(self):
        if self.recipe_df is None:
            messagebox.showerror("Error", "No recipe file loaded.")
            return

        if not self.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return

        logging.info("Starting procedure...")

        self.start_time = time.time()  # Record the start time of the procedure

        self.execute_procedure(0)

    def execute_procedure(self, index):
        if index >= len(self.recipe_df):
            messagebox.showinfo("Procedure Complete",
                                "The procedure has been completed.")
            logging.info("Procedure completed.")
            return

        row = self.recipe_df.iloc[index]
        time_delay = int(float(row['Time (min)']) * 60 * 1000)
        remaining_time = int(float(row['Time (min)']) * 60)

        for i, child in self.recipe_rows:
            if i == index:
                self.recipe_table.item(child, values=list(
                    row) + ["0%", f"{remaining_time}s"])

        # Parse pump and valve actions dynamically
        pump_actions = {col: row[col]
                        for col in row.index if col.startswith('Pump')}
        valve_actions = {col: row[col]
                         for col in row.index if col.startswith('Valve')}

        # issue a one-time status update
        self.update_status()
        # issue a one-time read serial
        self.read_serial()

        for pump, action in pump_actions.items():
            pump_id = int(re.search(r'\d+', pump).group())
            if pump_id in self.pumps:
                logging.debug(
                    f"pump_id: {pump_id}, intended status: {action}, current status: {self.pumps[pump_id]['power_status']}")
                if action == 'On' and self.pumps[pump_id]['power_status'] == 'OFF':
                    self.toggle_power(pump_id)
                elif action == 'Off' and self.pumps[pump_id]['power_status'] == 'ON':
                    self.toggle_power(pump_id)

        for valve, action in valve_actions.items():
            valve_id = int(re.search(r'\d+', valve).group())
            if valve_id in self.pumps:
                logging.debug(
                    f"valve_id: {valve_id}, intended status: {action}")
                if action == 'CW' and self.pumps[valve_id]['direction_status'] == 'CCW':
                    self.toggle_direction(valve_id)
                elif action == 'CCW' and self.pumps[valve_id]['direction_status'] == 'CW':
                    self.toggle_direction(valve_id)

        def update_progress_bar():
            try:
                elapsed_time = time.time() - self.start_time
                step_time = float(row['Time (min)']) * 60
                remaining = max(0, step_time - elapsed_time)
                progress = 100 * \
                    (elapsed_time / step_time) if step_time > 0 else 100
                self.recipe_table.item(self.recipe_rows[index][1], values=list(
                    row) + [f"{progress:.1f}%", f"{remaining:.1f}s"])
                if remaining > 0:
                    self.master.after(1000, update_progress_bar)
            except Exception as e:
                logging.error(f"An error occurred in update_progress_bar: {e}")

        update_progress_bar()
        self.master.after(
            time_delay, lambda: self.execute_procedure(index + 1))


root = tk.Tk()
app = PicoController(root)
root.mainloop()