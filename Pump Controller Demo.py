import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import time
from datetime import datetime
import logging
import pandas as pd
import re


class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        self.port_refresh_rate = 5000  # Refresh rate for COM ports when not connected
        self.poll_rate = 1000  # Default poll rate in milliseconds
        self.timeout = 1  # Serial port timeout in seconds

        self.serial_port = None
        self.current_port = None
        self.ongoing_status_update = False
        self.ongoing_read_serial = False
        self.pumps = {}  # Dictionary to store pump information and widgets
        self.recipe_df = None

        # Set up logging
        runtime = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f'pico_controller_log_{runtime}.log'
        logging.basicConfig(level=logging.INFO, format='%(asctime)s: %(message)s [%(funcName)s]', handlers=[
                            logging.FileHandler(log_filename), logging.StreamHandler()])

        # Create and place widgets
        self.port_label = ttk.Label(master, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=10, pady=10)

        self.port_combobox = ttk.Combobox(master)
        self.port_combobox.grid(row=0, column=1, padx=10, pady=10)
        self.refresh_ports()
        if len(self.port_combobox['values']) > 0:
            self.port_combobox.current(0)  # Default to the first port

        self.connect_button = ttk.Button(
            master, text="Connect", command=self.connect_to_pico)
        self.connect_button.grid(row=0, column=2, padx=10, pady=10)

        self.disconnect_button = ttk.Button(
            master, text="Disconnect", command=self.disconnect_pico)
        self.disconnect_button.grid(row=0, column=3, padx=10, pady=10)

        self.status_label = ttk.Label(master, text="Status: Not connected")
        self.status_label.grid(row=1, column=0, columnspan=4, padx=10, pady=10)

        self.poll_rate_label = ttk.Label(master, text="Set Poll Rate (ms):")
        self.poll_rate_label.grid(row=2, column=0, padx=10, pady=10)

        self.poll_rate_entry = ttk.Entry(master)
        self.poll_rate_entry.grid(row=2, column=1, padx=10, pady=10)
        self.poll_rate_entry.insert(0, str(self.poll_rate))

        self.set_poll_rate_button = ttk.Button(
            master, text="Set Poll Rate", command=self.set_poll_rate)
        self.set_poll_rate_button.grid(row=2, column=2, padx=10, pady=10)

        self.load_recipe_button = ttk.Button(
            master, text="Load Recipe", command=self.load_recipe)
        self.load_recipe_button.grid(row=2, column=3, padx=10, pady=10)

        self.start_button = ttk.Button(
            master, text="Start", command=self.start_procedure)
        self.start_button.grid(row=2, column=4, padx=10, pady=10)

        # Manual control title with box
        self.manual_control_frame = ttk.Labelframe(
            master, text="Manual Control", padding=(10, 10, 10, 10))
        self.manual_control_frame.grid(
            row=3, column=0, columnspan=4, padx=10, pady=10, sticky='ew')

        # Moved inside the manual control frame
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(row=0, column=0, columnspan=4, padx=10, pady=10)

        self.recipe_frame = ttk.Frame(master)
        self.recipe_frame.grid(row=3, column=4, padx=10, pady=10, sticky='n')

        self.recipe_table = ttk.Treeview(self.recipe_frame)
        self.recipe_table.grid(row=0, column=0, padx=10, pady=10)

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

                # Start reading serial data
                if not self.ongoing_read_serial:
                    self.ongoing_read_serial = True
                    self.read_serial()
                # issue a pump info query
                self.query_pump_info()
                # issue a status update command
                if not self.ongoing_status_update:
                    self.ongoing_status_update = True
                    self.update_status()

            except serial.SerialException:
                self.status_label.config(text="Status: Not connected")
                logging.error(f"Failed to connect to {selected_port}")
                messagebox.showerror("Connection Status",
                                     f"Failed to connect to {selected_port}")

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            # First stop both polling and reading serial data
            self.ongoing_status_update = False
            self.ongoing_read_serial = False

            self.serial_port.close()
            self.serial_port = None
            # Refresh the COM ports list once disconnected
            self.refresh_ports()
            self.current_port = None

            # update UI
            self.status_label.config(text="Status: Not connected")
            self.pumps_frame.destroy()
            # Recreate inside the manual control frame
            self.pumps_frame = ttk.Frame(self.manual_control_frame)
            self.pumps_frame.grid(
                row=0, column=0, columnspan=4, padx=10, pady=10)

            logging.info(f"Disconnected from {self.current_port}")
            if show_message:
                messagebox.showinfo(
                    "Disconnection Status", f"Successfully disconnected from {self.current_port}")

    def query_pump_info(self):
        if self.serial_port:
            self.send_command('0:info')

    def toggle_power(self, pump_id):
        if self.serial_port:
            self.send_command(f'{pump_id}:pw')

    def toggle_direction(self, pump_id):
        if self.serial_port:
            self.send_command(f'{pump_id}:di')

    def send_command(self, command):
        if self.serial_port:
            self.serial_port.write(f'{command}\n'.encode())
            logging.info(f"PC -> Pico: {command}")

    # Once called, this function will keep updating the status of the pumps until disconnected
    def update_status(self):
        if self.serial_port:
            self.send_command('0:st')
            if self.ongoing_status_update:
                self.master.after(self.poll_rate, self.update_status)

    def set_poll_rate(self):
        try:
            new_rate = int(self.poll_rate_entry.get())
            if new_rate < 1:
                raise ValueError("Poll rate too low")
            self.poll_rate = new_rate
            messagebox.showinfo("Poll Rate", f"Poll rate set to {new_rate} ms")
            logging.info(f"Poll rate set to {new_rate} ms")
        except ValueError as e:
            logging.error(f"Invalid poll rate: {e}")
            messagebox.showerror(
                "Invalid Input", "Please enter a valid poll rate in milliseconds (minimum 1 ms)")
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            messagebox.showerror("Error", f"An error occurred: {e}")

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

        for match in matches:
            pump_id, power_pin, direction_pin, initial_power, initial_direction = match
            pump_id = int(pump_id)
            self.pumps[pump_id] = {
                "power_pin": power_pin,
                "direction_pin": direction_pin,
                "power_status": initial_power,
                "direction_status": initial_direction,
            }

            row = pump_id * 3

            pump_label = ttk.Label(self.pumps_frame, text=f"Pump {pump_id}")
            pump_label.grid(row=row, column=0, padx=10, pady=10)

            power_label = ttk.Label(
                self.pumps_frame, text=f"Power Status: {initial_power}")
            power_label.grid(row=row + 1, column=0, padx=10, pady=10)
            self.pumps[pump_id]['power_label'] = power_label

            direction_label = ttk.Label(
                self.pumps_frame, text=f"Direction Status: {initial_direction}")
            direction_label.grid(row=row + 1, column=1, padx=10, pady=10)
            self.pumps[pump_id]['direction_label'] = direction_label

            power_button = ttk.Button(
                self.pumps_frame, text="Toggle Power", command=lambda pid=pump_id: self.toggle_power(pid))
            power_button.grid(row=row + 2, column=0, padx=10, pady=10)

            direction_button = ttk.Button(
                self.pumps_frame, text="Toggle Direction", command=lambda pid=pump_id: self.toggle_direction(pid))
            direction_button.grid(row=row + 2, column=1, padx=10, pady=10)

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

    def read_serial(self):
        if self.serial_port:
            try:
                while self.serial_port.in_waiting:
                    response = self.serial_port.readline().decode('utf-8').strip()
                    logging.info(f"Received: {response}")
                    self.process_response(response)
            except serial.SerialException as e:
                self.disconnect_pico(show_message=False)
                messagebox.showerror(
                    "Connection Error", "Connection to Pico lost. Please reconnect to continue.")
                logging.error(f"Connection to Pico lost: {e}")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Read_serial: An error occurred: {e}")
                logging.error(f"Read_serial: An error occurred: {e}")
        if self.ongoing_read_serial:  # Ensure serial reading continues only if connected
            self.master.after(self.poll_rate, self.read_serial)

    # Below are the functions for the recipe execution
    def load_recipe(self):
        file_path = filedialog.askopenfilename(
            # allow both csv and excel files
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

        columns = list(self.recipe_df.columns) + ['Progress', 'Remaining Time']
        self.recipe_table = ttk.Treeview(
            self.recipe_frame, columns=columns, show='headings')
        for col in columns:
            self.recipe_table.heading(col, text=col)
            self.recipe_table.column(col, width=100, anchor='center')

        for index, row in self.recipe_df.iterrows():
            self.recipe_table.insert('', 'end', values=list(row) + ['', ''])

        self.recipe_table.grid(row=0, column=0, padx=10, pady=10)

    def start_procedure(self):
        if self.recipe_df is None:
            messagebox.showerror("Error", "No recipe file loaded.")
            return

        self.execute_procedure(0)

    def execute_procedure(self, index):
        if index >= len(self.recipe_df):
            messagebox.showinfo("Procedure Complete",
                                "The procedure has been completed.")
            logging.info("Procedure completed.")
            return

        row = self.recipe_df.iloc[index]
        time_delay = int(row['Time (min)']) * 60 * 1000
        pump_actions = {f'Pump {i + 1}': row[f'Pump {i + 1}'] for i in range(3)}
        print(pump_actions)
        valve_actions = {f'Valve {i + 1}': row[f'Valve {i + 1}'] for i in range(3)}
        print(valve_actions)

        for pump, action in pump_actions.items():
            if action == 'On':
                self.toggle_power(int(pump.split()[1]))
            elif action == 'Off':
                self.toggle_power(int(pump.split()[1]))

        # Add valve action handling
        for valve, action in valve_actions.items():
            if action == 1:
                self.toggle_direction(int(valve.split()[1]))
            elif action == 2:
                self.toggle_direction(int(valve.split()[1]))

        self.update_progress(index)

        self.master.after(
            time_delay, lambda: self.execute_procedure(index + 1))

    def update_progress(self, index):
        progress = (index + 1) / len(self.recipe_df) * 100
        for i in range(len(self.recipe_df)):
            if i == index:
                remaining_time = self.recipe_df.iloc[i]['Time (min)'] * 60
                self.recipe_table.set(self.recipe_table.get_children()[i], 'Progress', f'{progress:.2f}%')
                self.recipe_table.set(self.recipe_table.get_children()[i], 'Remaining Time', f'{remaining_time:.0f}s')
            else:
                self.recipe_table.set(self.recipe_table.get_children()[i], 'Progress', f'{progress:.2f}%')
                self.recipe_table.set(self.recipe_table.get_children()[i], 'Remaining Time', '')


root = tk.Tk()
app = PicoController(root)
root.mainloop()