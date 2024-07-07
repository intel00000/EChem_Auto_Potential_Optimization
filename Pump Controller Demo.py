import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox
import time
from datetime import datetime
import logging
import re

class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        self.style = ttk.Style(master)
        self.style.theme_use("vista")
        
        self.serial_port = None
        self.current_port = None
        self.poll_rate = 100  # Default poll rate in milliseconds
        self.onging_status_update = False
        self.pumps = {}  # Dictionary to store pump information and widgets
        
        # Set up logging
        runtime = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f'pico_controller_log_{runtime}.log'
        logging.basicConfig(level=logging.INFO, format='%(asctime)s: %(message)s', handlers=[logging.FileHandler(log_filename), logging.StreamHandler()])
        
        # Create and place widgets
        self.port_label = ttk.Label(master, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.port_combobox = ttk.Combobox(master)
        self.port_combobox.grid(row=0, column=1, padx=10, pady=10)
        self.refresh_ports()
        if len(self.port_combobox['values']) > 0:
            self.port_combobox.current(0)  # Default to the first port
        
        self.connect_button = ttk.Button(master, text="Connect", command=self.connect_to_pico)
        self.connect_button.grid(row=0, column=2, padx=10, pady=10)
        
        self.disconnect_button = ttk.Button(master, text="Disconnect", command=self.disconnect_pico)
        self.disconnect_button.grid(row=0, column=3, padx=10, pady=10)
        
        self.status_label = ttk.Label(master, text="Status: Not connected")
        self.status_label.grid(row=1, column=0, columnspan=4, padx=10, pady=10)
        
        self.poll_rate_label = ttk.Label(master, text="Set Poll Rate (ms):")
        self.poll_rate_label.grid(row=2, column=0, padx=10, pady=10)
        
        self.poll_rate_entry = ttk.Entry(master)
        self.poll_rate_entry.grid(row=2, column=1, padx=10, pady=10)
        self.poll_rate_entry.insert(0, str(self.poll_rate))
        
        self.set_poll_rate_button = ttk.Button(master, text="Set Poll Rate", command=self.set_poll_rate)
        self.set_poll_rate_button.grid(row=2, column=2, padx=10, pady=10)

        self.pumps_frame = ttk.Frame(master)
        self.pumps_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=10)

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox['values'] = ports

    def connect_to_pico(self):
        selected_port = self.port_combobox.get()
        if selected_port:
            # Check if already connected to the same port
            if self.serial_port and self.current_port == selected_port:
                # suppress the message if the user is reconnecting to the same port
                self.disconnect_pico(show_message=False)
            # Check if connected to a different port
            elif self.serial_port and self.current_port != selected_port:
                self.disconnect_pico()
            # Attempt to connect to the selected port
            try:
                self.serial_port = serial.Serial(selected_port, 115200, timeout=1)
                self.current_port = selected_port
                self.status_label.config(text=f"Status: Connected to {selected_port}")
                messagebox.showinfo("Connection Status", f"Successfully connected to {selected_port}")
                logging.info(f"Connected to {selected_port}")
                self.query_pump_info()
                # Prevent multiple status polling after reconnection
                if not self.onging_status_update:
                    self.onging_status_update = True
                    self.update_status()
            except serial.SerialException:
                self.status_label.config(text="Status: Not connected")
                messagebox.showerror("Connection Status", f"Failed to connect to {selected_port}")
                logging.error(f"Failed to connect to {selected_port}")

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None
            self.status_label.config(text="Status: Not connected")
            self.pumps_frame.destroy()
            self.pumps_frame = ttk.Frame(self.master)
            self.pumps_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=10)
            if show_message:
                messagebox.showinfo("Disconnection Status", f"Successfully disconnected from {self.current_port}")
            logging.info("Disconnected")

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
            logging.info(f"Sent: {command}")

    def update_status(self):
        if self.serial_port:
            self.send_command('0:st')
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
            messagebox.showerror("Invalid Input", "Please enter a valid poll rate in milliseconds (minimum 100 ms)")
            logging.error(f"Invalid poll rate: {e}")

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
        info_pattern = re.compile(r'Pump(\d+) Info: Power Pin ID: (\d+), Direction Pin ID: (\d+), Initial Power Status: (ON|OFF), Initial Direction Status: (CW|CCW)')
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

            power_label = ttk.Label(self.pumps_frame, text=f"Power Status: {initial_power}")
            power_label.grid(row=row + 1, column=0, padx=10, pady=10)
            self.pumps[pump_id]['power_label'] = power_label

            direction_label = ttk.Label(self.pumps_frame, text=f"Direction Status: {initial_direction}")
            direction_label.grid(row=row + 1, column=1, padx=10, pady=10)
            self.pumps[pump_id]['direction_label'] = direction_label

            power_button = ttk.Button(self.pumps_frame, text="Toggle Power", command=lambda pid=pump_id: self.toggle_power(pid))
            power_button.grid(row=row + 2, column=0, padx=10, pady=10)

            direction_button = ttk.Button(self.pumps_frame, text="Toggle Direction", command=lambda pid=pump_id: self.toggle_direction(pid))
            direction_button.grid(row=row + 2, column=1, padx=10, pady=10)

    def update_pump_status(self, response):
        status_pattern = re.compile(r'Pump(\d+) Status: Power: (ON|OFF), Direction: (CW|CCW)')
        matches = status_pattern.findall(response)

        for match in matches:
            pump_id, power_status, direction_status = match
            pump_id = int(pump_id)
            if pump_id in self.pumps:
                self.pumps[pump_id]['power_status'] = power_status
                self.pumps[pump_id]['direction_status'] = direction_status
                self.pumps[pump_id]['power_label'].config(text=f"Power Status: {power_status}")
                self.pumps[pump_id]['direction_label'].config(text=f"Direction Status: {direction_status}")

    def read_serial(self):
        if self.serial_port:
            try:
                while self.serial_port.in_waiting > 0:
                    response = self.serial_port.readline().decode('utf-8').strip()
                    logging.info(f"Received: {response}")
                    self.process_response(response)
            except serial.SerialException as e:
                self.disconnect_pico(show_message=False)
                messagebox.showerror("Connection Error", "Connection to Pico lost. Please reconnect to continue.")
                logging.error(f"Connection to Pico lost: {e}")
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {e}")
                logging.error(f"An error occurred: {e}")
        self.master.after(self.poll_rate, self.read_serial)

root = tk.Tk()
app = PicoController(root)
root.after(100, app.read_serial)
root.mainloop()