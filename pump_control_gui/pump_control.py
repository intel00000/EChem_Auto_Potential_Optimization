# pyserial imports
import serial
import serial.tools.list_ports

# gui imports
import tkinter as tk
from tkinter import NO, ttk, messagebox, filedialog
import pystray
from PIL import Image

# other library
import os
import re
import time
import json
import logging
import pandas as pd
from queue import Queue
from collections import OrderedDict
from datetime import datetime, timedelta
from tkinter_helpers import (
    non_blocking_messagebox,
    non_blocking_custom_messagebox,
    non_blocking_checklist,
    non_blocking_single_select,
    non_blocking_input_dialog,
)
from helper_functions import (
    check_lock_file,
    remove_lock_file,
    resource_path,
    convert_minutes_to_ns,
    convert_ns_to_timestr,
    process_pump_actions,
    generate_gsequence,
)

pico_vid = 0x2E8A  # Pi Pico vendor ID

global_pad_x = 2
global_pad_y = 2

global_pad_N = 3
global_pad_S = 3
global_pad_W = 3
global_pad_E = 3

NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MILLISECOND = 1_000_000


class PicoController:
    def __init__(self, root) -> None:
        self.root = root
        self.root.title("Pump Control via Pi Pico")
        self.main_loop_interval_ms = 20  # Main loop interval in milliseconds
        self.sizeGrip = ttk.Sizegrip(self.root)
        self.sizeGrip.pack(side="bottom", anchor="se")

        # port refresh timer
        self.port_refresh_interval_ns = (
            5 * NANOSECONDS_PER_SECOND
        )  # Refresh rate for COM ports when not connected
        self.last_port_refresh_ns = -1
        self.timeout = 1  # Serial port timeout in seconds

        # instance fields for the serial port and queue
        # we have multiple controller, the key is the id, the value is the serial port object
        self.pump_controllers = {}
        self.pump_controllers_connected = {}
        # format is "controller_id: bool"
        self.pump_controllers_id_to_widget_map = {}
        self.pump_controllers_send_queue = Queue()  # format is "controller_id:command"
        self.pump_controllers_rtc_time = {}

        # instance field for the autosampler serial port
        self.autosamplers = None
        self.autosamplers_send_queue = Queue()
        self.autosamplers_rtc_time = "Autosampler Time: --:--:--"

        # Dictionary to store pump information
        self.pumps = {}
        # a mapping from pump id to the controller id
        self.pump_ids_to_controller_ids = {}
        self.controller_ids_to_pump_ids = {}
        # define pumps per row in the manual control frame
        self.pumps_per_row = 3

        # Dataframe to store the recipe
        self.recipe_df = None
        self.recipe_df_time_header_index = -1
        self.recipe_rows = []

        # Dataframe to store the EChem automation sequence
        self.eChem_sequence_df = None
        self.eChem_sequence_df_time_header_index = -1

        # time stamp for the start of the procedure
        self.start_time_ns = -1
        self.total_procedure_time_ns = -1
        self.current_index = -1
        self.pause_timepoint_ns = -1
        self.pause_duration_ns = 0
        self.scheduled_task = None

        # time stamp for the RTC time query
        self.last_time_query = time.monotonic_ns()

        # define window behavior
        self.image_red = Image.open(
            resource_path(os.path.join("icons", "icons-red.ico"))
        )
        self.image_white = Image.open(
            resource_path(os.path.join("icons", "icons-white.ico"))
        )
        self.first_close = True

        # Set up logging
        runtime = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.mkdir("log")
        except FileExistsError:
            pass
        log_filename = os.path.join("log", f"pump_control_run_{runtime}.log")
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s: %(message)s [%(funcName)s]",
            handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
        )

        # a notebook widget to hold the tabs
        self.notebook = ttk.Notebook(
            self.root, padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E)
        )
        self.notebook.pack(side="top", fill="both", expand=True)

        # root frame for the manual control page
        self.manual_control_tab = ttk.Frame(self.root)
        self.create_manual_control_page(self.manual_control_tab)
        self.notebook.add(
            self.manual_control_tab, text="Hardware control", sticky="NSEW"
        )

        # root frame for the experiment scheduler page
        self.experiment_scheduler_tab = ttk.Frame(self.root)
        self.create_experiment_scheduler_page(self.experiment_scheduler_tab)
        self.notebook.add(
            self.experiment_scheduler_tab, text="Experiment scheduler", sticky="NSEW"
        )

        # root frame for the generate automation sequence page
        self.eChem_sequence_view = ttk.Frame(self.root)
        self.create_eChem_sequence_view_page(self.eChem_sequence_view)
        self.notebook.add(
            self.eChem_sequence_view, text="EChem sequence viewer", sticky="NSEW"
        )

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        self.root.after(self.main_loop_interval_ms, self.main_loop)

    def on_tab_change(self, event, notebook=None):
        if notebook is None:
            notebook = event.widget
        else:
            notebook = notebook
        notebook.update_idletasks()
        # query the current tab
        current_tab = notebook.nametowidget(notebook.select())
        # don't update the eChem_sequence_view if the corresponding dataframe is empty
        if (
            current_tab == self.eChem_sequence_view
            and self.eChem_sequence_df is not None
        ):
            # update the size of the window to fit the content
            self.root.geometry(
                f"{current_tab.winfo_reqwidth() + 10}x{current_tab.winfo_reqheight() + 48}"
            )
        if current_tab != self.eChem_sequence_view:
            # update the size of the window to fit the content
            self.root.geometry(
                f"{current_tab.winfo_reqwidth() + 10}x{current_tab.winfo_reqheight() + 48}"
            )

    def create_manual_control_page(self, root_frame):
        current_row = 0
        local_columnspan = 8

        # Port selection frame
        self.port_select_frame = ttk.Labelframe(
            root_frame,
            text="Select Port",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.port_select_frame.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
            rowspan=3,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # first in the port_select_frame
        # Create a row for each potential pump controller
        for controller_id in range(1, 4):  # Assume we can have up to 3 pump controllers
            self.add_pump_controller_widgets(controller_id=controller_id)
        current_row = self.port_select_frame.grid_size()[1]

        # second in the port_select_frame
        self.port_label_as = ttk.Label(self.port_select_frame, text="Autosampler:")
        self.port_label_as.grid(
            row=current_row, column=0, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.port_combobox_as = ttk.Combobox(
            self.port_select_frame, state="readonly", width=30
        )
        self.port_combobox_as.grid(
            row=current_row, column=1, padx=global_pad_x, pady=global_pad_y
        )
        self.connect_button_as = ttk.Button(
            self.port_select_frame, text="Connect", command=self.connect_as
        )
        self.connect_button_as.grid(
            row=current_row, column=2, padx=global_pad_x, pady=global_pad_y
        )
        self.disconnect_button_as = ttk.Button(
            self.port_select_frame, text="Disconnect", command=self.disconnect_as
        )
        self.disconnect_button_as.grid(
            row=current_row, column=3, padx=global_pad_x, pady=global_pad_y
        )
        self.disconnect_button_as.config(state=tk.DISABLED)
        self.reset_button_as = ttk.Button(
            self.port_select_frame, text="Reset", command=self.reset_as
        )
        self.reset_button_as.grid(
            row=current_row, column=4, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.reset_button_as.config(state=tk.DISABLED)
        self.status_label_as = ttk.Label(
            self.port_select_frame, text="Status: Not connected"
        )
        self.status_label_as.grid(
            row=current_row,
            column=5,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="W",
        )
        # update the current row
        current_row = self.port_select_frame.grid_size()[1]

        # Pump Manual Control frame
        self.manual_control_frame = ttk.Labelframe(
            root_frame,
            text="Pump Manual Control",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.manual_control_frame.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # first row in the manual control frame, containing all the buttons
        self.manual_control_frame_buttons = ttk.Frame(self.manual_control_frame)
        self.manual_control_frame_buttons.grid(
            row=0,
            column=0,
            columnspan=local_columnspan,
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
        self.clear_pumps_button = ttk.Button(
            self.manual_control_frame_buttons,
            text="Clear All Pumps",
            command=lambda: self.remove_pump(remove_all=True),
        )
        self.clear_pumps_button.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.save_pumps_button = ttk.Button(
            self.manual_control_frame_buttons,
            text="Save Config",
            command=self.save_pump_config,
        )
        self.save_pumps_button.grid(
            row=0, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.emergency_shutdown_button = ttk.Button(
            self.manual_control_frame_buttons,
            text="Shutdown All Pumps",
            command=lambda: self.pumps_shutdown(confirmation=True),
        )
        self.emergency_shutdown_button.grid(
            row=0, column=3, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # second row in the manual control frame, containing the pumps widgets
        self.pumps_frame = ttk.Frame(self.manual_control_frame)
        self.pumps_frame.grid(
            row=1,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # update the current row
        current_row += self.manual_control_frame.grid_size()[1]

        # Autosampler Manual Control frame
        self.manual_control_frame_as = ttk.Labelframe(
            root_frame,
            text="Autosampler Manual Control",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.manual_control_frame_as.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # Text Entry for Position
        self.position_entry_as = ttk.Entry(self.manual_control_frame_as, width=15)
        self.position_entry_as.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.goto_position_button_as = ttk.Button(
            self.manual_control_frame_as,
            text="Go to Position",
            command=self.goto_position_as,
        )
        self.goto_position_button_as.grid(
            row=0, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # Dropdown and Button for Slots
        self.slot_combobox_as = ttk.Combobox(
            self.manual_control_frame_as, state="readonly", width=15
        )
        self.slot_combobox_as.grid(
            row=0, column=3, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.goto_slot_button_as = ttk.Button(
            self.manual_control_frame_as, text="Go to Slot", command=self.goto_slot_as
        )
        self.goto_slot_button_as.grid(
            row=0, column=4, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # update the current row
        current_row += self.manual_control_frame_as.grid_size()[1]

        self.set_manual_control_buttons_state(tk.DISABLED)
        self.set_autosampler_buttons_state(tk.DISABLED)

    # add the widgets under the provided root_frame
    def create_experiment_scheduler_page(self, root_frame):
        current_row = 0  # Row Counter
        local_columnspan = 8

        # Recipe frame
        self.recipe_frame = ttk.Labelframe(
            root_frame,
            text="Recipe",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.recipe_frame.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        # first row in the recipe frame, containing the buttons
        self.recipe_frame_buttons = ttk.Frame(self.recipe_frame)
        self.recipe_frame_buttons.grid(
            row=0,
            column=0,
            columnspan=local_columnspan,
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
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.recipe_table = ttk.Frame(self.recipe_table_frame)
        self.recipe_table.grid(
            row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="NSEW"
        )
        self.scrollbar = ttk.Scrollbar()
        # update the current row
        current_row += self.recipe_frame.grid_size()[1]

        # Progress frame
        self.progress_frame = ttk.Labelframe(
            root_frame,
            text="Progress",
            padding=(global_pad_N, global_pad_S, global_pad_W, global_pad_E),
        )
        self.progress_frame.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
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
            self.progress_frame, length=250, mode="determinate"
        )
        self.total_progress_bar.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # second row in the progress frame, containing the remaining time and Procedure end time
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
        self.end_time_label = ttk.Label(self.progress_frame, text="End Time:")
        self.end_time_label.grid(
            row=1, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.end_time_value = ttk.Label(self.progress_frame, text="")
        self.end_time_value.grid(
            row=1, column=3, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # update the current row
        current_row += self.progress_frame.grid_size()[1]

        # RTC time frame
        self.rtc_time_frame = ttk.Frame(
            root_frame,
            padding=(0, 0, 0, 0),
        )
        self.rtc_time_frame.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
            padx=0,
            pady=0,
            sticky="NSE",
        )
        # first row in the rtc_time_frame, containing the current rtc time from the Pico
        self.current_time_label = ttk.Label(
            self.rtc_time_frame, text="Pump Controller Time: --:--:--"
        )
        self.current_time_label.grid(row=0, column=0, padx=0, pady=0, sticky="NSE")
        self.current_time_label_as = ttk.Label(
            self.rtc_time_frame, text=self.autosamplers_rtc_time
        )
        self.current_time_label_as.grid(row=0, column=1, padx=0, pady=0, sticky="NSE")

    def create_eChem_sequence_view_page(self, root_frame):
        current_row = 0  # Row Counter
        local_columnspan = 8

        # sequence table frame
        self.eChem_sequence_frame = ttk.Labelframe(
            root_frame,
            text="EChem Sequence Viewer",
            padding=(global_pad_N, global_pad_E, global_pad_S, global_pad_W),
        )
        self.eChem_sequence_frame.grid(
            row=current_row,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )

        self.eChem_sequence_table_frame = ttk.Frame(self.eChem_sequence_frame)
        self.eChem_sequence_table_frame.grid(
            row=0,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.eChem_sequence_table = ttk.Frame(
            self.eChem_sequence_table_frame,
        )
        self.eChem_sequence_table.grid(
            row=0,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.scrollbar_EC = ttk.Scrollbar()
        # update the current row
        current_row += self.eChem_sequence_frame.grid_size()[1]
        current_row += 1

    def add_pump_controller_widgets(self, controller_id):
        # update the pump_controllers dictionary
        self.pump_controllers[controller_id] = serial.Serial()
        self.pump_controllers_connected[controller_id] = False
        """Adds the combobox and buttons for selecting and connecting a pump controller."""
        row = controller_id - 1  # Zero-indexed for row position
        port_label = ttk.Label(
            self.port_select_frame, text=f"Pump controller {controller_id}:"
        )
        port_label.grid(
            row=row, column=0, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        port_combobox = ttk.Combobox(self.port_select_frame, state="readonly", width=30)
        port_combobox.grid(row=row, column=1, padx=global_pad_x, pady=global_pad_y)
        connect_button = ttk.Button(
            self.port_select_frame,
            text="Connect",
            command=lambda: self.connect(controller_id),
        )
        connect_button.grid(row=row, column=2, padx=global_pad_x, pady=global_pad_y)
        disconnect_button = ttk.Button(
            self.port_select_frame,
            text="Disconnect",
            command=lambda: self.disconnect(controller_id),
        )
        disconnect_button.grid(row=row, column=3, padx=global_pad_x, pady=global_pad_y)
        disconnect_button.config(state=tk.DISABLED)
        reset_button = ttk.Button(
            self.port_select_frame,
            text="Reset",
            command=lambda: self.reset(controller_id),
        )
        reset_button.grid(
            row=row, column=4, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        reset_button.config(state=tk.DISABLED)
        status_label = ttk.Label(
            self.port_select_frame,
            text="Status: Not connected",
        )
        status_label.grid(
            row=row,
            column=5,
            padx=global_pad_x,
            pady=global_pad_y,
            columnspan=1,
            sticky="W",
        )
        # Save references to widgets
        self.pump_controllers_id_to_widget_map[controller_id] = {
            "combobox": port_combobox,
            "connect_button": connect_button,
            "disconnect_button": disconnect_button,
            "reset_button": reset_button,
            "status_label": status_label,
        }

    def main_loop(self):
        try:
            self.refresh_ports()
            self.read_serial()
            self.read_serial_as()
            self.send_command()
            self.send_command_as()
            self.update_progress()
            self.query_rtc_time()
            self.update_rtc_time_display()
            self.root.after(self.main_loop_interval_ms, self.main_loop)
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in the main loop: {e}",
            )

    def refresh_ports(self, instant=False):
        # check if all serial objects in the self.pump_controllers dictionary are connected
        pump_ctls_all_connected = all(
            [
                serial_port_obj and serial_port_obj.is_open
                for serial_port_obj in self.pump_controllers.values()
            ]
        )
        if not pump_ctls_all_connected or not self.autosamplers:
            if (
                time.monotonic_ns() - self.last_port_refresh_ns
                < self.port_refresh_interval_ns
                and not instant
            ):
                return
            # filter by vendor id and ignore already connected ports
            # get a list of connected ports name from the serial_port dictionary
            connected_ports = [
                port.name
                for port in self.pump_controllers.values()
                if port and port.is_open
            ]
            if self.autosamplers:
                connected_ports.append(self.autosamplers.name)

            ports = [
                port.device + " (SN:" + str(port.serial_number) + ")"
                for port in serial.tools.list_ports.comports()
                if port.vid == pico_vid and port.name.strip() not in connected_ports
            ]
            ports_list = [
                port
                for port in serial.tools.list_ports.comports()
                if port.vid == pico_vid and port.name.strip() not in connected_ports
            ]
            # print detail information of the ports to the console
            for port in ports_list:
                try:
                    # put these into one line
                    logging.debug(
                        f"name: {port.name}, description: {port.description}, device: {port.device}, hwid: {port.hwid}, manufacturer: {port.manufacturer}, pid: {hex(port.pid)}, serial_number: {port.serial_number}, vid: {hex(port.vid)}"
                    )
                except Exception as e:
                    logging.error(f"Error: {e}")

            # go through the pump controllers dictionary and update the comboboxes in the corresponding frame
            for id, widgets in self.pump_controllers_id_to_widget_map.items():
                serial_port_obj = self.pump_controllers[id]
                if (
                    serial_port_obj and not serial_port_obj.is_open
                ):  # don't update the combobox if the port is already connected
                    widgets["combobox"]["values"] = ports
                    if widgets["combobox"].get() not in ports:
                        if len(ports) > 0:
                            widgets["combobox"].current(0)
                        else:
                            widgets["combobox"].set("")
            if not self.autosamplers:
                self.port_combobox_as["values"] = ports
                # if current value is in the list, don't change it
                if self.port_combobox_as.get() not in ports:
                    if len(ports) > 0:
                        self.port_combobox_as.current(0)
                    else:
                        self.port_combobox_as.set("")
            self.last_port_refresh_ns = time.monotonic_ns()

    def connect(self, controller_id):
        selected_port = self.pump_controllers_id_to_widget_map[controller_id][
            "combobox"
        ].get()
        if selected_port:
            parsed_port = selected_port.split("(")[0].strip()
            if self.pump_controllers[controller_id].is_open:
                if (  # if already connected, pop a confirmation message before disconnecting
                    messagebox.askyesno(
                        "Disconnect",
                        f"Disconnect from current port {parsed_port}?",
                    )
                    == tk.YES
                ):
                    # suppress the message for the disconnect
                    self.disconnect(controller_id=controller_id, show_message=False)
                else:
                    return
            try:  # Attempt to connect to the selected port
                serial_port_obj = self.pump_controllers[controller_id]
                serial_port_widget = self.pump_controllers_id_to_widget_map[
                    controller_id
                ]
                serial_port_obj.port = parsed_port
                serial_port_obj.timeout = self.timeout
                serial_port_obj.open()
                serial_port_obj.write("0:ping\n".encode())  # identify Pico type
                response = serial_port_obj.readline().decode("utf-8").strip()
                if "Pico Pump Control Version" not in response:
                    self.disconnect(controller_id=controller_id, show_message=False)
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Connected to the wrong device for pump control",
                    )
                    return
                now = datetime.now()  # synchronize the RTC with the PC time
                sync_command = f"0:stime:{now.year}:{now.month}:{now.day}:{now.hour}:{now.minute}:{now.second}"
                serial_port_obj.write(f"{sync_command}\n".encode())
                response = serial_port_obj.readline().decode("utf-8").strip()

                logging.info(f"Connected to {selected_port}")
                self.refresh_ports(instant=True)  # refresh the ports immediately
                serial_port_widget["status_label"].config(
                    text=f"Status: Connected to {parsed_port}"
                )
                self.pump_controllers_connected[controller_id] = True

                self.query_pump_info(controller_id=controller_id)  # query the pump info
                # enable the buttons
                serial_port_widget["disconnect_button"].config(state=tk.NORMAL)
                serial_port_widget["reset_button"].config(state=tk.NORMAL)
                self.set_manual_control_buttons_state(tk.NORMAL)
            except Exception as e:
                serial_port_widget["status_label"].config(text="Status: Not connected")
                self.pump_controllers_connected[controller_id] = False
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function connect: {e}",
                )

    def set_manual_control_buttons_state(self, state) -> None:
        self.add_pump_button.config(state=state)
        self.clear_pumps_button.config(state=state)
        self.save_pumps_button.config(state=state)
        self.emergency_shutdown_button.config(state=state)

    def connect_as(self):
        selected_port = self.port_combobox_as.get()
        if selected_port:
            parsed_port = selected_port.split("(")[0].strip()
            if self.autosamplers:
                if (
                    messagebox.askyesno(
                        "Disconnect",
                        f"Disconnect from current port {parsed_port}?",
                    )
                    == tk.YES
                ):
                    self.disconnect_as(show_message=False)
                else:
                    return
            try:
                self.autosamplers = serial.Serial(parsed_port, timeout=self.timeout)
                self.autosamplers.write("0:ping\n".encode())  # identify Pico type
                response = self.autosamplers.readline().decode("utf-8").strip()
                if "Pico Autosampler Control Version" not in response:
                    self.disconnect_as(show_message=False)
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Connected to the wrong device for autosampler.",
                    )
                    return
                now = datetime.now()  # synchronize the RTC with the PC time
                sync_command = f"0:stime:{now.year}:{now.month}:{now.day}:{now.hour}:{now.minute}:{now.second}"
                self.autosamplers.write(f"{sync_command}\n".encode())
                response = self.autosamplers.readline().decode("utf-8").strip()

                self.status_label_as.config(text=f"Status: Connected to {parsed_port}")
                logging.info(f"Connected to Autosampler at {selected_port}")
                self.refresh_ports(instant=True)
                self.set_autosampler_buttons_state(tk.NORMAL)
                self.autosamplers_send_queue.put("config")  # Populate the slots
            except Exception as e:
                self.status_label_as.config(text="Status: Not connected")
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function connect_as: {e}",
                )

    def set_autosampler_buttons_state(self, state) -> None:
        self.disconnect_button_as.config(state=state)
        self.reset_button_as.config(state=state)
        self.position_entry_as.config(state=state)
        self.goto_position_button_as.config(state=state)
        self.slot_combobox_as.config(state=state)
        self.goto_slot_button_as.config(state=state)

    def query_rtc_time(self) -> None:
        """Send a request to the Pico to get the current RTC time every second."""
        current_time = time.monotonic_ns()
        if current_time - self.last_time_query >= NANOSECONDS_PER_SECOND:
            # send the command to each controller
            for id, connection_status in self.pump_controllers_connected.items():
                if connection_status:
                    self.pump_controllers_send_queue.put(f"{id}:0:time")
            if self.autosamplers:
                self.autosamplers_send_queue.put("0:time")
            self.last_time_query = current_time

    def parse_rtc_time(self, controller_id, response, is_Autosampler=False) -> None:
        try:
            match = re.search(r"RTC Time: (\d+-\d+-\d+ \d+:\d+:\d+)", response)
            if match and not is_Autosampler:
                rtc_time = match.group(1)
                # store the time in the dictionary
                self.pump_controllers_rtc_time[controller_id] = (
                    f"{controller_id}:{rtc_time}"
                )
            if match and is_Autosampler:
                rtc_time = match.group(1)
                self.autosamplers_rtc_time = f"Autosampler Time: {rtc_time}"
        except Exception as e:
            logging.error(f"Error updating RTC time display: {e}")

    def update_rtc_time_display(self) -> None:
        try:
            # assemble the time string
            rtc_time_str = "Pump Controllers Time: "
            # sort the keys of the dictionary by the pump id, join the values and update the label
            rtc_time_str += " | ".join(
                [
                    self.pump_controllers_rtc_time[key]
                    for key in sorted(self.pump_controllers_rtc_time.keys())
                    if self.pump_controllers_connected[key]
                ]
            )
            self.current_time_label.config(text=rtc_time_str)
            self.current_time_label_as.config(text=self.autosamplers_rtc_time)
        except Exception as e:
            logging.error(f"Error updating RTC time display: {e}")

    def disconnect(self, controller_id, show_message=True):
        if self.pump_controllers[controller_id]:
            serial_port_obj = self.pump_controllers[controller_id]
            serial_port_widget = self.pump_controllers_id_to_widget_map[controller_id]
            if serial_port_obj.is_open:
                try:
                    serial_port_obj.close()  # close the serial port connection
                    self.pump_controllers_connected[controller_id] = False

                    # update UI
                    serial_port_widget["status_label"].config(
                        text="Status: Not connected"
                    )  # update the status label
                    serial_port_widget["disconnect_button"].config(state=tk.DISABLED)
                    serial_port_widget["reset_button"].config(state=tk.DISABLED)
                    self.remove_pumps_widgets(
                        remove_all=False, controller_id=controller_id
                    )
                    # only disable the manual control buttons if all controllers are disconnected
                    if all(
                        [not port.is_open for port in self.pump_controllers.values()]
                    ):
                        self.set_manual_control_buttons_state(tk.DISABLED)
                        self.clear_recipe()  # clear the recipe table
                        self.stop_procedure(False)  # also stop any running procedure

                    # go into the queue and remove any command that is meant for the disconnected controller
                    temp_queue = Queue()
                    while not self.pump_controllers_send_queue.empty():
                        command = self.pump_controllers_send_queue.get()
                        if int(command.split(":")[0]) != controller_id:
                            temp_queue.put(command)
                    while not temp_queue.empty():
                        self.pump_controllers_send_queue.put(temp_queue.get())

                    self.refresh_ports(instant=True)  # refresh the ports immediately
                    logging.info(f"Disconnected from Pico {controller_id}")
                    if show_message:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Connection Status",
                            message=f"Disconnected from pump controller {controller_id}",
                        )
                except Exception as e:
                    logging.error(f"Error: {e}")
                    self.pump_controllers_connected[controller_id] = False
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message=f"An error occurred in function disconnect: {e}",
                    )

    def disconnect_as(self, show_message=True):
        if self.autosamplers:
            try:
                self.autosamplers.close()
                self.autosamplers = None
                self.status_label_as.config(text="Status: Not connected")
                self.set_autosampler_buttons_state(tk.DISABLED)
                while not self.autosamplers_send_queue.empty():  # empty the queue
                    self.autosamplers_send_queue.get()

                logging.info("Disconnected from Autosampler")
                if show_message:
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Disconnected from Autosampler",
                    )
            except Exception as e:
                logging.error(f"Error: {e}")
                self.autosamplers = None
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred: {e}",
                )

    def reset(self, controller_id):
        try:
            if self.pump_controllers[controller_id].is_open:
                if messagebox.askyesno(
                    "Reset", "Are you sure you want to reset the Pico?"
                ):
                    self.pump_controllers_send_queue.put(f"{controller_id}:0:reset")
                    logging.info(f"Signal sent for controller {controller_id} reset.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function reset: {e}",
            )

    def reset_as(self):
        if self.autosamplers:
            try:
                if messagebox.askyesno(
                    "Reset", "Are you sure you want to reset the Autosampler?"
                ):
                    self.autosamplers_send_queue.put("0:reset")
                    logging.info("Signal sent for Autosampler reset.")
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function reset_as: {e}",
                )

    def query_pump_info(self, controller_id):
        serial_obj = self.pump_controllers.get(controller_id, None)
        if serial_obj and serial_obj.is_open:
            self.pump_controllers_send_queue.put(f"{controller_id}:0:info")

    def update_status(self, controller_id):
        serial_obj = self.pump_controllers.get(controller_id, None)
        if serial_obj and serial_obj.is_open:
            self.pump_controllers_send_queue.put(f"{controller_id}:0:st")

    def toggle_power(self, pump_id, update_status=True):
        controller_id = self.pump_ids_to_controller_ids.get(pump_id, None)
        if controller_id:
            if self.pump_controllers[controller_id].is_open:
                self.pump_controllers_send_queue.put(f"{controller_id}:{pump_id}:pw")
                if update_status:
                    self.update_status(controller_id=controller_id)
        else:
            logging.error(
                f"Trying to toggle power for pump {pump_id} without a controller."
            )

    def toggle_direction(self, pump_id, update_status=True):
        controller_id = self.pump_ids_to_controller_ids.get(pump_id, None)
        if controller_id:
            if self.pump_controllers[controller_id].is_open:
                self.pump_controllers_send_queue.put(f"{controller_id}:{pump_id}:di")
                if update_status:
                    self.update_status(controller_id=controller_id)
        else:
            logging.error(
                f"Trying to toggle direction for pump {pump_id} without a controller."
            )

    def register_pump(
        self,
        controller_id,
        pump_id,
        power_pin,
        direction_pin,
        initial_power_pin_value,
        initial_direction_pin_value,
        initial_power_status,
        initial_direction_status,
    ):
        try:
            serial_obj = self.pump_controllers.get(controller_id, None)
            if serial_obj and serial_obj.is_open:
                command = f"{pump_id}:reg:{power_pin}:{direction_pin}:{initial_power_pin_value}:{initial_direction_pin_value}:{initial_power_status}:{initial_direction_status}"
                self.pump_controllers_send_queue.put(f"{controller_id}:{command}")
                self.update_status(controller_id=controller_id)
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function register_pump: {e}",
            )

    def remove_pump(self, remove_all=False, pump_id=None):
        try:
            if remove_all:
                if messagebox.askyesno("Clear Pumps", "Clear all pumps?") == tk.YES:
                    # query the pump info for all the controllers
                    for (
                        id,
                        connection_status,
                    ) in self.pump_controllers_connected.items():
                        if connection_status:
                            self.remove_pumps_widgets(
                                remove_all=False, controller_id=id
                            )
                            self.pump_controllers_send_queue.put(f"{id}:0:clr")
                            self.query_pump_info(controller_id=id)
            else:
                if (
                    messagebox.askyesno("Clear Pump", f"Clear pump {pump_id}?")
                    == tk.YES
                    and pump_id
                ):
                    # find the controller id of the pump
                    controller_id = self.pump_ids_to_controller_ids.get(pump_id, None)
                    if controller_id:
                        self.remove_pumps_widgets(remove_all=False, pump_id=pump_id)
                        self.pump_controllers_send_queue.put(
                            f"{controller_id}:{pump_id}:clr"
                        )
                        self.query_pump_info(controller_id=controller_id)
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function remove_pump: {e}",
            )

    def save_pump_config(self):
        if any(self.pump_controllers_connected.values()):
            try:
                # pop a checklist message box to let user choose which pump to save
                pump_id_list = [
                    f"Controller {id}"
                    for id, connected in self.pump_controllers_connected.items()
                    if connected
                ]
                if len(pump_id_list) > 1:
                    pump_id_list.insert(0, "All")
                result_var = tk.StringVar()
                result_var.set("")  # Initialize as empty
                non_blocking_checklist(
                    parent=self.root,
                    title="Select Controller to Save",
                    items=pump_id_list,
                    result_var=result_var,
                )  # Trigger non-blocking checklist

                def on_selection(*args):  # act once the user makes a selection
                    result = result_var.get()
                    if result == "":  # check if empty
                        result_var.trace_remove("write", trace_id)  # Untrace
                        return
                    selected_pumps = result.split(",")
                    if "All" in selected_pumps:
                        for id, connected in self.pump_controllers_connected.items():
                            if connected:
                                self.pump_controllers_send_queue.put(f"{id}:0:save")
                                logging.info(
                                    f"Signal sent to save pump {id} configuration."
                                )
                    else:
                        for pump in selected_pumps:
                            pump_id = int(pump.split(" ")[1])
                            self.pump_controllers_send_queue.put(f"{pump_id}:0:save")
                            logging.info(
                                f"Signal sent to save pump {pump_id} configuration."
                            )

                    result_var.trace_remove("write", trace_id)  # Untrace

                trace_id = result_var.trace_add("write", on_selection)  # Trace
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function save_pump_config: {e}",
                )

    def pumps_shutdown(self, confirmation=False, all=True, controller_id=None):
        if any(self.pump_controllers_connected.values()):
            try:
                if not confirmation or messagebox.askyesno(
                    "Shutdown All",
                    "Are you sure you want to shutdown pumps on all controllers?",
                ):
                    if all:
                        for (
                            id,
                            connection_status,
                        ) in self.pump_controllers_connected.items():
                            if connection_status:
                                self.pump_controllers_send_queue.put(f"{id}:0:shutdown")
                                self.update_status(controller_id=id)
                                logging.info(
                                    f"Signal sent for emergency shutdown of pump controller {id}."
                                )
                    else:
                        if (
                            controller_id
                            and self.pump_controllers_connected[controller_id]
                        ):
                            self.pump_controllers_send_queue.put(
                                f"{controller_id}:0:shutdown"
                            )
                            self.update_status(controller_id=controller_id)
                            logging.info(
                                f"Signal sent for emergency shutdown of pump controller {controller_id}."
                            )
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function pumps_shutdown: {e}",
                )

    def stop_procedure(self, message=False):
        try:
            if self.scheduled_task:
                self.root.after_cancel(self.scheduled_task)
                self.scheduled_task = None
            self.start_time_ns = -1
            self.total_procedure_time_ns = -1
            self.current_index = -1
            self.pause_timepoint_ns = -1
            self.pause_duration_ns = 0
            # call a emergency shutdown in case the power is still on
            self.pumps_shutdown()
            # update the status
            for id, connection_status in self.pump_controllers_connected.items():
                if connection_status:
                    self.update_status(controller_id=id)
                    # enable the disconnect button
                    self.pump_controllers_id_to_widget_map[id][
                        "disconnect_button"
                    ].config(state=tk.NORMAL)
            # disable the buttons
            self.stop_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.continue_button.config(state=tk.DISABLED)
            logging.info("Procedure stopped.")
            if message:
                non_blocking_messagebox(
                    parent=self.root,
                    title="Procedure Stopped",
                    message="The procedure has been stopped.",
                )
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function stop_procedure: {e}",
            )

    def pause_procedure(self):
        try:
            if self.scheduled_task:
                self.root.after_cancel(self.scheduled_task)
                self.scheduled_task = None
            self.pause_timepoint_ns = time.monotonic_ns()
            self.pause_button.config(state=tk.DISABLED)
            self.continue_button.config(state=tk.NORMAL)
            self.end_time_value.config(text="")
            logging.info("Procedure paused.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function pause_procedure: {e}",
            )

    def continue_procedure(self):
        try:
            if self.pause_timepoint_ns != -1:
                self.pause_duration_ns += time.monotonic_ns() - self.pause_timepoint_ns
                self.pause_timepoint_ns = -1
            self.pause_button.config(state=tk.NORMAL)
            self.continue_button.config(state=tk.DISABLED)
            self.execute_procedure(self.current_index)
            logging.info("Procedure continued.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function continue_procedure: {e}",
            )

    # send_command will remove the first item from the queue and send it
    def send_command(self):
        if not self.pump_controllers_send_queue.empty():
            try:
                command = self.pump_controllers_send_queue.get(block=False)
                controller_id = int(command.split(":")[0])
                # assemble the command (everything after the first colon, the rest might also contain colons)
                command = command.split(":", 1)[1]
                if self.pump_controllers[
                    controller_id
                ].is_open:  # check if the controller is connected
                    self.pump_controllers[controller_id].write(f"{command}\n".encode())
                    if "time" not in command:
                        logging.debug(f"PC -> Pico {controller_id}: {command}")
                else:
                    logging.error(
                        f"Error: Trying to send command to disconnected controller {controller_id}"
                    )
            except serial.SerialException as e:
                self.disconnect(controller_id, False)
                logging.error(f"Error: controller {controller_id} {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"Failed to send command to pump controller {controller_id} with error: {e}",
                )
            except Exception as e:
                self.disconnect(controller_id, False)
                logging.error(f"Error: controller {controller_id} {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function send_command: {e}",
                )

    def send_command_as(self):
        try:
            if self.autosamplers and not self.autosamplers_send_queue.empty():
                command = self.autosamplers_send_queue.get(block=False)
                self.autosamplers.write(f"{command}\n".encode())
                if "time" not in command:
                    logging.debug(f"PC -> Autosampler: {command}")
        except serial.SerialException as e:
            self.disconnect_as(False)
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Failed to send command to Autosampler with error: {e}",
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function send_command_as: {e}",
            )

    def read_serial(self):
        try:
            for controller_id, serial_port_obj in self.pump_controllers.items():
                if (
                    serial_port_obj
                    and serial_port_obj.is_open
                    and serial_port_obj.in_waiting
                ):
                    response = serial_port_obj.readline().decode("utf-8").strip()
                    if "RTC Time" not in response:
                        logging.debug(f"Pico {controller_id} -> PC: {response}")
                    if "Info" in response:
                        self.add_pump_widgets(controller_id, response)
                    elif "Status" in response:
                        self.update_pump_status(controller_id, response)
                    elif "RTC Time" in response:
                        self.parse_rtc_time(
                            controller_id, response, is_Autosampler=False
                        )
                    elif "Success" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Success",
                            message=f"Pump Controller {controller_id}: {response}",
                        )
                    elif "Error" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message=f"Pump Controller {controller_id}: {response}",
                        )
        except serial.SerialException as e:
            self.disconnect(controller_id, False)
            logging.error(f"Error: controller {controller_id} {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Failed to read from pump controller {controller_id} with error: {e}",
            )
        except Exception as e:
            self.disconnect(controller_id, False)
            logging.error(f"Error: controller {controller_id} {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function read_serial: {e}",
            )

    def update_pump_status(self, controller_id, response):
        status_pattern = re.compile(
            r"Pump(\d+) Status: Power: (ON|OFF), Direction: (CW|CCW)"
        )
        matches = status_pattern.findall(response)

        for match in matches:
            pump_id, power_status, direction_status = match
            pump_id = int(pump_id)
            if pump_id in self.pumps:
                # check the controller id of the pump
                if self.pump_ids_to_controller_ids[pump_id] == controller_id:
                    self.pumps[pump_id]["power_status"] = power_status
                    self.pumps[pump_id]["direction_status"] = direction_status
                    self.pumps[pump_id]["power_label"].config(
                        text=f"Power Status: {power_status}"
                    )
                    self.pumps[pump_id]["direction_label"].config(
                        text=f"Direction Status: {direction_status}"
                    )
                else:
                    logging.error(
                        f"We received a status update for pump {pump_id} from the wrong controller {controller_id}. The current controller for this pump is {self.pump_ids_to_controller_ids[pump_id]}.\n You should remove the duplicate pump id from one of the above controllers to resolve this issue."
                    )
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message=f"We received a status update for pump {pump_id} from the wrong controller {controller_id}. The current controller for this pump is {self.pump_ids_to_controller_ids[pump_id]}.\n You should remove the duplicate pump id from one of the above controllers to resolve this issue.",
                    )
            else:
                # This mean we somehow received a status update for a pump that does not exist
                # clear the pumps widgets and re-query the pump info
                self.remove_pumps_widgets(remove_all=True)
                for id, connection_status in self.pump_controllers_connected.items():
                    if connection_status:
                        self.query_pump_info(controller_id=id)
                logging.error(
                    f"We received a status update for a pump {pump_id} that does not exist from controller {controller_id}. Re-querying all pump info."
                )

    def read_serial_as(self):
        try:
            if self.autosamplers and self.autosamplers.in_waiting:
                response = self.autosamplers.readline().decode("utf-8").strip()

                if "RTC Time" not in response:
                    logging.debug(f"Autosampler -> PC: {response}")

                if "Autosampler Configuration:" in response:
                    # Extract the JSON part of the response
                    config_str = response.replace(
                        "Autosampler Configuration:", ""
                    ).strip()
                    try:
                        autosampler_config = json.loads(config_str)
                        slots = list(autosampler_config.keys())
                        # the slow have pure number and alplabet string
                        # sort the slots by the number first and then the alphabet
                        slots.sort(
                            key=lambda x: (
                                not x.isdigit(),
                                int(x) if x.isdigit() else x,
                            )
                        )
                        self.slot_combobox_as["values"] = slots
                        if slots:
                            self.slot_combobox_as.current(
                                0
                            )  # Set the first slot as default
                        logging.info(f"Slots populated: {slots}")
                    except json.JSONDecodeError as e:
                        logging.error(f"Error decoding autosampler configuration: {e}")
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message="Failed to parse autosampler configuration with error: {e}",
                        )
                elif "RTC Time" in response:
                    self.parse_rtc_time(
                        controller_id=None, response=response, is_Autosampler=True
                    )
                elif "Error" in response:
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message=f"Autosampler: {response}",
                    )
                elif "Success" in response:
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Success",
                        message=f"Autosampler: {response}",
                    )
        except serial.SerialException as e:
            self.disconnect_as(False)
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Failed to read from Autosampler with error: {e}",
            )
        except Exception as e:
            self.disconnect_as(False)
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function read_serial_as: {e}",
            )

    def goto_position_as(self, position=None):
        if self.autosamplers:
            try:
                if position is None:
                    position = self.position_entry_as.get().strip()
                if position and position.isdigit():
                    command = f"position:{position}"
                    self.autosamplers_send_queue.put(command)
                    logging.info(f"Autosampler command sent: {command}")
                else:
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Invalid input, please enter a valid position number.",
                    )
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function goto_position_as: {e}",
                )

    def goto_slot_as(self, slot=None):
        if self.autosamplers:
            try:
                if slot is None:
                    slot = self.slot_combobox_as.get().strip()
                if slot:
                    command = f"slot:{slot}"
                    self.autosamplers_send_queue.put(command)
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function goto_slot_as: {e}",
                )

    def add_pump_widgets(self, controller_id, response):
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
                if (
                    pump_id not in self.pumps
                ):  # pump does not exist, create a new pump frame
                    # update both mappings
                    self.pump_ids_to_controller_ids[pump_id] = controller_id
                    if controller_id not in self.controller_ids_to_pump_ids:
                        self.controller_ids_to_pump_ids[controller_id] = []
                    self.controller_ids_to_pump_ids[controller_id].append(pump_id)
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
                        command=lambda pid=pump_id: self.remove_pump(
                            remove_all=False, pump_id=pid
                        ),
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
                elif self.pump_ids_to_controller_ids[pump_id] == controller_id:
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
                else:  # we have a pump with the same id but different controller
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error: Duplicate Pump Id",
                        message=f"Pump {pump_id} in controller {controller_id} already exists in controller {self.pump_ids_to_controller_ids[pump_id]}!\nDuplicate pump ids are not allow!\nConnect ONLY to one of the above controllers and remove the duplicated pump id to resolve this issue.",
                    )
            self.on_tab_change(event=None, notebook=self.notebook)
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function add_pump_widgets: {e}",
            )

    # a function to clear all pumps or or remove all pump under a controller or remove a specific pump
    def remove_pumps_widgets(self, remove_all=True, pump_id=None, controller_id=None):
        if remove_all:
            for widget in self.pumps_frame.winfo_children():
                widget.destroy()
            # destroy the pumps frame
            self.pumps_frame.destroy()
            # recreate pumps frame inside the manual control frame
            self.pumps_frame = ttk.Frame(self.manual_control_frame)
            self.pumps_frame.grid(
                row=1,
                column=0,
                columnspan=8,
                padx=global_pad_x,
                pady=global_pad_y,
                sticky="NSEW",
            )
            self.pumps.clear()
            self.pump_ids_to_controller_ids.clear()
            self.controller_ids_to_pump_ids.clear()
        else:
            if pump_id:  # we now remove a specific pump
                if pump_id in self.pumps:
                    self.pumps[pump_id]["frame"].destroy()
                    self.pumps.pop(pump_id)
                    controller_id = self.pump_ids_to_controller_ids.pop(pump_id)
                    self.controller_ids_to_pump_ids[controller_id].remove(pump_id)
            elif controller_id:  # we now remove all pumps under a specific controller
                if controller_id in self.controller_ids_to_pump_ids:
                    for pump_id in self.controller_ids_to_pump_ids[controller_id]:
                        self.pumps[pump_id]["frame"].destroy()
                        self.pumps.pop(pump_id)
                        self.pump_ids_to_controller_ids.pop(pump_id)
                    self.controller_ids_to_pump_ids.pop(controller_id)
        self.on_tab_change(event=None, notebook=self.notebook)

    def load_recipe(self):
        file_path = filedialog.askopenfilename(
            initialdir=os.getcwd(),
            title="Select a Recipe File",
            filetypes=(("CSV/Excel files", "*.csv *.xlsx"), ("all files", "*.*")),
        )
        if file_path:
            try:
                self.stop_procedure()
                self.clear_recipe()
                if file_path.endswith(".csv"):
                    temp_df = pd.read_csv(
                        file_path, keep_default_na=False, dtype=object
                    )
                elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                    # we default read the "Do Not Edit (Export Settings)" sheet
                    if (
                        "Do Not Edit (Export Settings)"
                        in pd.ExcelFile(file_path).sheet_names
                    ):
                        temp_df = pd.read_excel(
                            file_path,
                            sheet_name="Do Not Edit (Export Settings)",
                            keep_default_na=False,
                            dtype=object,
                        )
                    else:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Warning",
                            message="The recipe file does not contain the 'Do Not Edit (Export Settings)' sheet.\nPlease select a sheet to load.",
                        )
                        return
                elif file_path.endswith(".pkl"):
                    temp_df = pd.read_pickle(file_path, compression=None)
                elif file_path.endswith(".json"):
                    temp_df = pd.read_json(file_path, dtype=False)
                else:
                    raise ValueError("Unsupported file format.")

                # Clean the data frame
                # search for any header containing the keyword "time"
                recipe_headers = [
                    (col_idx, cell)
                    for col_idx, cell in enumerate(temp_df.columns)
                    if isinstance(cell, str) and "time" in cell.lower()
                ]
                self.recipe_df_time_header_index, recipe_header = recipe_headers[0]
                # look for the second anchor named "Echem Steps" , we will split the dataframe into two based on this index
                echem_headers = [
                    (col_idx, cell)
                    for col_idx, cell in enumerate(temp_df.columns)
                    if isinstance(cell, str) and "echem steps" in cell.lower()
                ]
                echem_header_col_idx, echem_header = echem_headers[0]

                # Split the dataframe until echem_header_col_idx, that is the recipe data
                self.recipe_df = temp_df.iloc[:, 0:echem_header_col_idx]
                self.eChem_sequence_df = temp_df.iloc[:, echem_header_col_idx:]
                # drop rows where time column has NaN
                self.recipe_df = self.recipe_df.dropna(axis=0, subset=[recipe_header])
                self.recipe_df = self.recipe_df.drop(
                    self.recipe_df[self.recipe_df[recipe_header] == ""].index,
                )
                self.recipe_df = self.recipe_df.reset_index(drop=True)

                # drop tows where echem_header has NaN or empty string
                self.eChem_sequence_df = self.eChem_sequence_df.dropna(
                    axis=0, subset=[echem_header]
                )
                self.eChem_sequence_df = self.eChem_sequence_df.drop(
                    self.eChem_sequence_df[
                        self.eChem_sequence_df[echem_header] == ""
                    ].index,
                )
                self.eChem_sequence_df = self.eChem_sequence_df.reset_index(drop=True)
                # convert the time column to float
                self.recipe_df[recipe_header] = self.recipe_df[recipe_header].apply(
                    float
                )
                # check if the time points are in ascending order
                if not self.recipe_df[recipe_header].is_monotonic_increasing:
                    raise ValueError(
                        "Time points are required in monotonically increasing order."
                    )
                # check if there is duplicate time points
                if self.recipe_df[recipe_header].duplicated().any():
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
                    self.recipe_table.column(col, width=len(col) * 10, anchor="center")

                for index, row in self.recipe_df.iterrows():
                    # Convert all cells to strings, allow up to 2 significant figures for floats
                    values = [
                        (f"{cell:.2f}" if isinstance(cell, float) else str(cell))
                        for cell in row
                    ]
                    self.recipe_table.insert("", "end", values=values)
                    self.recipe_rows.append(
                        (index, self.recipe_table.get_children()[-1])
                    )
                # double width for the first column
                self.recipe_table.column(recipe_header, width=100, anchor="center")
                # set width for the notes column if it exists
                if "Notes" in columns:
                    self.recipe_table.column("Notes", width=150, anchor="center")
                if "Progress Bar" in columns:
                    self.recipe_table.column("Progress Bar", width=150, anchor="center")
                if "Remaining Time" in columns:
                    self.recipe_table.column(
                        "Remaining Time", width=150, anchor="center"
                    )

                # Enable the start button
                self.start_button.config(state=tk.NORMAL)
                self.on_tab_change(event=None, notebook=self.notebook)

                # now setup the eChem table
                columns = list(self.eChem_sequence_df.columns)
                self.eChem_sequence_table = ttk.Treeview(
                    self.eChem_sequence_table_frame,
                    columns=columns,
                    show="headings",
                )
                # Create a scrollbar
                self.scrollbar_EC = ttk.Scrollbar(
                    self.eChem_sequence_table_frame,
                    orient="vertical",
                    command=self.eChem_sequence_table.yview,
                )
                self.eChem_sequence_table.configure(
                    yscrollcommand=self.scrollbar_EC.set
                )
                self.scrollbar_EC.grid(row=0, column=1, sticky="NS")
                self.eChem_sequence_table.grid(
                    row=0,
                    column=0,
                    padx=global_pad_x,
                    pady=global_pad_y,
                    sticky="NSEW",
                )
                for col in columns:
                    self.eChem_sequence_table.heading(col, text=col)
                    self.eChem_sequence_table.column(
                        col, width=len(col) * 10, anchor="center"
                    )
                for index, row in self.eChem_sequence_df.iterrows():
                    # Convert all cells to strings, allow up to 2 significant figures for floats
                    values = [
                        (f"{cell:.2f}" if isinstance(cell, float) else str(cell))
                        for cell in row
                    ]
                    self.eChem_sequence_table.insert("", "end", values=values)

                # pop a unblocking message box to ask user if they want to convert the eChem sequence to a GSequence
                if not self.eChem_sequence_df.empty:
                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Convert eChem Sequence",
                        message="Do you want to convert the included eChem sequence to a GSequence file?",
                        buttons=["Yes", "No"],
                        callback=self.convert_to_gsequence,
                    )

                logging.info(f"Recipe file loaded successfully: {file_path}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="File Load",
                    message=f"Recipe file loaded successfully: {file_path}",
                )
            except Exception as e:
                # shutdown the procedure if it is running
                self.stop_procedure()
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function load_recipe: {e}",
                )
                logging.error(f"Error: {e}")

    # a function to clear the recipe table
    def clear_recipe(self):
        try:
            # clear the recipe table
            self.recipe_df = None
            self.recipe_df_time_header_index = -1
            self.recipe_rows = []
            self.recipe_table.destroy()  # destroy the recipe table
            self.scrollbar.destroy()  # destroy the scrollbar
            # recreate the recipe table
            self.recipe_table = ttk.Frame(self.recipe_table_frame)
            self.recipe_table.grid(
                row=0, column=0, padx=global_pad_x, pady=global_pad_y, sticky="NSEW"
            )
            # clear the progress bar
            self.total_progress_bar["value"] = 0
            self.remaining_time_value.config(text="")
            self.end_time_value.config(text="")

            # clear the eChem table
            self.eChem_sequence_df = None
            self.eChem_sequence_df_time_header_index = -1
            self.eChem_sequence_table.destroy()  # destroy the eChem table
            self.scrollbar_EC.destroy()  # destroy the scrollbar
            # recreate the eChem table
            self.eChem_sequence_table = ttk.Frame(self.eChem_sequence_table_frame)
            self.eChem_sequence_table.grid(
                row=0,
                column=0,
                padx=global_pad_x,
                pady=global_pad_y,
                sticky="NSEW",
            )

            # disable all procedure buttons
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.DISABLED)
            self.continue_button.config(state=tk.DISABLED)
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function clear_recipe: {e}",
            )

    def start_procedure(self):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        # require at least one MCU connection
        if not self.autosamplers and not any(self.pump_controllers_connected.values()):
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message="No controller connection. Please connect to at least one controller to continue.",
            )
            return
        # display warning if only one MCU is connected
        if not any(self.pump_controllers_connected.values()) or not self.autosamplers:
            message = "Only one type of controller connected. Continue?"
            if not messagebox.askyesno("Warning", message):
                return

        logging.info("Starting procedure...")

        try:
            self.stop_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.NORMAL)
            self.continue_button.config(state=tk.DISABLED)
            # disable the disconnect button for connected controllers
            for (
                controller_id,
                connection_status,
            ) in self.pump_controllers_connected.items():
                if connection_status:
                    self.pump_controllers_id_to_widget_map[controller_id][
                        "disconnect_button"
                    ].config(state=tk.DISABLED)

            # clear the stop time and pause time
            self.pause_timepoint_ns = -1

            # cancel the scheduled task if it exists
            if self.scheduled_task:
                self.root.after_cancel(self.scheduled_task)
                self.scheduled_task = None

            # calculate the total procedure time, max time point in the first column
            self.total_procedure_time_ns = convert_minutes_to_ns(
                float(self.recipe_df.iloc[:, self.recipe_df_time_header_index].max())
            )

            # clear the "Progress Bar" and "Remaining Time" columns in the recipe table
            for _, child in self.recipe_rows:
                self.recipe_table.set(child, "Progress Bar", "")
                self.recipe_table.set(child, "Remaining Time", "")

            # record start time
            self.start_time_ns = time.monotonic_ns() - self.pause_duration_ns
            self.current_index = 0
            self.execute_procedure()
        except Exception as e:
            # stop the procedure if an error occurs
            self.stop_procedure()
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function start_procedure: {e}",
            )

    def execute_procedure(self, index=0):
        if self.recipe_df is None or self.recipe_df.empty:
            non_blocking_messagebox(
                parent=self.root, title="Error", message="No recipe file loaded."
            )
            logging.error("No recipe data to execute.")
            return

        try:
            if index >= len(self.recipe_df):
                # update progress bar and remaining time
                self.update_progress()
                self.start_time_ns = -1
                self.total_procedure_time_ns = -1
                self.current_index = -1
                # call a emergency shutdown in case the power is still on
                self.pumps_shutdown()
                logging.info("Procedure completed.")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Procedure Complete",
                    message=f"The procedure has been completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                )
                # disable the stop button
                self.stop_button.config(state=tk.DISABLED)
                self.pause_button.config(state=tk.DISABLED)
                self.continue_button.config(state=tk.DISABLED)
                return

            self.current_index = index
            row = self.recipe_df.iloc[index]
            target_time_ns = convert_minutes_to_ns(
                float(row.iloc[self.recipe_df_time_header_index])
            )
            elapsed_time_ns = (
                time.monotonic_ns() - self.start_time_ns - self.pause_duration_ns
            )
            # calculate the remaining time for the current step
            current_step_remaining_time_ns = target_time_ns - elapsed_time_ns

            # If there is time remaining, sleep for half of the remaining time
            if current_step_remaining_time_ns > 0:
                intended_sleep_time_ms = max(
                    100,
                    current_step_remaining_time_ns // 2 // NANOSECONDS_PER_MILLISECOND,
                )
                # convert from nanoseconds to milliseconds
                self.scheduled_task = self.root.after(
                    int(intended_sleep_time_ms),
                    self.execute_procedure,
                    index,
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
            auto_sampler_actions_slots = {
                col: row[col] for col in row.index if col.startswith("Autosampler")
            }
            auto_sampler_actions_positions = {
                col: row[col]
                for col in row.index
                if col.startswith("Autosampler_position")
            }

            # issue a one-time status update for all pumps and autosampler
            for id, connection_status in self.pump_controllers_connected.items():
                if connection_status:
                    self.update_status(controller_id=id)
            self.execute_actions(
                index,
                pump_actions,
                valve_actions,
                auto_sampler_actions_slots,
                auto_sampler_actions_positions,
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function execute_procedure: {e}",
            )

    def execute_actions(
        self,
        index,
        pump_actions,
        valve_actions,
        auto_sampler_actions_slots,
        auto_sampler_actions_positions,
    ):
        # Process power toggling
        process_pump_actions(
            pumps=self.pumps,
            index=index,
            actions=pump_actions,
            action_type="power",
            status_key="power_status",
            toggle_function=self.toggle_power,
        )
        # Process direction toggling
        process_pump_actions(
            pumps=self.pumps,
            index=index,
            actions=valve_actions,
            action_type="direction",
            status_key="direction_status",
            toggle_function=self.toggle_direction,
        )

        for _, slot in auto_sampler_actions_slots.items():
            if pd.isna(slot) or slot == "":
                continue
            self.goto_slot_as(str(slot))

        for _, position in auto_sampler_actions_positions.items():
            if pd.isna(position) or position == "":
                continue
            # check if the position is a number
            if position.isdigit():
                self.goto_position_as(int(position))
            else:
                logging.error(
                    f"Warning: Invalid autosampler position: {position} at index {index}"
                )

        # update status for all pumps and autosampler
        for id, connection_status in self.pump_controllers_connected.items():
            if connection_status:
                self.update_status(controller_id=id)
        self.execute_procedure(index + 1)

    def update_progress(self):
        if (
            self.total_procedure_time_ns == -1  # Check if not started
            or self.recipe_df is None
            or self.recipe_df.empty
            or self.pause_timepoint_ns != -1  # Check if paused
        ):
            return

        elapsed_time_ns = (
            time.monotonic_ns() - self.start_time_ns - self.pause_duration_ns
        )
        # Handle total_procedure_time_ns being zero
        if self.total_procedure_time_ns <= 0:
            total_progress = 100
            remaining_time_ns = 0
        else:
            total_progress = min(
                100, (elapsed_time_ns / self.total_procedure_time_ns) * 100
            )
            remaining_time_ns = max(
                0,
                self.total_procedure_time_ns - elapsed_time_ns,
            )

        self.total_progress_bar["value"] = int(total_progress)
        self.remaining_time_value.config(
            text=f"{convert_ns_to_timestr(int(remaining_time_ns))}"
        )
        end_time = datetime.now() + timedelta(
            seconds=remaining_time_ns / NANOSECONDS_PER_SECOND
        )
        formatted_end_time = end_time.strftime("%Y-%m-%d %a %H:%M:%S")
        self.end_time_value.config(text=f"{formatted_end_time}")

        # Update the recipe table with individual progress and remaining time
        for i, child in self.recipe_rows:
            time_stamp_ns = convert_minutes_to_ns(
                float(self.recipe_df.iloc[i].iloc[self.recipe_df_time_header_index])
            )

            # if the time stamp is in the future, break the loop
            if elapsed_time_ns < time_stamp_ns:
                break
            else:
                # Calculate progress for each step
                if i < len(self.recipe_df) - 1:
                    next_row = self.recipe_df.iloc[i + 1]
                    next_time_stamp_ns = convert_minutes_to_ns(
                        float(next_row.iloc[self.recipe_df_time_header_index])
                    )
                    time_interval = next_time_stamp_ns - time_stamp_ns
                    if time_interval > 0:
                        # handle the case where the next row has the same timestamp
                        row_progress = int(
                            min(
                                100,
                                ((elapsed_time_ns - time_stamp_ns) / time_interval)
                                * 100,
                            )
                        )
                        remaining_time_row_ns = max(
                            0,
                            next_time_stamp_ns - elapsed_time_ns,
                        )
                    else:
                        # If the next row has the same timestamp, mark the progress as 100%
                        row_progress = 100
                        remaining_time_row_ns = 0
                else:
                    row_progress = 100
                    remaining_time_row_ns = 0

                # Update only the "Progress Bar" and "Remaining Time" columns
                self.recipe_table.set(child, "Progress Bar", f"{row_progress}%")
                self.recipe_table.set(
                    child,
                    "Remaining Time",
                    f"{convert_ns_to_timestr(int(remaining_time_row_ns))}",
                )

    def add_pump(self):
        # if we have any connected pump controller, we can add a pump
        if not any(self.pump_controllers_connected.values()):
            non_blocking_messagebox(
                parent=self.root, title="Error", message="Not connected to Pico."
            )
            return

        try:
            controller_list = [
                f"Controller {id}"
                for id, connected in self.pump_controllers_connected.items()
                if connected
            ]
            result_var = tk.StringVar()
            result_var.set("")  # Initialize as empty
            non_blocking_single_select(
                parent=self.root,
                title="Select Controller for Pump",
                items=controller_list,
                result_var=result_var,
            )  # Trigger non-blocking selection dialog

            def on_selection(*args):
                result = result_var.get()
                if result == "":
                    result_var.trace_remove("write", trace_id)
                    return
                selected_controller = result  # Get the selected controller
                controller_id = int(selected_controller.split(" ")[1])

                pump_id = max(self.pumps.keys(), default=0) + 1
                self.add_pump_widgets(
                    controller_id=controller_id,
                    response=f"Pump{pump_id} Info: Power Pin: -1, Direction Pin: -1, Initial Power Pin Value: 0, Initial Direction Pin Value: 0, Current Power Status: OFF, Current Direction Status: CCW",
                )
                non_blocking_messagebox(
                    parent=self.root,
                    title="Success",
                    message=f"Pump {pump_id} added to {selected_controller}.",
                )
                result_var.trace_remove("write", trace_id)  # Untrace

            trace_id = result_var.trace_add("write", on_selection)  # trace the variable
        except Exception as e:
            logging.error(f"Error adding pump: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred while adding the pump: {e}",
            )

    def edit_pump(self, pump_id):
        # Find the controller ID for the pump
        controller_id = self.pump_ids_to_controller_ids[pump_id]
        pump = self.pumps[pump_id]

        # Define fields for the input dialog
        fields = [
            {
                "label": "Power Pin",
                "type": "text",
                "initial_value": int(pump["power_pin"]),
            },
            {
                "label": "Direction Pin",
                "type": "text",
                "initial_value": int(pump["direction_pin"]),
            },
            {
                "label": "Initial Power Pin Value",
                "type": "text",
                "initial_value": int(pump["initial_power_pin_value"]),
            },
            {
                "label": "Initial Direction Pin Value",
                "type": "text",
                "initial_value": int(pump["initial_direction_pin_value"]),
            },
            {
                "label": "Initial Power Status",
                "type": "dropdown",
                "choices": ["ON", "OFF"],
                "initial_value": pump["power_status"],
            },
            {
                "label": "Initial Direction Status",
                "type": "dropdown",
                "choices": ["CW", "CCW"],
                "initial_value": pump["direction_status"],
            },
        ]

        # Result variable
        result_var = tk.StringVar()
        result_var.set("")  # Initialize as empty

        def on_result(*args):
            result = result_var.get()
            if not result:
                result_var.trace_remove("write", trace_id)  # Untrace on cancel
                return
            try:
                inputs = json.loads(result)
                self.register_pump(
                    controller_id=controller_id,
                    pump_id=pump_id,
                    power_pin=int(inputs["Power Pin"]),
                    direction_pin=int(inputs["Direction Pin"]),
                    initial_power_pin_value=int(inputs["Initial Power Pin Value"]),
                    initial_direction_pin_value=int(
                        inputs["Initial Direction Pin Value"]
                    ),
                    initial_power_status=inputs["Initial Power Status"],
                    initial_direction_status=inputs["Initial Direction Status"],
                )
                # update the pump info
                self.query_pump_info(controller_id)
            except Exception as e:
                logging.error(f"Error updating pump: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred while updating the pump: {e}",
                )
            result_var.trace_remove("write", trace_id)  # Untrace after completion

        trace_id = result_var.trace_add("write", on_result)  # Trace the variable
        non_blocking_input_dialog(
            parent=self.root,
            title=f"Edit Pump {pump_id}",
            fields=fields,
            result_var=result_var,
        )

    # on closing, minimize window to the system tray
    def on_closing(self) -> None:
        if self.first_close:
            # pop a message box to confirm exit the first time
            non_blocking_custom_messagebox(
                parent=self.root,
                title="Quit",
                message="Do you want to quit or minimize to tray?",
                buttons=["Quit", "Minimize", "Cancel"],
                callback=self.on_closing_handle,
            )
        else:
            self.minimize_to_tray_icon()

    def on_closing_handle(self, response):
        if response == "Quit":
            self.exit(icon=None)
        elif response == "Minimize":
            self.first_close = False
            self.minimize_to_tray_icon()

    def exit(self, icon) -> None:
        if icon is not None:
            icon.stop()
        # stop the procedure if it is running
        self.stop_procedure()
        # close all connections
        for id, connection_status in self.pump_controllers_connected.items():
            if connection_status:
                self.disconnect(id, show_message=False)
        if self.autosamplers:
            self.disconnect_as(show_message=False)
        root.quit()

    def show_window(self, icon) -> None:
        icon.stop()
        root.deiconify()

    # A system tray icon which have two menu options: "show window" and "exit", when hovered over the icon, it will display the remaining procedure time if the procedure is running, else display "Pico Controller", the main loop of the program will still be running in the background
    def minimize_to_tray_icon(self) -> None:
        try:
            # hide the window
            root.withdraw()
            menu = (
                pystray.MenuItem("Show", self.show_window),
                pystray.MenuItem("Exit", self.exit),
            )
            icon = pystray.Icon(
                name="Pico EChem Automation Controller",
                icon=self.image_white,
                title="Pico EChem Automation Controller",
                menu=menu,
            )
            icon.run_detached()
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function minimize_to_tray_icon: {e}",
            )

    def convert_to_gsequence(self, response):
        if response == "No" or self.eChem_sequence_df is None:
            return
        try:
            # Generate GSequence
            new_method_tree = generate_gsequence(
                df=self.eChem_sequence_df,
                template_method_path=resource_path(
                    os.path.join("xmls", "combined_sequencer_methods.xml")
                ),
            )
            if new_method_tree is not None:
                non_blocking_messagebox(
                    parent=self.root,
                    title="Success",
                    message="GSequence generated successfully, select a save location.",
                )
                # Save the file
                save_path = filedialog.asksaveasfilename(
                    title="Save GSequence File",
                    defaultextension=".GSequence",
                    filetypes=[
                        ("GSequence files", "*.GSequence"),
                        ("All files", "*.*"),
                    ],
                )
                if save_path:
                    new_method_tree.write(
                        save_path, encoding="utf-8", xml_declaration=True
                    )
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Success",
                        message=f"GSequence saved to {save_path}",
                    )
        except Exception as e:
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Error generating GSequence: {e}",
            )


root = tk.Tk()
root.withdraw()
root.resizable(True, True)
check_lock_file()
root.iconbitmap(resource_path(os.path.join("icons", "icons-red.ico")))
app = PicoController(root)
root.deiconify()
root.geometry(f"+{root.winfo_screenwidth() // 8}+{root.winfo_screenheight() // 8}")
root.protocol("WM_DELETE_WINDOW", app.on_closing)
root.mainloop()
remove_lock_file()
