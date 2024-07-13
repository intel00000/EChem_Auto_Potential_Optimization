import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import os
import pandas as pd
import socketio

sio = socketio.Client()

class PicoControllerFrontend:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        self.main_loop_interval = 1000  # Main loop interval in milliseconds
        self.port_refresh_rate = 5  # Refresh interval for COM ports when not connected
        self.last_port_refresh = -1  # Last time the COM ports were refreshed

        self.connected = False

        # Dictionary to store pump information
        self.pumps = {}

        self.recipe_df = None
        self.recipe_rows = []

        # Time stamp for the start of the procedure
        self.start_time = -1
        self.total_procedure_time = -1

        # Create and place widgets
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

        self.manual_control_frame = ttk.Labelframe(
            master, text="Manual Control", padding=(10, 10, 10, 10)
        )
        self.manual_control_frame.grid(
            row=2, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW"
        )

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

        # Connect to the WebSocket server
        sio.connect('http://localhost:5000')

        @sio.on('my_response')
        def on_message(data):
            print('Received message:', data)

        @sio.on('progress_update')
        def on_progress_update(data):
            self.update_progress(data)

        self.master.after(self.main_loop_interval, self.main_loop)

    def main_loop(self):
        self.refresh_ports()
        self.master.after(self.main_loop_interval, self.main_loop)

    def refresh_ports(self):
        if self.connected:
            current_time = int(time.time())
            if current_time - self.last_port_refresh > self.port_refresh_rate:
                self.last_port_refresh = current_time
        response = requests.get("http://localhost:5000/refresh_ports")
        ports = response.json().get("ports", [])
        self.port_combobox["values"] = ports

    def connect_to_pico(self):
        selected_port = self.port_combobox.get()
        response = requests.post("http://localhost:5000/connect", json={"port": selected_port})
        if response.json().get("success"):
            self.status_label.config(text=f"Status: Connected to {selected_port}")
            self.query_pump_info()
            self.update_status()
            self.connected = True

    def disconnect_pico(self):
        response = requests.post("http://localhost:5000/disconnect")
        if response.json().get("success"):
            self.status_label.config(text="Status: Not connected")
            self.pumps_frame.destroy()
            self.pumps_frame = ttk.Frame(self.manual_control_frame)
            self.pumps_frame.grid(row=0, column=0, columnspan=4, padx=10, pady=10)
            self.recipe_df = None
            self.recipe_rows = []
            for widget in self.recipe_frame.winfo_children():
                widget.destroy()
            self.recipe_table = ttk.Frame(self.recipe_frame)
            self.recipe_table.grid(row=0, column=0, columnspan=4, padx=10, pady=10, sticky="NSEW")
            self.total_progress_bar["value"] = 0
            self.remaining_time_value.config(text="")
            self.connected = False

    def query_pump_info(self):
        response = requests.post("http://localhost:5000/toggle_power")
        pumps = response.json().get("pumps", {})
        self.create_pump_widgets(pumps)

    def update_status(self):
        response = requests.post("http://localhost:5000/toggle_direction")
        pumps = response.json().get("pumps", {})
        self.update_pump_status(pumps)

    def toggle_power(self, pump_id):
        requests.post("http://localhost:5000/toggle_power", json={"pump_id": pump_id})
        self.update_status()

    def toggle_direction(self, pump_id):
        requests.post("http://localhost:5000/toggle_direction", json={"pump_id": pump_id})
        self.update_status()

    def load_recipe(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            response = requests.post("http://localhost:5000/load_recipe", json={"file_path": file_path})
            if response.json().get("success"):
                self.recipe_df = pd.DataFrame(response.json().get("recipe"))
                self.display_recipe()

    def display_recipe(self):
        for widget in self.recipe_frame.winfo_children():
            widget.destroy()
        if self.recipe_df is None or self.recipe_df.empty:
            return
        columns = list(self.recipe_df.columns) + ["Progress Bar", "Remaining Time"]
        self.recipe_table = ttk.Treeview(self.recipe_frame, columns=columns, show="headings")
        for col in columns:
            self.recipe_table.heading(col, text=col)
            self.recipe_table.column(col, width=100, anchor="center")
        for index, row in self.recipe_df.iterrows():
            values = list(row)
            self.recipe_table.insert("", "end", values=values)
            self.recipe_rows.append((index, self.recipe_table.get_children()[-1]))
        self.recipe_table.column("Notes", width=200)
        self.recipe_table.grid(row=0, column=0, padx=10, pady=10)

    def start_procedure(self):
        response = requests.post("http://localhost:5000/start_procedure")
        if response.json().get("success"):
            self.update_progress()

    def update_progress(self, progress_info=None):
        if not progress_info:
            response = requests.get("http://localhost:5000/progress")
            progress_info = response.json()
        total_progress = progress_info.get("total_progress", 0)
        remaining_time = progress_info.get("remaining_time", 0)
        self.total_progress_bar["value"] = total_progress
        self.remaining_time_value.config(text=f"{remaining_time}s")
        recipe_progress = progress_info.get("recipe_progress", [])
        for progress in recipe_progress:
            i = progress.get("index")
            row_progress = progress.get("progress")
            remaining_time_row = progress.get("remaining_time")
            row = progress.get("data")
            child = self.recipe_rows[i][1]
            self.recipe_table.item(
                child,
                values=list(row.values()) + [f"{row_progress}%", f"{remaining_time_row}s"],
            )

    def create_pump_widgets(self, pumps):
        for widget in self.pumps_frame.winfo_children():
            widget.destroy()
        self.pumps = pumps
        for pump_id, pump_info in pumps.items():
            pump_frame = ttk.Labelframe(self.pumps_frame, text=f"Pump {pump_id}")
            pump_frame.grid(row=0, column=int(pump_id) - 1, padx=10, pady=10, sticky="NS")
            pump_label = ttk.Label(
                pump_frame,
                text=f"Pump {pump_id}, power pin: {pump_info['power_pin']}, direction pin: {pump_info['direction_pin']}",
            )
            pump_label.grid(row=0, column=0, padx=10, pady=10, sticky="NS")
            power_label = ttk.Label(pump_frame, text=f"Power Status: {pump_info['power_status']}")
            power_label.grid(row=1, column=0, padx=10, pady=10, sticky="NS")
            self.pumps[pump_id]["power_label"] = power_label
            direction_label = ttk.Label(pump_frame, text=f"Direction Status: {pump_info['direction_status']}")
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

    def update_pump_status(self, pumps):
        for pump_id, pump_info in pumps.items():
            self.pumps[pump_id]["power_status"] = pump_info["power_status"]
            self.pumps[pump_id]["direction_status"] = pump_info["direction_status"]
            self.pumps[pump_id]["power_label"].config(text=f"Power Status: {pump_info['power_status']}")
            self.pumps[pump_id]["direction_label"].config(text=f"Direction Status: {pump_info['direction_status']}")

root = tk.Tk()
app = PicoControllerFrontend(root)
root.mainloop()