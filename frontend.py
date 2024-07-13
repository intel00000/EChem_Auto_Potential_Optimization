# frontend.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from backend import PicoControllerBackend
import pandas as pd

class PicoControllerFrontend:
    def __init__(self, master):
        self.master = master
        self.master.title("Pump Controller via Pico Demo")
        self.backend = PicoControllerBackend(self.update_pump_widgets, self.update_pump_status)

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

        self.master.after(self.backend.main_loop_interval, self.main_loop)

    def main_loop(self):
        self.backend.main_loop()
        self.master.after(self.backend.main_loop_interval, self.main_loop)

    def refresh_ports(self):
        self.backend.refresh_ports()
        ports = self.backend.get_ports()
        self.port_combobox["values"] = ports

    def connect_to_pico(self):
        selected_port = self.port_combobox.get()
        if selected_port:
            self.backend.connect_to_pico(selected_port)
            self.status_label.config(text=f"Status: Connected to {selected_port}")

    def disconnect_pico(self):
        self.backend.disconnect_pico()
        self.status_label.config(text="Status: Not connected")
        self.pumps_frame.destroy()
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(row=0, column=0, columnspan=4, padx=10, pady=10)

    def load_recipe(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel/CSV files", "*.xlsx;*.xls;*.csv")]
        )
        if file_path:
            self.backend.load_recipe(file_path)
            self.display_recipe()

    def display_recipe(self):
        for widget in self.recipe_frame.winfo_children():
            widget.destroy()
        if self.backend.recipe_df is None or self.backend.recipe_df.empty:
            return
        columns = list(self.backend.recipe_df.columns) + ["Progress Bar", "Remaining Time"]
        self.recipe_table = ttk.Treeview(
            self.recipe_frame, columns=columns, show="headings"
        )
        for col in columns:
            self.recipe_table.heading(col, text=col)
            self.recipe_table.column(col, width=100, anchor="center")
        for index, row in self.backend.recipe_df.iterrows():
            values = list(row)
            self.recipe_table.insert("", "end", values=values)
            self.backend.recipe_rows.append((index, self.recipe_table.get_children()[-1]))
        self.recipe_table.column("Notes", width=200)
        self.recipe_table.grid(row=0, column=0, padx=10, pady=10)

    def start_procedure(self):
        if self.backend.recipe_df is None:
            messagebox.showerror("Error", "No recipe file loaded.")
            return
        if not self.backend.serial_port:
            messagebox.showerror("Error", "Not connected to Pico.")
            return
        self.backend.start_procedure()

    def update_pump_widgets(self, response):
        for widget in self.pumps_frame.winfo_children():
            widget.destroy()
        self.backend.pumps = {}

        info_pattern = re.compile(
            r"Pump(\d+) Info: Power Pin ID: (\d+), Direction Pin ID: (\d+), Initial Power Status: (ON|OFF), Initial Direction Status: (CW|CCW)"
        )
        matches = info_pattern.findall(response)
        matches = sorted(matches, key=lambda x: int(x[0]))

        for match in matches:
            pump_id, power_pin, direction_pin, initial_power, initial_direction = match
            pump_id = int(pump_id)
            self.backend.pumps[pump_id] = {
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
            self.backend.pumps[pump_id]["power_label"] = power_label

            direction_label = ttk.Label(
                pump_frame, text=f"Direction Status: {initial_direction}"
            )
            direction_label.grid(row=1, column=1, padx=10, pady=10, sticky="NS")
            self.backend.pumps[pump_id]["direction_label"] = direction_label

            power_button = ttk.Button(
                pump_frame,
                text="Toggle Power",
                command=lambda pid=pump_id: self.backend.toggle_power(pid),
            )
            power_button.grid(row=2, column=0, padx=10, pady=10, sticky="NS")

            direction_button = ttk.Button(
                pump_frame,
                text="Toggle Direction",
                command=lambda pid=pump_id: self.backend.toggle_direction(pid),
            )
            direction_button.grid(row=2, column=1, padx=10, pady=10, sticky="NS")

    def update_pump_status(self, response):
        status_pattern = re.compile(
            r"Pump(\d+) Status: Power: (ON|OFF), Direction: (CW|CCW)"
        )
        matches = status_pattern.findall(response)

        for match in matches:
            pump_id, power_status, direction_status = match
            pump_id = int(pump_id)
            if pump_id in self.backend.pumps:
                self.backend.pumps[pump_id]["power_status"] = power_status
                self.backend.pumps[pump_id]["direction_status"] = direction_status
                self.backend.pumps[pump_id]["power_label"].config(
                    text=f"Power Status: {power_status}"
                )
                self.backend.pumps[pump_id]["direction_label"].config(
                    text=f"Direction Status: {direction_status}"
                )

root = tk.Tk()
app = PicoControllerFrontend(root)
root.mainloop()