import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox

class PicoController:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        
        self.serial_port = None
        self.current_port = None
        self.poll_rate = 500  # Default poll rate in milliseconds
        self.status_update_job = None  # Job reference for status updates
        
        # Create and place widgets
        self.port_label = ttk.Label(master, text="Select COM Port:")
        self.port_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.port_combobox = ttk.Combobox(master)
        self.port_combobox.grid(row=0, column=1, padx=10, pady=10)
        self.refresh_ports()
        
        self.connect_button = ttk.Button(master, text="Connect", command=self.connect_to_pico)
        self.connect_button.grid(row=0, column=2, padx=10, pady=10)
        
        self.disconnect_button = ttk.Button(master, text="Disconnect", command=self.disconnect_pico)
        self.disconnect_button.grid(row=0, column=3, padx=10, pady=10)
        
        self.status_label = ttk.Label(master, text="Status: Not connected")
        self.status_label.grid(row=1, column=0, columnspan=2, padx=10, pady=10)
        
        self.power_label = ttk.Label(master, text="Power Status: Unknown")
        self.power_label.grid(row=2, column=0, padx=10, pady=10)
        
        self.direction_label = ttk.Label(master, text="Direction Status: Unknown")
        self.direction_label.grid(row=3, column=0, padx=10, pady=10)
        
        self.power_button = ttk.Button(master, text="Toggle Power", command=self.toggle_power)
        self.power_button.grid(row=2, column=1, padx=10, pady=10)
        
        self.direction_button = ttk.Button(master, text="Toggle Direction", command=self.toggle_direction)
        self.direction_button.grid(row=3, column=1, padx=10, pady=10)

        self.poll_rate_label = ttk.Label(master, text="Set Poll Rate (ms):")
        self.poll_rate_label.grid(row=4, column=0, padx=10, pady=10)
        
        self.poll_rate_entry = ttk.Entry(master)
        self.poll_rate_entry.grid(row=4, column=1, padx=10, pady=10)
        self.poll_rate_entry.insert(0, str(self.poll_rate))
        
        self.set_poll_rate_button = ttk.Button(master, text="Set Poll Rate", command=self.set_poll_rate)
        self.set_poll_rate_button.grid(row=4, column=2, padx=10, pady=10)
        
        self.schedule_status_update()

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
                print(f"Connected to {selected_port}")
                self.update_status()  # Call update_status immediately after connecting
            except serial.SerialException:
                self.status_label.config(text="Status: Not connected")
                messagebox.showerror("Connection Status", f"Failed to connect to {selected_port}")
                print(f"Failed to connect to {selected_port}")

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None
            self.status_label.config(text="Status: Not connected")
            self.power_label.config(text="Power Status: Unknown")  # Reset power status to unknown
            self.direction_label.config(text="Direction Status: Unknown")  # Reset direction status to unknown
            if show_message:
                messagebox.showinfo("Disconnection Status", f"Successfully disconnected from {self.current_port}")
            print("Disconnected")

    def toggle_power(self):
        if self.serial_port:
            self.pause_status_update()
            self.master.after(500, lambda: self.send_toggle_command('power'))

    def toggle_direction(self):
        if self.serial_port:
            self.pause_status_update()
            self.master.after(500, lambda: self.send_toggle_command('direction'))

    def send_toggle_command(self, command):
        if self.serial_port:
            self.serial_port.write(f'{command}\n'.encode())
            print(f"Sent: {command}")
            self.master.after(500, self.schedule_status_update)  # Resume regular status update after 0.5 seconds

    def update_status(self):
        print("called update_status")
        if self.serial_port:
            self.serial_port.write(b'status\n')
            print("Sent: status request")
            self.poll_status()

        self.schedule_status_update()  # Schedule next status update

    def schedule_status_update(self):
        self.status_update_job = self.master.after(self.poll_rate, self.update_status)  # automatically poll status based on poll rate

    def pause_status_update(self):
        if self.status_update_job:
            self.master.after_cancel(self.status_update_job)
            self.status_update_job = None

    def poll_status(self):
        print("called poll_status")
        if self.serial_port and self.serial_port.in_waiting > 0:
            response = self.serial_port.readline().decode('utf-8').strip()
            print(f"Received: {response}")
            if "Power:" in response and "Direction:" in response:
                parts = response.split(", ")
                power_status = parts[0].split(": ")[1]
                direction_status = parts[1].split(": ")[1]
                self.power_label.config(text=f"Power Status: {power_status}")
                self.direction_label.config(text=f"Direction Status: {direction_status}")

    def set_poll_rate(self):
        try:
            new_rate = int(self.poll_rate_entry.get())
            if new_rate < 100:
                raise ValueError("Poll rate too low")
            self.poll_rate = new_rate
            messagebox.showinfo("Poll Rate", f"Poll rate set to {new_rate} ms")
            print(f"Poll rate set to {new_rate} ms")
        except ValueError as e:
            messagebox.showerror("Invalid Input", "Please enter a valid poll rate in milliseconds (minimum 100 ms)")
            print(f"Invalid poll rate: {e}")

root = tk.Tk()
app = PicoController(root)
root.mainloop()