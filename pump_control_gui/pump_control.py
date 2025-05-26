# pyserial imports
import serial
import serial.tools.list_ports

# gui imports
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk, filedialog
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
from datetime import datetime, timedelta
import bootloader_helpers
from fw_update import PicoFlasherApp
from tkinter_helpers import (
    non_blocking_messagebox,
    non_blocking_custom_messagebox,
    non_blocking_checklist,
    non_blocking_single_select,
    non_blocking_input_dialog,
    label,
    button,
    combobox,
)
from helper_functions import (
    check_lock_file,
    remove_lock_file,
    resource_path,
    convert_minutes_to_ns,
    convert_ns_to_timestr,
    process_pump_actions,
    generate_gsequence,
    get_config,
    save_config,
    setProcessDpiAwareness,
    getScalingFactor,
)

pico_vid = 0x2E8A  # Pi Pico vendor ID

global_pad_x = 2
global_pad_y = 2

global_pad_N = 3
global_pad_S = 3
global_pad_W = 3
global_pad_E = 3

NANOSECONDS_PER_SECOND = 1e9
NANOSECONDS_PER_MILLISECOND = 1e6
NORMAL_FONT_SIZE = 10
LARGE_FONT_SIZE = 11
FONT_FAMILY = "Arial"


class PicoController:
    def __init__(self, root) -> None:
        self.root = root
        self.root.title("Pump Control & Automation")
        self.main_loop_interval_ms = 5  # Main loop interval in milliseconds
        self.config = get_config()

        # port refresh timer
        self.port_refresh_interval_ns = 2 * NANOSECONDS_PER_SECOND
        self.port_refresh_last_ns = -1
        self.serial_wait_time = 0.1  # Serial port wait time in seconds
        self.timeout = 1  # Serial port timeout in seconds

        # instance fields for the serial port and queue
        # we have multiple controller, the key is the id, the value is the serial port object
        self.num_pump_controllers = self.config.get("num_pump_controllers", 3)
        self.config["num_pump_controllers"] = self.num_pump_controllers
        save_config(self.config)
        self.pc = {}
        self.pc_connected = {}  # format is "controller_id: bool"
        self.pc_id_to_widget_map = {}
        self.pc_send_queue = Queue()  # format is "controller_id:command"
        self.pc_rtc_time = {}
        self.pc_names = {}  # format is "controller_id:name"
        # Dictionary to store pump information
        self.pumps = {}
        self.pump_ids_to_controller_ids = {}  # mapping from pump id to the controller id
        self.controller_ids_to_pump_ids = {}
        self.pumps_per_row = 4  # define num of pumps per row in manual control frame
        # instance field for the autosampler serial port
        self.autosampler = serial.Serial(timeout=self.timeout)
        self.autosampler_widget_map = {}
        self.autosampler_send_queue = Queue()
        self.autosampler_rtc_time = "--:--:--"
        self.autosampler_name = "N/A"
        self.autosampler_slots = {}
        # instance field for the potentiostat serial port
        self.potentiostat = serial.Serial(timeout=self.timeout)
        self.potentiostat_widget_map = {}
        self.potentiostat_send_queue = Queue()
        self.potentiostat_rtc_time = "--:--:--"
        self.potentiostat_name = "N/A"
        self.potentiostat_config = {}

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
        self.last_querytime = time.monotonic_ns()

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

        def main_tabview_changed():
            current_tab = self.Tabview.get()
            if current_tab == "Advanced Settings" or current_tab == "Connect":
                self.refresh_ports()

        # a notebook widget to hold the tabs
        self.Tabview = ctk.CTkTabview(self.root, command=main_tabview_changed)
        self.Tabview.pack(
            anchor="center",
            padx=global_pad_x,
            pady=global_pad_y,
        )

        # frame for different tabs
        self.Tabview.add("Setup")
        self.Tabview.add("Schedule")
        self.Tabview.add("Advanced Settings")

        self.create_setup_page(self.Tabview.tab("Setup"))
        self.create_scheduler_page(self.Tabview.tab("Schedule"))
        self.create_advanced_settings_page(self.Tabview.tab("Advanced Settings"))
        for b in self.Tabview._segmented_button._buttons_dict.values():
            b.configure(
                font=(
                    "Arial",
                    int(b.cget("font").cget("size") * 1.75),
                )
            )

        # RTC time frame
        self.rtc_time_frame = ctk.CTkFrame(
            self.root, fg_color="transparent", bg_color="transparent"
        )
        self.rtc_time_frame.pack(anchor="se", padx=global_pad_x, pady=global_pad_y)
        self.create_rtc_time_frame(self.rtc_time_frame)

        # TODO
        style = ttk.Style()
        style.configure(
            ".",
            font=(FONT_FAMILY, NORMAL_FONT_SIZE),
        )
        style.configure(
            "Treeview",
            font=(FONT_FAMILY, NORMAL_FONT_SIZE),
            rowheight=int(NORMAL_FONT_SIZE * 3),
        )
        style.configure(
            "Treeview.Heading",
            font=(FONT_FAMILY, LARGE_FONT_SIZE),
            rowheight=int(LARGE_FONT_SIZE * 3),
        )
        style.configure(
            "TLabelframe",
            background=self.Tabview.tab("Advanced Settings").cget("fg_color"),
        )
        self.refresh_ports()
        self.root.after(self.main_loop_interval_ms, self.main_loop)

    def create_setup_page(self, root_frame):
        """create a striped down version of the create_advanced_settings_page"""

        def c_tabview_changed():
            """Callback for the manual control tabview change."""
            selected_tab = self.setup_view.get()
            if selected_tab == "Connect":
                self.refresh_ports()

        self.setup_view = ctk.CTkTabview(
            root_frame, fg_color="darkgray", command=c_tabview_changed
        )
        self.setup_view.pack(
            anchor="center",
            padx=global_pad_x,
            pady=global_pad_y,
        )
        port_select_frame = self.setup_view.add("Connect")

        # first in the port_select_frame
        # Create a row for each potential pump controller
        for controller_id in range(1, self.num_pump_controllers + 1):
            self.add_pc_connect_widgets(
                root_frame=port_select_frame,
                port_label="Pump Controller",
                controller_id=controller_id,
                row=port_select_frame.grid_size()[1],
            )
        # second in the port_select_frame
        self.add_as_connect_widgets(
            root_frame=port_select_frame,
            row=port_select_frame.grid_size()[1],
        )
        # third in the port_select_frame
        self.add_po_connect_widgets(
            root_frame=port_select_frame,
            row=port_select_frame.grid_size()[1],
        )

        for b in self.setup_view._segmented_button._buttons_dict.values():
            b.configure(
                font=(
                    FONT_FAMILY,
                    int(b.cget("font").cget("size") * 1.5),
                )
            )

    def create_rtc_time_frame(self, root_frame):
        current_row, current_column = 0, 0
        # Pump Controller Time
        self.current_time_label = label(
            root_frame, "Pump Controllers: ", current_row, current_column
        )
        current_column += 1
        self.current_time_value = label(
            root_frame, "--:--:--", current_row, current_column
        )
        current_column += 1
        # Autosampler Time
        self.current_time_label_as = label(
            root_frame, "Autosampler: ", current_row, current_column
        )
        current_column += 1
        self.current_time_value_as = label(
            root_frame, self.autosampler_rtc_time, current_row, current_column
        )
        current_column += 1
        # Potentiostat Time
        self.current_time_label_po = label(
            root_frame, "Potentiostat: ", current_row, current_column
        )
        current_column += 1
        self.current_time_value_po = label(
            root_frame, self.potentiostat_rtc_time, current_row, current_column
        )

    def create_advanced_settings_page(self, root_frame):
        def ac_tabview_changed():
            """Callback for the manual control tabview change."""
            selected_tab = self.advanced_settings_view.get()
            if selected_tab == "Connect" or selected_tab == "Firmware Update":
                self.refresh_ports()

        self.advanced_settings_view = ctk.CTkTabview(
            root_frame, fg_color="darkgray", command=ac_tabview_changed
        )
        self.advanced_settings_view.pack(
            anchor="center",
            padx=global_pad_x,
            pady=global_pad_y,
        )
        port_select_frame = self.advanced_settings_view.add("Connect")

        for controller_id in range(1, self.num_pump_controllers + 1):
            self.add_pc_connect_widgets(
                root_frame=port_select_frame,
                port_label="Pump Controller",
                controller_id=controller_id,
                row=port_select_frame.grid_size()[1],
            )
        self.add_as_connect_widgets(
            root_frame=port_select_frame,
            row=port_select_frame.grid_size()[1],
        )
        self.add_po_connect_widgets(
            root_frame=port_select_frame,
            row=port_select_frame.grid_size()[1],
        )

        pumps_mc_frame = self.advanced_settings_view.add("Pumps Manual Control")
        # first row in the manual control frame, containing all the buttons
        self.manual_control_frame_buttons = ctk.CTkFrame(
            pumps_mc_frame, bg_color="transparent", fg_color="transparent"
        )
        self.manual_control_frame_buttons.pack(
            padx=global_pad_x, pady=global_pad_y, side="top"
        )
        self.add_pump_button = button(
            self.manual_control_frame_buttons, "Add Pump", 0, 0, self.add_pump
        )
        self.clear_pumps_button = button(
            self.manual_control_frame_buttons,
            "Clear All Pumps",
            0,
            1,
            lambda: self.remove_pump(remove_all=True),
        )
        self.save_pumps_button = button(
            self.manual_control_frame_buttons,
            "Save Config to EC",
            0,
            2,
            self.save_pump_config,
        )
        self.emergency_shutdown_button = button(
            self.manual_control_frame_buttons,
            "Shutdown All Pumps",
            0,
            3,
            lambda: self.pumps_shutdown(messageboxConfirmationNeeded=True),
        )
        # second row in the manual control frame, containing the pumps widgets
        self.pumps_frame = ctk.CTkFrame(pumps_mc_frame)
        self.pumps_frame.pack(
            anchor="center",
            padx=global_pad_x,
            pady=global_pad_y,
            fill="both",
            expand=True,
        )

        # Potentiostat Manual Control frame
        po_mc_frame = ctk.CTkFrame(
            self.advanced_settings_view.add("Potentiostat Manual Control"),
            bg_color="transparent",
            fg_color="transparent",
        )
        po_mc_frame.pack(anchor="center", padx=global_pad_x, pady=global_pad_y)
        self.current_trigger_state_label_po = label(po_mc_frame, "Trigger State:", 0, 0)
        self.current_trigger_state_value_po = label(po_mc_frame, "N/A", 0, 1)
        self.trigger_high_button_po = button(
            po_mc_frame,
            "Set High",
            0,
            2,
            lambda: self.set_trigger_po(state="high"),
            state="disabled",
        )
        self.trigger_low_button_po = button(
            po_mc_frame,
            "Set Low",
            0,
            3,
            lambda: self.set_trigger_po(state="low"),
            state="disabled",
        )

        # Autosampler Manual Control frame
        as_mc_frame = self.advanced_settings_view.add("Autosampler Manual Control")
        # Text Entry for Position
        self.position_entry_label_as = label(
            as_mc_frame, "Target Position:", 0, 0, sticky="W"
        )
        self.position_entry_as = ctk.CTkEntry(
            as_mc_frame, placeholder_text="Target position"
        )
        self.position_entry_as.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.current_position_frame_as = ctk.CTkFrame(
            as_mc_frame, bg_color="transparent", fg_color="transparent"
        )
        self.current_position_frame_as.grid(
            row=0, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.current_position_label_as = label(
            self.current_position_frame_as, "Current position: ", 0, 0
        )
        self.current_position_value_as = label(
            self.current_position_frame_as, "N/A", 0, 1
        )
        self.goto_position_button_as = button(
            as_mc_frame,
            "Go to",
            0,
            3,
            self.goto_position_as,
        )
        self.stop_movement_button_as = button(
            as_mc_frame,
            "Stop",
            0,
            4,
            self.stop_movement_as,
        )
        self.set_position_button_as = button(
            as_mc_frame,
            "Set",
            0,
            5,
            self.set_position_as,
        )

        # Slots selection
        self.slot_label_as = label(as_mc_frame, "Available slots:", 1, 0, sticky="W")
        self.slot_combobox_as = combobox(
            as_mc_frame,
            1,
            1,
            state="readonly",
            width=140,
            command=self.on_slot_combobox_selected,
        )
        self.slot_combobox_as.grid(
            row=1, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.slot_position_frame_as = ctk.CTkFrame(
            as_mc_frame, bg_color="transparent", fg_color="transparent"
        )
        self.slot_position_frame_as.grid(
            row=1, column=2, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.slot_position_label_as = label(
            self.slot_position_frame_as, "Slot position:", 0, 0, sticky="W"
        )
        self.slot_position_value_as = label(
            self.slot_position_frame_as, "N/A", 0, 1, sticky="W"
        )
        self.goto_slot_button_as = button(
            as_mc_frame, "Go to slot", 1, 3, self.goto_slot_as
        )
        self.delete_slot_button_as = button(
            as_mc_frame,
            "Delete slot",
            1,
            4,
            self.delete_slot_as,
        )

        self.update_slot_label_as = label(as_mc_frame, "Update slot:", 2, 0, sticky="W")
        self.update_slot_slotname_as = ctk.CTkEntry(
            as_mc_frame, placeholder_text="Slot name"
        )
        self.update_slot_slotname_as.grid(
            row=2, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        self.update_slot_position_as = ctk.CTkEntry(
            as_mc_frame, placeholder_text="Position"
        )
        self.update_slot_position_as.grid(
            row=2,
            column=2,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="W",
        )
        self.update_slot_button_as = button(
            as_mc_frame,
            "Update slot",
            2,
            3,
            self.update_slot_as,
        )

        self.create_firmware_update_page(
            self.advanced_settings_view.add("Firmware Update")
        )
        for b in self.advanced_settings_view._segmented_button._buttons_dict.values():
            b.configure(
                font=(
                    FONT_FAMILY,
                    int(b.cget("font").cget("size") * 1.5),
                )
            )
        self.set_mc_buttons_state("disabled")
        self.set_as_buttons_state("disabled")

    def _add_connect_widgets(
        self,
        root_frame,
        row,
        widget_map,
        label_text: str,
        connect_cmd,
        disconnect_cmd,
        reset_cmd,
        *,
        id=None,
    ):
        # 1) build widgets
        label(root_frame, label_text, row, 0, sticky="W")
        cb = combobox(root_frame, row, 1, state="readonly", width=240)
        st = label(root_frame, "Status: Not connected", row, 2, sticky="W")
        btn_conn = button(root_frame, "Connect", row, 3, connect_cmd)
        btn_disc = button(root_frame, "Disconnect", row, 4, disconnect_cmd)
        btn_rst = button(root_frame, "Reset", row, 5, reset_cmd)
        btn_set_ctl_name = button(
            root_frame,
            "Set Name",
            row,
            6,
            lambda: self.set_controller_name(controller_id=id),
        )

        btn_disc.configure(state="disabled", hover=True)
        btn_rst.configure(state="disabled", hover=True)
        btn_set_ctl_name.configure(state="disabled", hover=True)

        # 2) pick the widget map
        if id is not None:
            map = widget_map.setdefault(id, {})  # pump controllers: keyed by id
        else:
            map = widget_map  # autosampler/potentiostat: just the map

        # 3) on first use, create your SVs + empty lists
        if "comboboxs" not in map:
            map.update(
                {
                    "comboboxs": [],
                    "connect_buttons": [],
                    "disconnect_buttons": [],
                    "reset_buttons": [],
                    "set_name_buttons": [],
                    "comboboxs_sv": ctk.StringVar(master=root_frame),
                    "status_label_sv": ctk.StringVar(
                        master=root_frame, value="Status: Not connected"
                    ),
                }
            )

        # 4) record this widget
        map["comboboxs"].append(cb)
        map["connect_buttons"].append(btn_conn)
        map["disconnect_buttons"].append(btn_disc)
        map["reset_buttons"].append(btn_rst)
        map["set_name_buttons"].append(btn_set_ctl_name)

        # 5) bind them all to the *same* StringVars
        cb.configure(variable=map["comboboxs_sv"])
        st.configure(textvariable=map["status_label_sv"])

    def add_pc_connect_widgets(self, root_frame, port_label, controller_id, row):
        # update the pump_controllers dictionary
        self.pc[controller_id] = serial.Serial()
        self.pc_connected[controller_id] = False
        self.pc_rtc_time[controller_id] = "N/A"
        self.pc_names[controller_id] = "N/A"
        self._add_connect_widgets(
            root_frame,
            row,
            self.pc_id_to_widget_map,
            f"{port_label} {controller_id}:",
            lambda: self.connect_pc(controller_id),
            lambda: self.disconnect_pc(controller_id),
            lambda: self.reset_pc(controller_id),
            id=controller_id,
        )

    def add_as_connect_widgets(self, root_frame, row):
        self._add_connect_widgets(
            root_frame,
            row,
            self.autosampler_widget_map,
            "Autosampler:",
            self.connect_as,
            self.disconnect_as,
            self.reset_as,
        )

    def add_po_connect_widgets(self, root_frame, row):
        self._add_connect_widgets(
            root_frame,
            row,
            self.potentiostat_widget_map,
            "Potentiostat:",
            self.connect_po,
            self.disconnect_po,
            self.reset_po,
        )

    # add the widgets under the provided root_frame
    def create_scheduler_page(self, root_frame):
        current_row = 0  # Row Counter
        local_columnspan = 7

        self.experiment_scheduler_tabview = ctk.CTkTabview(
            root_frame, fg_color="darkgray"
        )
        self.experiment_scheduler_tabview.grid(
            row=current_row,
            column=0,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.recipe_frame = self.experiment_scheduler_tabview.add("Load Recipe")
        for (
            b
        ) in self.experiment_scheduler_tabview._segmented_button._buttons_dict.values():
            b.configure(
                font=(
                    FONT_FAMILY,
                    int(b.cget("font").cget("size") * 1.5),
                )
            )
        current_row = self.recipe_frame.grid_size()[1]
        # first row in the recipe frame, containing the buttons
        self.recipe_frame_buttons = ctk.CTkFrame(
            self.recipe_frame, bg_color="transparent", fg_color="transparent"
        )
        self.recipe_frame_buttons.grid(
            row=0,
            column=0,
            columnspan=local_columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        temp_col_counter = 0
        self.load_recipe_button = button(
            self.recipe_frame_buttons,
            "Load Recipe",
            0,
            temp_col_counter,
            self.load_recipe,
        )
        temp_col_counter += 1
        self.clear_recipe_button = button(
            self.recipe_frame_buttons,
            "Clear Recipe",
            0,
            temp_col_counter,
            self.clear_recipe,
        )
        self.clear_recipe_button.configure(state="disabled", hover=True)
        temp_col_counter += 1
        self.start_button = button(
            self.recipe_frame_buttons,
            "Start",
            0,
            temp_col_counter,
            self.start_procedure,
        )
        self.start_button.configure(state="disabled", hover=True)
        temp_col_counter += 1
        self.stop_button = button(
            self.recipe_frame_buttons,
            "Stop",
            0,
            temp_col_counter,
            lambda: self.stop_procedure(True),
        )
        self.stop_button.configure(state="disabled", hover=True)
        temp_col_counter += 1
        self.pause_button = button(
            self.recipe_frame_buttons,
            "Pause",
            0,
            temp_col_counter,
            self.pause_procedure,
        )
        self.pause_button.configure(state="disabled", hover=True)
        temp_col_counter += 1
        self.continue_button = button(
            self.recipe_frame_buttons,
            "Continue",
            0,
            temp_col_counter,
            self.continue_procedure,
        )
        self.continue_button.configure(state="disabled", hover=True)

        # second row in the recipe_frame_buttons, containing the gSequence and generate button
        self.gSquence_save_frame = ctk.CTkFrame(
            self.recipe_frame_buttons,
            bg_color="transparent",
            fg_color="transparent",
            height=24,
        )
        self.gSquence_save_frame.grid(
            row=1,
            column=0,
            columnspan=3,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        temp_col_counter = 0
        self.gSquence_save_path_label = label(
            self.gSquence_save_frame, "Save Directory:", 0, temp_col_counter, sticky="W"
        )
        temp_col_counter += 1
        self.gSquence_save_path_entry = combobox(
            self.gSquence_save_frame,
            0,
            temp_col_counter,
            values=self.config.get("gSequence_save_dir_history", []),
            state="readonly",
            width=250,
        )
        save_paths = self.gSquence_save_path_entry.cget("values")
        if len(save_paths) > 0:
            self.gSquence_save_path_entry.set(save_paths[0])
        self.gSquence_save_path_entry.bind(
            "<<ComboboxSelected>>", self.update_directory_history
        )
        temp_col_counter += 2
        self.gSquence_save_path_set_button = button(
            self.recipe_frame_buttons,
            "Set",
            1,
            temp_col_counter,
            self.set_gSequence_save_path,
        )
        temp_col_counter += 1
        self.gSquence_save_path_entry_clear_button = button(
            self.recipe_frame_buttons,
            "Clear History",
            1,
            temp_col_counter,
            self.clear_gSequence_save_path_history,
        )
        temp_col_counter += 1
        self.generate_sequence_button = button(
            self.recipe_frame_buttons,
            "Generate",
            1,
            temp_col_counter,
            lambda: non_blocking_custom_messagebox(
                parent=self.root,
                title="Convert to GSequence?",
                message="Convert EChem sequence to a GSequence file?",
                buttons=["Yes", "No"],
                callback=self.convert_to_gsequence,
            ),
        )
        self.generate_sequence_button.configure(state="disabled", hover=True)
        current_row = self.recipe_frame.grid_size()[1]

        # second row in the recipe_frame, containing the recipe table and the EChem sequence table
        self.table_tabview = ctk.CTkTabview(
            self.recipe_frame, fg_color="transparent", bg_color="transparent"
        )
        self.table_tabview.grid(
            row=2,
            column=0,
            columnspan=local_columnspan - 1,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.recipe_table_frame = self.table_tabview.add("Recipe Sequence")
        self.create_recipe_sequence_table(self.recipe_table_frame)

        self.eChem_sequence_table_frame = self.table_tabview.add(
            "Potentiostat Sequence"
        )
        self.create_eChem_sequence_table(self.eChem_sequence_table_frame)
        for b in self.table_tabview._segmented_button._buttons_dict.values():
            b.configure(
                font=(
                    FONT_FAMILY,
                    int(b.cget("font").cget("size") * 1.25),
                )
            )

        # first row in the progress frame, containing the progress bar
        self.total_progress_frame = ctk.CTkFrame(
            self.recipe_frame, bg_color="transparent", fg_color="transparent"
        )
        self.total_progress_frame.grid(
            row=self.recipe_frame.grid_size()[1],
            column=0,
            columnspan=local_columnspan - 1,
            sticky="NSEW",
        )
        self.total_progress_label = label(
            self.total_progress_frame, "Total Progress:", 0, 0, sticky="W"
        )
        self.total_progress_bar = ctk.CTkProgressBar(
            self.total_progress_frame,
            height=15,
            width=500,
            mode="determinate",
            bg_color="transparent",
        )
        self.total_progress_bar.set(0)
        self.total_progress_bar.grid(
            row=0, column=1, padx=global_pad_x, pady=global_pad_y, sticky="W"
        )
        # second row in the progress frame, containing the remaining time and Procedure end time
        self.remaining_time_frame = ctk.CTkFrame(
            self.recipe_frame, bg_color="transparent", fg_color="transparent"
        )
        self.remaining_time_frame.grid(
            row=self.recipe_frame.grid_size()[1],
            column=0,
            columnspan=local_columnspan - 1,
            sticky="NSEW",
        )
        self.remaining_time_label = label(
            self.remaining_time_frame, "Remaining Time:", 0, 0, sticky="W"
        )
        self.remaining_time_value = label(
            self.remaining_time_frame, "", 0, 1, sticky="W"
        )
        self.remaining_time_value.configure(width=100)
        self.end_time_label = label(
            self.remaining_time_frame, "End Time:", 0, 2, sticky="W"
        )
        self.end_time_value = label(self.remaining_time_frame, "", 0, 3, sticky="W")

    def create_recipe_sequence_table(self, root_frame, columns=["", "", "", "", ""]):
        self.recipe_table = ttk.Treeview(root_frame, columns=columns, show="headings")
        self.scrollbar = ctk.CTkScrollbar(
            root_frame,
            orientation="vertical",
            command=self.recipe_table.yview,
        )
        self.recipe_table.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.recipe_table.configure(yscrollcommand=self.scrollbar.set)

    def create_eChem_sequence_table(self, root_frame, columns=["", "", "", "", ""]):
        self.eChem_sequence_table = ttk.Treeview(
            root_frame, columns=columns, show="headings"
        )
        self.scrollbar_EC = ctk.CTkScrollbar(
            root_frame, orientation="vertical", command=self.eChem_sequence_table.yview
        )
        self.eChem_sequence_table.pack(side="left", fill="both", expand=True)
        self.scrollbar_EC.pack(side="right", fill="y")
        self.eChem_sequence_table.configure(yscrollcommand=self.scrollbar_EC.set)

    # the flash firmware page
    def create_firmware_update_page(self, root_frame):
        self.create_flash_serial_obj = serial.Serial()
        columnspan = 7

        local_row, local_column = 0, 0
        # first in the flash_firmware_frame
        self.port_label_ff = label(
            parent=root_frame,
            text="Port: ",
            row=local_row,
            column=local_column,
            columnspan=2,
            sticky="W",
        )
        local_column += 2
        self.port_combobox_ff = combobox(
            root_frame, local_row, local_column, state="readonly", width=240
        )
        local_column += 1
        self.connect_button_ff = button(
            root_frame,
            "Connect",
            local_row,
            local_column,
            lambda: self.connect_ff(
                self.create_flash_serial_obj, self.port_combobox_ff.get()
            ),
        )
        local_column += 1
        self.disconnect_button_ff = button(
            root_frame,
            "Disconnect",
            local_row,
            local_column,
            lambda: self.disconnect_ff(self.create_flash_serial_obj),
            state="disabled",
        )
        local_column += 1
        self.reset_button_ff = button(
            root_frame,
            "Reset",
            local_row,
            local_column,
            lambda: self.reset_ff(self.create_flash_serial_obj),
            state="disabled",
        )
        local_column += 1
        self.status_label_ff = label(
            root_frame, "Status: Not connected", local_row, local_column, sticky="W"
        )

        # second row in the flash_firmware_frame
        local_row += 1
        local_column = 0
        self.mode_label_ff = label(
            root_frame,
            "Current Mode: N/A",
            local_row,
            local_column,
            columnspan=3,
            sticky="W",
        )
        local_column += 3
        self.enter_bootloader_button_ff = button(
            root_frame,
            "Bootloader",
            local_row,
            local_column,
            lambda: self.switch_mode_ff(mode="bootloader"),
            state="disabled",
        )
        local_column += 1
        self.enter_controller_button_ff = button(
            root_frame,
            "Controller",
            local_row,
            local_column,
            lambda: self.switch_mode_ff(mode="controller"),
            state="disabled",
        )
        local_column += 1
        self.enter_bootsel_button_ff = button(
            root_frame,
            "Bootsel",
            local_row,
            local_column,
            lambda: self.switch_mode_ff(mode="bootsel"),
            state="disabled",
        )

        local_row += 1
        local_column = 0
        self.switch_controller_mode_label_ff = label(
            root_frame,
            "Controller Mode Switching:",
            local_row,
            local_column,
            columnspan=3,
            sticky="W",
        )
        local_column += 3
        self.switch_controller_mode_button_po_ff = button(
            root_frame,
            "Potentiostat",
            local_row,
            local_column,
            lambda: self.switch_controller_mode_ff(
                serial_port_obj=self.create_flash_serial_obj, mode="Potentiostat"
            ),
            state="disabled",
        )
        local_column += 1
        self.switch_controller_mode_button_pc_ff = button(
            root_frame,
            "Pump",
            local_row,
            local_column,
            lambda: self.switch_controller_mode_ff(
                serial_port_obj=self.create_flash_serial_obj, mode="Pump"
            ),
            state="disabled",
        )

        local_row += 1
        local_column = 0
        label(
            root_frame,
            "Enter bootsel mode first to flash uf2 file using Updater.",
            local_row,
            local_column,
            columnspan=3,
            sticky="W",
        )
        local_column += 3
        self.launch_fw_update_button = button(
            root_frame,
            "Launch Updater",
            local_row,
            local_column,
            self.open_fw_updater,  # method you’ll define below
        )

        local_row += 1
        local_column = 0
        label(
            root_frame,
            "Switch to Bootloader Mode to allow single file upload below.",
            local_row,
            local_column,
            columnspan=3,
            sticky="W",
        )
        local_row += 1
        local_column = 0
        self.space_label_ff = label(
            root_frame,
            "Available Space: N/A",
            local_row,
            local_column,
            columnspan=3,
            sticky="W",
        )
        local_column += 3
        self.send_file_button_ff = button(
            root_frame,
            "Upload File",
            local_row,
            local_column,
            self.upload_file_ff,
            state="disabled",
        )
        local_column += 1
        self.remove_file_button_ff = button(
            root_frame,
            "Remove File",
            local_row,
            local_column,
            self.remove_file_ff,
            state="disabled",
        )

        local_row += 1
        local_column = 0
        # next will be a table to show all the files on the disk
        self.file_table_frame_ff = ctk.CTkFrame(root_frame)
        self.file_table_frame_ff.grid(
            row=local_row,
            column=local_column,
            columnspan=columnspan,
            padx=global_pad_x,
            pady=global_pad_y,
            sticky="NSEW",
        )
        self.file_table_ff = ttk.Treeview(
            self.file_table_frame_ff,
            columns=["filename", "size"],
            show="headings",
        )
        self.scrollbar_ff = ctk.CTkScrollbar(
            self.file_table_frame_ff,
            orientation="vertical",
            command=self.file_table_ff.yview,
        )
        self.file_table_ff.pack(side="left", fill="both", expand=True)
        self.scrollbar_ff.pack(side="right", fill="y")
        self.file_table_ff.configure(yscrollcommand=self.scrollbar_ff.set)

    def open_fw_updater(self):
        # Create a new top-level window (so you don’t clobber your main root)
        top = tk.Toplevel(self.root)
        top.title("Firmware Updater")
        # Instantiate the existing PicoFlasherApp into that Toplevel
        updater = PicoFlasherApp(top)

        # Optional: when you close that window, it just destroys itself
        top.protocol("WM_DELETE_WINDOW", top.destroy)

    def main_loop(self):
        self.refresh_ports(instant=False)
        self.read_serial()
        self.read_serial_as()
        self.read_serial_po()
        self.send_command()
        self.send_command_as()
        self.send_command_po()
        self.update_progress()
        self.query_rtc_time()
        self.update_rtc_time_display()
        self.root.after(self.main_loop_interval_ms, self.main_loop)

    def refresh_ports(self, instant=True):
        if not instant:
            t_elapsed = time.time_ns() - self.port_refresh_last_ns
            if t_elapsed < self.port_refresh_interval_ns:
                return
        else:
            current_tab = self.Tabview.get()
            if current_tab != "Advanced Settings" and current_tab != "Connect":
                return

        self.port_refresh_last_ns = time.time_ns()
        # check if all serial objects in the self.pc dictionary are connected
        pump_ctls_all_connected = all(
            [
                serial_port_obj and serial_port_obj.is_open
                for serial_port_obj in self.pc.values()
            ]
        )
        if (
            not pump_ctls_all_connected
            or not self.autosampler.is_open
            or not self.potentiostat.is_open
            or not self.create_flash_serial_obj.is_open
        ):
            # get a list of connected ports name from the serial_port dictionary, filter by vendor id
            connected_ports = [
                port.name for port in self.pc.values() if port and port.is_open
            ]
            if self.autosampler.is_open:
                connected_ports.append(self.autosampler.name)
            if self.potentiostat.is_open:
                connected_ports.append(self.potentiostat.name)
            if self.create_flash_serial_obj.is_open:
                connected_ports.append(self.create_flash_serial_obj.name)

            ports = [
                port.device + " (SN:" + str(port.serial_number) + ")"
                for port in serial.tools.list_ports.comports()
                if port.vid == pico_vid and port.name.strip() not in connected_ports
            ]
            # create a dict of serial objects with serial object as key and the corresponding comboboxs as list
            serial_to_comboboxs = {}

            def set_combobox_values(comboboxs, port):
                if port is None:
                    port = ""
                for c in comboboxs:
                    c.configure(values=[port])
                    c.set(port)

            for id, widgets in self.pc_id_to_widget_map.items():
                serial_port_obj = self.pc.get(id)
                if serial_port_obj:
                    if serial_port_obj.is_open:
                        set_combobox_values(
                            widgets["comboboxs"],
                            str(serial_port_obj.port)
                            + " (Name:"
                            + self.pc_names[id]
                            + ")",
                        )
                    else:
                        serial_to_comboboxs[serial_port_obj] = widgets["comboboxs"]
            if self.autosampler.is_open:
                set_combobox_values(
                    self.autosampler_widget_map["comboboxs"],
                    str(self.autosampler.port)
                    + " (Name:"
                    + self.autosampler_name
                    + ")",
                )
            else:
                serial_to_comboboxs[self.autosampler] = self.autosampler_widget_map[
                    "comboboxs"
                ]
            if self.potentiostat.is_open:
                set_combobox_values(
                    self.potentiostat_widget_map["comboboxs"],
                    str(self.potentiostat.port)
                    + " (Name:"
                    + self.potentiostat_name
                    + ")",
                )
            else:
                serial_to_comboboxs[self.potentiostat] = self.potentiostat_widget_map[
                    "comboboxs"
                ]
            if self.create_flash_serial_obj.is_open:
                set_combobox_values(
                    [self.port_combobox_ff], self.create_flash_serial_obj.port
                )
            else:
                serial_to_comboboxs[self.create_flash_serial_obj] = [
                    self.port_combobox_ff
                ]

            for serial_port_obj, comboboxs in serial_to_comboboxs.items():
                for combobox in comboboxs:
                    # update the combobox with the list of ports
                    current_value = combobox.get()
                    combobox.configure(values=ports)
                    if current_value in ports:
                        combobox.set(current_value)
                    else:
                        if len(ports) > 0:
                            combobox.set(ports[0])
                        else:
                            combobox.set("")

    # connection to the selected port for firmware update
    def connect_ff(self, serial_port_obj, COM_port):
        # parse the COM port using regex expression "^(COM\d+)"
        parsed_port = re.match(r"^(COM\d+)", COM_port)
        if parsed_port:
            parsed_port = parsed_port.group(1)
            if serial_port_obj.is_open:

                def callback(choice):
                    if choice == "Yes":
                        self.disconnect_ff(serial_port_obj)
                        self.connect_ff(serial_port_obj, COM_port)

                non_blocking_custom_messagebox(
                    parent=self.root,
                    title="Already Connected",
                    message=f"Already connected to {serial_port_obj.port}. Disconnect?",
                    buttons=["Yes", "No"],
                    callback=callback,
                )
                return
            try:
                serial_port_obj.port = parsed_port
                serial_port_obj.timeout = self.timeout
                serial_port_obj.open()
                t = time.time_ns()
                while (
                    time.time_ns() - t < self.serial_wait_time * NANOSECONDS_PER_SECOND
                ):
                    pass
                serial_port_obj.reset_input_buffer()
                serial_port_obj.reset_output_buffer()
                # we have to distinguish between the firmware update mode and the controller mode
                serial_port_obj.write("0:ping\n".encode())  # identify Pico type
                response = serial_port_obj.readline().decode("utf-8").strip()
                logging.debug(f"Response from {parsed_port}: {response}")
                # if we have a response, we are in the controller mode
                if "CONTROL VERSION" in response.upper():
                    if "PICO" not in response.upper():
                        # which mean the firmware won't work
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message="The connected device is not running a Micropython firmware, easy firmware upload is not possible.",
                        )
                    pattern = r"Pico (\S+) Control Version"
                    match = re.search(pattern, response, re.IGNORECASE)
                    mode = "Unknown"
                    if match:
                        mode = match.group(1)
                    self.mode_label_ff.configure(
                        text=f"Current Mode: {mode} Controller"
                    )
                    self.enter_bootloader_button_ff.configure(
                        state="normal", hover=True
                    )
                    self.enter_controller_button_ff.configure(
                        state="disabled", hover=True
                    )
                    self.enter_bootsel_button_ff.configure(state="normal", hover=True)
                    self.switch_controller_mode_button_po_ff.configure(
                        state="normal", hover=True
                    )
                    self.switch_controller_mode_button_pc_ff.configure(
                        state="normal", hover=True
                    )
                elif "Error: Invalid JSON payload" in response:
                    self.mode_label_ff.configure(text="Current Mode: Firmware Update")
                    self.enter_bootloader_button_ff.configure(
                        state="disabled", hover=True
                    )
                    self.enter_controller_button_ff.configure(
                        state="normal", hover=True
                    )
                    self.enter_bootsel_button_ff.configure(state="disabled", hover=True)
                    self.send_file_button_ff.configure(state="normal", hover=True)
                    self.remove_file_button_ff.configure(state="normal", hover=True)
                    available_space, total_space = (
                        bootloader_helpers.request_disc_available_space(serial_port_obj)
                    )
                    available_space_mb = available_space / (1024 * 1024)
                    total_space_mb = total_space / (1024 * 1024)
                    self.space_label_ff.configure(
                        text=f"Available Space: {available_space_mb:.3f} / {total_space_mb:.3f} MB"
                    )

                    self.update_ff_file_stats(
                        bootloader_helpers.request_dir_list(serial_port_obj)
                    )

                # enable the buttons
                self.set_ff_buttons_state("normal", basic=True)
                logging.info(f"Connected to {parsed_port} for firmware update")
                self.status_label_ff.configure(text="Status: Connected")
                self.refresh_ports()  # refresh the ports immediately
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function connect: {e}",
                )

    def update_ff_file_stats(self, files_stats):
        for child in self.file_table_frame_ff.winfo_children():
            child.destroy()
        headings = ["filename", "size"]
        self.file_table_ff = ttk.Treeview(
            self.file_table_frame_ff,
            columns=headings,
            show="headings",
        )
        for heading in headings:
            self.file_table_ff.heading(heading, text=heading)
            self.file_table_ff.column(heading, anchor="center")
        self.scrollbar_ff = ctk.CTkScrollbar(
            self.file_table_frame_ff,
            orientation="vertical",
            command=self.file_table_ff.yview,
        )
        self.file_table_ff.configure(yscrollcommand=self.scrollbar_ff.set)
        self.file_table_ff.pack(side="left", fill="both", expand=True)
        self.scrollbar_ff.pack(side="right", fill="y")
        for filename, stats in files_stats.items():
            size = stats[-4]
            if size == 0:
                size = "DIR"
            else:
                if size < 1024:
                    size = f"{size} Bytes"
                elif size < 1024 * 1024:
                    size = f"{size / 1024:.3f} KB"
                else:
                    size = f"{size / (1024 * 1024):.3f} MB"
            self.file_table_ff.insert("", "end", values=(filename, size))

    def set_ff_buttons_state(self, state: str, basic=False):
        # set the state of all buttons in the flash firmware page
        self.disconnect_button_ff.configure(state=state)
        self.reset_button_ff.configure(state=state, hover=True)
        if not basic:
            self.enter_bootloader_button_ff.configure(state=state, hover=True)
            self.enter_controller_button_ff.configure(state=state, hover=True)
            self.enter_bootsel_button_ff.configure(state=state, hover=True)
            self.switch_controller_mode_button_po_ff.configure(state=state, hover=True)
            self.switch_controller_mode_button_pc_ff.configure(state=state, hover=True)
            self.send_file_button_ff.configure(state=state, hover=True)
            self.remove_file_button_ff.configure(state=state, hover=True)

    def disconnect_ff(self, serial_port_obj):
        if serial_port_obj.is_open:
            logging.info(f"Disconnected from {serial_port_obj.port}")
            serial_port_obj.close()
            if serial_port_obj == self.create_flash_serial_obj:
                self.status_label_ff.configure(text="Status: Not connected")
                self.mode_label_ff.configure(text="Current Mode: N/A")
                self.space_label_ff.configure(text="Available Space: N/A")
                self.set_ff_buttons_state("disabled")
                for child in self.file_table_frame_ff.winfo_children():
                    child.destroy()
                self.file_table_ff = ttk.Treeview(
                    self.file_table_frame_ff,
                    columns=["filename", "size"],
                    show="headings",
                )
                self.scrollbar_ff = ctk.CTkScrollbar(
                    self.file_table_frame_ff,
                    orientation="vertical",
                    command=self.file_table_ff.yview,
                )
                self.file_table_ff.configure(yscrollcommand=self.scrollbar_ff.set)
                self.file_table_ff.pack(side="left", fill="both", expand=True)
                self.scrollbar_ff.pack(side="right", fill="y")
            self.refresh_ports()

    def switch_mode_ff(self, mode: str):
        # set a "0:set_mode:update_firmware" command to the serial port
        if self.create_flash_serial_obj and not self.create_flash_serial_obj.is_open:
            return
        try:
            if mode == "bootloader":
                bootloader_helpers.enter_bootloader(self.create_flash_serial_obj)
            elif mode == "controller":
                bootloader_helpers.enter_controller(self.create_flash_serial_obj)
            elif mode == "bootsel":
                bootloader_helpers.enter_bootselect(self.create_flash_serial_obj)

            # update the frame
            self.status_label_ff.configure(text="Status: Not connected")
            self.mode_label_ff.configure(text="Current Mode: N/A")
            self.space_label_ff.configure(text="Available Space: N/A")
            self.disconnect_ff(self.create_flash_serial_obj)
            if mode == "bootloader" or mode == "controller":
                for _ in range(10):
                    self.refresh_ports()
                    for value in self.port_combobox_ff.cget("values"):
                        if self.create_flash_serial_obj.port in value:
                            t = time.time_ns()
                            while time.time_ns() - t < 3 * NANOSECONDS_PER_SECOND:
                                pass
                            self.connect_ff(
                                self.create_flash_serial_obj,
                                self.create_flash_serial_obj.port,
                            )
                            return
                    t = time.time_ns()
                    while time.time_ns() - t < 0.5 * NANOSECONDS_PER_SECOND:
                        pass
        except Exception as e:
            logging.error(f"Error: {e}")

    def upload_file_ff(self):
        try:
            # open a file dialog to select files to upload, allow multiple files being selected
            filenames = filedialog.askopenfilenames(
                parent=self.root,
                title="Select File to Upload",
                filetypes=[("All Files", "*.*")],
            )
            if not filenames or filenames == "" or len(filenames) == 0:
                return
            if not self.create_flash_serial_obj.is_open:
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message="Please connect to a port first.",
                )
                return
            result = False
            for filename in filenames:
                result = bootloader_helpers.upload_file(
                    serial_port=self.create_flash_serial_obj,
                    file_path=filename,
                    message_parent=self.root,
                )
            if result:
                self.update_ff_file_stats(
                    bootloader_helpers.request_dir_list(self.create_flash_serial_obj)
                )
        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred while uploading the file: {e}",
            )

    def remove_file_ff(self):
        try:
            # get the current selection in self.file_table_ff
            selected_items = self.file_table_ff.selection()
            logging.debug(f"Selected items: {selected_items}")
            if not selected_items or selected_items == "" or len(selected_items) == 0:
                return
            result = False
            for selected_item in selected_items:
                value = self.file_table_ff.item(selected_item, "values")
                filename = value[0] if value else None
                if filename:
                    result = bootloader_helpers.remove_file(
                        serial_port=self.create_flash_serial_obj,
                        filename=filename,
                        messagebox_parent=self.root,
                    )
            if result:
                self.update_ff_file_stats(
                    bootloader_helpers.request_dir_list(self.create_flash_serial_obj)
                )
        except Exception as e:
            logging.error(f"Error uploading file: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred while uploading the file: {e}",
            )

    def reset_ff(self, serial_port_obj: serial.Serial):
        try:
            if not serial_port_obj.is_open:
                return
            """Reset the board by sending a soft reset command over serial. ONLY WORKS with MicroPython."""
            pythonInject = [
                "import machine",
                "machine.reset()",
            ]
            # interrupt the currently running code
            serial_port_obj.write(b"\x03")  # Ctrl+C
            serial_port_obj.write(b"\x03")  # Ctrl+C
            serial_port_obj.write(b"\x01")  # switch to raw REPL mode & inject code
            for code in pythonInject:
                serial_port_obj.write(bytes(code + "\n", "utf-8"))
            serial_port_obj.write(b"\x04")  # exit raw REPL and run injected code
            self.disconnect_ff(serial_port_obj)
        except Exception as e:
            logging.error(f"Error resetting board: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred while resetting the board: {e}",
            )

    def switch_controller_mode_ff(self, serial_port_obj: serial.Serial, mode: str):
        # switch the controller mode by sending a command to the serial port
        if not serial_port_obj.is_open:
            return
        if mode == "Pump":
            command = "0:set_mode:pump\n"
        elif mode == "Autosampler":
            command = "0:set_mode:autosampler\n"
        elif mode == "Potentiostat":
            command = "0:set_mode:potentiostat\n"
        else:
            logging.error(f"Unknown controller type: {mode}")
            return
        try:
            serial_port_obj.write(command.encode())
            response = serial_port_obj.readline().decode("utf-8").strip()
            non_blocking_messagebox(
                parent=self.root,
                title="Controller Mode Switch",
                message=response,
            )
            self.reset_ff(serial_port_obj)
            for _ in range(15):
                self.refresh_ports()
                for value in self.port_combobox_ff.cget("values"):
                    if self.create_flash_serial_obj.port in value:
                        t = time.time_ns()
                        while time.time_ns() - t < 3 * NANOSECONDS_PER_SECOND:
                            pass
                        self.connect_ff(
                            self.create_flash_serial_obj,
                            self.create_flash_serial_obj.port,
                        )
                        return
                t = time.time_ns()
                while time.time_ns() - t < 0.5 * NANOSECONDS_PER_SECOND:
                    pass
            logging.info(f"Device -> PC: {response}")
        except Exception as e:
            logging.error(f"Error switching controller mode: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred while switching controller mode: {e}",
            )

    def connect_pc(self, controller_id):
        selected_port = self.pc_id_to_widget_map[controller_id]["comboboxs_sv"].get()
        parsed_port = re.match(r"^(COM\d+)", selected_port)
        if parsed_port:
            parsed_port = parsed_port.group(1)
            if self.pc[controller_id].is_open:

                def callback(choice):
                    if choice == "Yes":
                        self.disconnect_pc(
                            controller_id=controller_id, show_message=False
                        )
                        self.connect_pc(controller_id=controller_id)

                non_blocking_custom_messagebox(
                    parent=self.root,
                    title="Already Connected",
                    message=f"Already connected to {self.pc[controller_id].port}. Disconnect?",
                    buttons=["Yes", "No"],
                    callback=callback,
                )
                return

            try:  # Attempt to connect to the selected port
                serial_port_obj = self.pc[controller_id]
                serial_port_widget = self.pc_id_to_widget_map.get(controller_id, {})
                serial_port_obj.port = parsed_port
                serial_port_obj.timeout = self.timeout
                serial_port_obj.open()
                t = time.time_ns()
                while (
                    time.time_ns() - t < self.serial_wait_time * NANOSECONDS_PER_SECOND
                ):
                    pass
                serial_port_obj.reset_input_buffer()
                serial_port_obj.reset_output_buffer()
                serial_port_obj.write("0:ping\n".encode())  # identify Pico type
                response = serial_port_obj.readline().decode("utf-8").strip()
                if "Pico Pump Control Version" not in response:
                    self.disconnect_pc(controller_id=controller_id, show_message=False)
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
                self.refresh_ports()  # refresh the ports immediately
                serial_port_widget["status_label_sv"].set("Status: Connected")
                self.pc_connected[controller_id] = True

                self.query_pump_info(controller_id=controller_id)  # query the pump info
                self.query_controller_name(
                    controller_id=controller_id
                )  # query the pump name
                # enable the buttons
                for b in serial_port_widget["disconnect_buttons"]:
                    b.configure(state="normal", hover=True)
                for b in serial_port_widget["reset_buttons"]:
                    b.configure(state="normal", hover=True)
                for b in serial_port_widget["set_name_buttons"]:
                    b.configure(state="normal", hover=True)
                self.set_mc_buttons_state("normal")
            except Exception as e:
                serial_port_widget = self.pc_id_to_widget_map.get(controller_id, None)
                if serial_port_widget:
                    serial_port_widget["status_label_sv"].set("Status: Not connected")
                self.pc_connected[controller_id] = False
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function connect: {e}",
                )

    def set_mc_buttons_state(self, state) -> None:
        self.add_pump_button.configure(state=state)
        self.clear_pumps_button.configure(state=state)
        self.save_pumps_button.configure(state=state)
        self.emergency_shutdown_button.configure(state=state)

    def connect_as(self):
        selected_port = self.autosampler_widget_map["comboboxs_sv"].get()
        parsed_port = re.match(r"^(COM\d+)", selected_port)
        if parsed_port:
            parsed_port = parsed_port.group(1)
            if self.autosampler.is_open:

                def callback(choice):
                    if choice == "Yes":
                        self.disconnect_as(show_message=False)
                        self.connect_as()

                non_blocking_custom_messagebox(
                    parent=self.root,
                    title="Already Connected",
                    message=f"Already connected to {self.autosampler.port}. Disconnect?",
                    buttons=["Yes", "No"],
                    callback=callback,
                )
                return
            try:
                self.autosampler.port = parsed_port
                self.autosampler.open()
                t = time.time_ns()
                while (
                    time.time_ns() - t < self.serial_wait_time * NANOSECONDS_PER_SECOND
                ):
                    pass
                self.autosampler.reset_input_buffer()
                self.autosampler.reset_output_buffer()
                self.autosampler.write("ping\n".encode())  # identify Pico type
                response = self.autosampler.readline().decode("utf-8").strip()
                if "Autosampler Control Version" not in response:
                    self.disconnect_as(show_message=False)
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Connected to the wrong device for autosampler.",
                    )
                    return
                now = datetime.now()  # synchronize the RTC with the PC time
                sync_command = f"stime:{now.year}:{now.month}:{now.day}:{now.isoweekday() - 1}:{now.hour}:{now.minute}:{now.second}"
                self.autosampler.write(f"{sync_command}\n".encode())
                response = self.autosampler.readline().decode("utf-8").strip()

                self.autosampler_widget_map["status_label_sv"].set("Status: Connected")
                logging.info(f"Connected to Autosampler at {selected_port}")
                self.refresh_ports()
                self.set_as_buttons_state("normal")
                self.autosampler_send_queue.put("dumpSlotsConfig")
            except Exception as e:
                self.autosampler_widget_map["status_label_sv"].set(
                    "Status: Not connected"
                )
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function connect_as: {e}",
                )

    def set_as_buttons_state(self, state) -> None:
        for b in self.autosampler_widget_map["disconnect_buttons"]:
            b.configure(state=state)
        for b in self.autosampler_widget_map["reset_buttons"]:
            b.configure(state=state)

        self.position_entry_as.configure(state=state)
        self.goto_position_button_as.configure(state=state)
        self.stop_movement_button_as.configure(state=state)
        self.set_position_button_as.configure(state=state)

        self.slot_combobox_as.configure(state=state)
        self.goto_slot_button_as.configure(state=state)
        self.delete_slot_button_as.configure(state=state)

        self.update_slot_slotname_as.configure(state=state)
        self.update_slot_position_as.configure(state=state)
        self.update_slot_button_as.configure(state=state)

    def connect_po(self):
        selected_port = self.potentiostat_widget_map["comboboxs_sv"].get()
        parsed_port = re.match(r"^(COM\d+)", selected_port)
        if parsed_port:
            parsed_port = parsed_port.group(1)
            if self.potentiostat.is_open:

                def callback(choice):
                    if choice == "Yes":
                        self.disconnect_po(show_message=False)
                        self.connect_po()

                non_blocking_custom_messagebox(
                    parent=self.root,
                    title="Already Connected",
                    message=f"Already connected to {self.potentiostat.port}. Disconnect?",
                    buttons=["Yes", "No"],
                    callback=callback,
                )
                return
            try:
                self.potentiostat.port = parsed_port
                self.potentiostat.open()
                t = time.time_ns()
                while (
                    time.time_ns() - t < self.serial_wait_time * NANOSECONDS_PER_SECOND
                ):
                    pass
                self.potentiostat.reset_input_buffer()
                self.potentiostat.reset_output_buffer()
                self.potentiostat.write("0:ping\n".encode())  # identify Pico type
                response = self.potentiostat.readline().decode("utf-8").strip()
                if "Potentiostats Control Version" not in response:
                    self.disconnect_po(show_message=False)
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Connected to the wrong device for potentiostat.",
                    )
                    return
                now = datetime.now()  # synchronize the RTC with the PC time
                sync_command = f"0:stime:{now.year}:{now.month}:{now.day}:{now.hour}:{now.minute}:{now.second}"
                self.potentiostat.write(f"{sync_command}\n".encode())
                response = self.potentiostat.readline().decode("utf-8").strip()

                self.potentiostat_widget_map["status_label_sv"].set("Status: Connected")
                logging.info(f"Connected to Potentiostat at {selected_port}")
                self.refresh_ports()
                self.set_trigger_po(state="low")
                self.set_potentiostat_buttons_state("normal")
                self.potentiostat_send_queue.put("0:info")
                self.potentiostat_send_queue.put("0:st")
            except Exception as e:
                self.potentiostat_widget_map["status_label_sv"].set(
                    "Status: Not connected"
                )
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function connect_po: {e}",
                )

    def set_potentiostat_buttons_state(self, state) -> None:
        for b in self.potentiostat_widget_map["disconnect_buttons"]:
            b.configure(state=state)
        for b in self.potentiostat_widget_map["reset_buttons"]:
            b.configure(state=state)
        self.trigger_high_button_po.configure(state=state)
        self.trigger_low_button_po.configure(state=state)

    def query_rtc_time(self) -> None:
        """Send a request to the Pico to get the current RTC time every second."""
        current_time = time.monotonic_ns()
        if current_time - self.last_querytime >= NANOSECONDS_PER_SECOND:
            # send the command to each controller
            for id, connection_status in self.pc_connected.items():
                if connection_status:
                    self.pc_send_queue.put(f"{id}:0:time")
            if self.autosampler.is_open:
                self.autosampler_send_queue.put("gtime")
                self.autosampler_send_queue.put("getPosition")
            if self.potentiostat.is_open:
                self.potentiostat_send_queue.put("0:time")
            self.last_querytime = current_time

    def parse_rtc_time(
        self, controller_id, response, is_Autosampler=False, is_Potentiostat=False
    ) -> None:
        try:
            match = re.search(
                r"RTC Time: (\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)", response
            )
            if match:
                _, _, _, hour, minute, second = match.groups()
                time_str = f"{int(hour):02}:{int(minute):02}:{int(second):02}"
                if is_Autosampler:
                    self.autosampler_rtc_time = time_str
                elif is_Potentiostat:
                    self.potentiostat_rtc_time = time_str
                else:
                    self.pc_rtc_time[controller_id] = f"{controller_id}:{time_str}"
        except Exception as e:
            logging.error(f"Error updating RTC time display: {e}")

    def query_controller_name(
        self, controller_id=None, is_Autosampler=False, is_Potentiostat=False
    ):
        if is_Autosampler:
            if self.autosampler.is_open:
                self.autosampler_send_queue.put("get_name")
        elif is_Potentiostat:
            if self.potentiostat.is_open:
                self.potentiostat_send_queue.put("0:get_name")
        else:
            serial_obj = self.pc.get(controller_id, None)
            if serial_obj and serial_obj.is_open:
                self.pc_send_queue.put(f"{controller_id}:0:get_name")

    def parse_controller_name(
        self, controller_id, response, is_Autosampler=False, is_Potentiostat=False
    ) -> None:
        try:
            match = re.search(r"Name:\W+(.*)$", response)
            if match:
                name = match.group(1)
                if is_Autosampler:
                    self.autosampler_name = name
                elif is_Potentiostat:
                    self.autosampler_name = name
                else:
                    self.pc_names[controller_id] = name
            self.refresh_ports(instant=True)
        except Exception as e:
            logging.error(f"Error updating controller name: {e}")

    def set_controller_name(
        self, name=None, controller_id=None, is_Autosampler=False, is_Potentiostat=False
    ):
        if name is None:
            fields = [
                {
                    "label": "Pump Name",
                    "type": "text",
                    "initial_value": "",
                    "placeholder_text": "Enter pump name",
                }
            ]
            result_var = ctk.StringVar(value="")

            def on_result(*args):
                result = result_var.get()
                if not result:
                    result_var.trace_remove("write", trace_id)  # Untrace on cancel
                    return
                try:
                    inputs = json.loads(result)
                    self.set_controller_name(
                        name=inputs["Pump Name"],
                        controller_id=controller_id,
                        is_Autosampler=is_Autosampler,
                        is_Potentiostat=is_Potentiostat,
                    )
                except Exception as e:
                    logging.error(f"Error updating controller name: {e}")
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message=f"An error occurred while updating the pump: {e}",
                    )
                result_var.trace_remove("write", trace_id)  # Untrace after completion

            trace_id = result_var.trace_add("write", on_result)  # Trace the variable
            non_blocking_input_dialog(
                parent=self.root,
                title="Set Controller Name",
                fields=fields,
                result_var=result_var,
            )
            return
        if is_Autosampler:
            if self.autosampler.is_open:
                self.autosampler_send_queue.put(f"set_name:{name}")
                self.autosampler_send_queue.put("get_name")
        elif is_Potentiostat:
            if self.potentiostat.is_open:
                self.potentiostat_send_queue.put(f"0:set_name:{name}")
                self.potentiostat_send_queue.put("0:get_name")
        else:
            serial_obj = self.pc.get(controller_id, None)
            if serial_obj and serial_obj.is_open:
                self.pc_send_queue.put(f"{controller_id}:0:set_name:{name}")
                self.pc_send_queue.put(f"{controller_id}:0:get_name")

    def parse_autosampler_config(self, response) -> None:
        # Extract the JSON part of the response
        config_str = response.replace("INFO: Slots configuration: ", "").strip()
        try:
            previous_value = self.slot_combobox_as.get()
            self.autosampler_slots.clear()
            self.autosampler_slots.update(json.loads(config_str))
            slots = list(self.autosampler_slots.keys())
            slots.sort(
                key=lambda x: (
                    not x.isdigit(),
                    int(x) if x.isdigit() else x,
                )
            )
            self.slot_combobox_as.configure(values=slots)

            if previous_value in slots:
                self.slot_combobox_as.set(previous_value)
            else:
                if len(slots) > 0:
                    self.slot_combobox_as.set(slots[0])
            self.on_slot_combobox_selected()  # update the slot details
            logging.info(f"Slots populated: {slots}")
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding autosampler configuration: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message="Failed to parse autosampler configuration with error: {e}",
            )

    def parse_potentiostat_config(self, response) -> None:
        config_pattern = re.compile(
            r"Potentiostat(\d+) Info: Trigger Pin: (0|1), Initial Trigger Pin Value: (0|1), Current Trigger Status: (LOW|HIGH)"
        )
        matches = config_pattern.findall(response)

        for match in matches:
            potentiostat_id, trigger_pin, initial_trigger_pin_value, trigger_status = (
                match
            )
            potentiostat_id = int(potentiostat_id)
            if potentiostat_id not in self.potentiostat_config:
                self.potentiostat_config[potentiostat_id] = {}
            potentiostat_config = self.potentiostat_config[potentiostat_id]
            potentiostat_config["trigger_pin"] = trigger_pin
            potentiostat_config["initial_trigger_pin_value"] = initial_trigger_pin_value
            potentiostat_config["trigger_status"] = trigger_status
            logging.debug(f"potentiostat_config {self.potentiostat_config}")

    def parse_potentiostat_status(self, response) -> None:
        # format INFO: Potentiostat <id> Status: <status>
        matches = re.findall(r"Potentiostat(\d+) Status: Trigger: (LOW|HIGH)", response)
        # asseble a string and update to self.potentiostat_status_label
        if matches:
            status_str = ""
            for match in matches:
                potentiostat_id, trigger_status = match
                status_str += f"{potentiostat_id}: {trigger_status}, "
            status_str = status_str[:-2]
            self.current_trigger_state_value_po.configure(text=status_str)

    def parse_autosampler_position(self, response) -> None:
        # format INFO: Current position: <position>
        match = re.search(r"position: (\d+)", response)
        if match:
            current_position = match.group(1)
            self.current_position_value_as.configure(text=f"{current_position}")
        else:
            logging.error(
                f"Failed to parse autosampler position from response: {response}"
            )

    def update_rtc_time_display(self) -> None:
        try:
            # sort the keys of the dictionary by the pump id, join the values and update the label
            rtc_time_str = " | ".join(
                [
                    self.pc_rtc_time[key]
                    for key in sorted(self.pc_rtc_time.keys())
                    if key and self.pc_connected[key]
                ]
            )
            self.current_time_value.configure(text=rtc_time_str)
            self.current_time_value_as.configure(text=self.autosampler_rtc_time)
            self.current_time_value_po.configure(text=self.potentiostat_rtc_time)
        except Exception as e:
            logging.error(f"Error updating RTC time display: {e}")

    def disconnect_pc(self, controller_id, show_message=True):
        if self.pc.get(controller_id, None):
            serial_port_obj = self.pc[controller_id]
            serial_port_widget = self.pc_id_to_widget_map[controller_id]
            if serial_port_obj.is_open:
                try:
                    serial_port_obj.close()  # close the serial port connection
                    self.pc_connected[controller_id] = False

                    # update UI
                    serial_port_widget["status_label_sv"].set(
                        "Status: Not connected"
                    )  # update the status label
                    for b in serial_port_widget["disconnect_buttons"]:
                        b.configure(state="disabled", hover=True)
                    for b in serial_port_widget["reset_buttons"]:
                        b.configure(state="disabled", hover=True)
                    for b in serial_port_widget["set_name_buttons"]:
                        b.configure(state="disabled", hover=True)
                    self.remove_pumps_widgets(
                        remove_all=False, controller_id=controller_id
                    )
                    # only disable the manual control buttons if all controllers are disconnected
                    if all([not port.is_open for port in self.pc.values()]):
                        self.set_mc_buttons_state("disabled")
                        self.clear_recipe()  # clear the recipe table
                        self.stop_procedure(False)  # also stop any running procedure

                    # go into the queue and remove any command that is meant for the disconnected controller
                    temp_queue = Queue()
                    while not self.pc_send_queue.empty():
                        command = self.pc_send_queue.get()
                        if int(command.split(":")[0]) != controller_id:
                            temp_queue.put(command)
                    while not temp_queue.empty():
                        self.pc_send_queue.put(temp_queue.get())

                    self.pc_names[controller_id] = "N/A"  # reset the name

                    self.refresh_ports()
                    logging.info(f"Disconnected from Pico {controller_id}")
                    if show_message:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Connection Status",
                            message=f"Disconnected from pump controller {controller_id}",
                        )
                except Exception as e:
                    logging.error(f"Error: {e}")
                    self.pc_connected[controller_id] = False
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message=f"An error occurred in function disconnect: {e}",
                    )

    def disconnect_as(self, show_message=True):
        if self.autosampler.is_open:
            try:
                self.autosampler.close()
                self.autosampler_widget_map["status_label_sv"].set(
                    "Status: Not connected"
                )
                self.current_position_value_as.configure(text="N/A")
                self.autosampler_rtc_time = "--:--:--"
                self.slot_combobox_as.set("")
                self.set_as_buttons_state("disabled")
                while not self.autosampler_send_queue.empty():  # empty the queue
                    self.autosampler_send_queue.get()
                logging.info("Disconnected from Autosampler")
                if show_message:
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Connection Status",
                        message="Disconnected from Autosampler",
                    )
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred: {e}",
                )

    def disconnect_po(self, show_message=True):
        if self.potentiostat.is_open:
            try:
                self.potentiostat.close()
                self.potentiostat_widget_map["status_label_sv"].set(
                    "Status: Not connected"
                )
                self.potentiostat_rtc_time = "--:--:--"
                self.current_trigger_state_value_po.configure(text="N/A")
                self.set_potentiostat_buttons_state("disabled")
                while not self.potentiostat_send_queue.empty():  # empty the queue
                    self.potentiostat_send_queue.get()
                logging.info("Disconnected from Potentiostat")
                if show_message:
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Connection Status",
                        message="Disconnected from Potentiostat",
                    )
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred: {e}",
                )

    def reset_pc(self, controller_id, confirmation=False):
        try:
            if self.pc[controller_id].is_open:
                if not confirmation:

                    def callback(choice):
                        if choice == "Yes":
                            self.reset_pc(
                                controller_id=controller_id, confirmation=True
                            )

                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Reset",
                        message=f"Are you sure you want to reset the controller {controller_id}?",
                        buttons=["Yes", "No"],
                        callback=callback,
                    )
                    return
                else:
                    self.pc_send_queue.put(f"{controller_id}:0:reset")
                    self.disconnect_pc(controller_id=controller_id, show_message=False)
                    logging.info(f"Signal sent for controller {controller_id} reset.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function reset: {e}",
            )

    def reset_as(self, confirmation=False):
        try:
            if self.autosampler.is_open:
                if not confirmation:

                    def callback(choice):
                        if choice == "Yes":
                            self.reset_as(confirmation=True)

                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Reset",
                        message="Are you sure you want to reset the Autosampler?",
                        buttons=["Yes", "No"],
                        callback=callback,
                    )
                    return
                else:
                    self.autosampler_send_queue.put("reset")
                    self.disconnect_as(show_message=False)
                    logging.info("Signal sent for Autosampler reset.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function reset_as: {e}",
            )

    def reset_po(self, confirmation=False):
        try:
            if self.potentiostat.is_open:
                if not confirmation:

                    def callback(choice):
                        if choice == "Yes":
                            self.reset_po(confirmation=True)

                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Reset",
                        message="Are you sure you want to reset the Potentiostat?",
                        buttons=["Yes", "No"],
                        callback=callback,
                    )
                    return
                else:
                    self.potentiostat_send_queue.put("0:reset")
                    self.disconnect_po(show_message=False)
                    logging.info("Signal sent for Autosampler reset.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function reset_po: {e}",
            )

    def toggle_trigger_po(self):
        self.potentiostat_send_queue.put("0:tr")

    def set_trigger_po(self, state: str, update_status=True):
        self.potentiostat_send_queue.put(f"0:set_trigger:{state.upper()}")
        if update_status:
            self.potentiostat_send_queue.put("0:st")

    def query_pump_info(self, controller_id):
        serial_obj = self.pc.get(controller_id, None)
        if serial_obj and serial_obj.is_open:
            self.pc_send_queue.put(f"{controller_id}:0:info")

    def update_status(self, controller_id):
        serial_obj = self.pc.get(controller_id, None)
        if serial_obj and serial_obj.is_open:
            self.pc_send_queue.put(f"{controller_id}:0:status")

    def toggle_power(self, pump_id, update_status=True):
        controller_id = self.pump_ids_to_controller_ids.get(pump_id, None)
        if controller_id:
            if self.pc[controller_id].is_open:
                self.pc_send_queue.put(f"{controller_id}:{pump_id}:toggle_power")
                if update_status:
                    self.update_status(controller_id=controller_id)
        else:
            logging.error(
                f"Trying to toggle power for pump {pump_id} without a controller."
            )

    def toggle_direction(self, pump_id, update_status=True):
        controller_id = self.pump_ids_to_controller_ids.get(pump_id, None)
        if controller_id:
            if self.pc[controller_id].is_open:
                self.pc_send_queue.put(f"{controller_id}:{pump_id}:toggle_direction")
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
            serial_obj = self.pc.get(controller_id, None)
            if serial_obj and serial_obj.is_open:
                command = f"{pump_id}:reg:{power_pin}:{direction_pin}:{initial_power_pin_value}:{initial_direction_pin_value}:{initial_power_status}:{initial_direction_status}"
                self.pc_send_queue.put(f"{controller_id}:{command}")
                self.update_status(controller_id=controller_id)
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function register_pump: {e}",
            )

    def remove_pump(self, remove_all=False, pump_id=None, confirmation=False):
        try:

            def callback(choice):
                if choice == "Yes":
                    self.remove_pump(
                        remove_all=remove_all, pump_id=pump_id, confirmation=True
                    )

            if remove_all:
                if not confirmation:
                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Clear Pumps",
                        message="Are you sure you want to clear all pumps?",
                        buttons=["Yes", "No"],
                        callback=callback,
                    )
                    return
                else:
                    # query the pump info for all the controllers
                    for (
                        id,
                        connection_status,
                    ) in self.pc_connected.items():
                        if connection_status:
                            self.remove_pumps_widgets(
                                remove_all=False, controller_id=id
                            )
                            self.pc_send_queue.put(f"{id}:0:clear_pumps")
                            self.query_pump_info(controller_id=id)
            else:
                if not confirmation:
                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Clear Pump",
                        message=f"Are you sure you want to clear pump {pump_id}?",
                        buttons=["Yes", "No"],
                        callback=callback,
                    )
                    return
                else:
                    if pump_id is None:
                        logging.error("Pump ID is None")
                        return
                    # find the controller id of the pump
                    controller_id = self.pump_ids_to_controller_ids.get(pump_id, None)
                    if controller_id:
                        self.remove_pumps_widgets(remove_all=False, pump_id=pump_id)
                        self.pc_send_queue.put(f"{controller_id}:{pump_id}:clear_pumps")
                        self.query_pump_info(controller_id=controller_id)
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function remove_pump: {e}",
            )

    def save_pump_config(self):
        if any(self.pc_connected.values()):
            try:
                # pop a checklist message box to let user choose which pump to save
                pump_id_list = [
                    f"Controller {id}"
                    for id, connected in self.pc_connected.items()
                    if connected
                ]
                if len(pump_id_list) > 1:
                    pump_id_list.insert(0, "All")
                result_var = tk.StringVar()
                result_var.set("")  # Initialize as empty
                non_blocking_checklist(
                    parent=self.root,
                    title="Select Controller to Save",
                    message="Select the controllers to save the configuration:",
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
                        for id, connected in self.pc_connected.items():
                            if connected:
                                self.pc_send_queue.put(f"{id}:0:save_pumps")
                                logging.info(
                                    f"Signal sent to save pump {id} configuration."
                                )
                    else:
                        for pump in selected_pumps:
                            pump_id = int(pump.split(" ")[1])
                            self.pc_send_queue.put(f"{pump_id}:0:save_pumps")
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

    def pumps_shutdown(
        self,
        all=True,
        controller_id=None,
        messageboxConfirmationNeeded=False,
        Confirmation=False,
    ):
        if any(self.pc_connected.values()):
            try:
                if messageboxConfirmationNeeded:

                    def callback(choice):
                        if choice == "Yes":
                            self.pumps_shutdown(
                                all=all,
                                controller_id=controller_id,
                                messageboxConfirmationNeeded=True,
                                Confirmation=True,
                            )

                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Shutdown All",
                        message="Are you sure you want to shutdown all pumps?",
                        buttons=["Yes", "No"],
                        callback=callback,
                    )
                    return
                if Confirmation or not messageboxConfirmationNeeded:
                    if all:
                        for (
                            id,
                            connection_status,
                        ) in self.pc_connected.items():
                            if connection_status:
                                self.pc_send_queue.put(f"{id}:0:shutdown")
                                self.update_status(controller_id=id)
                                logging.info(
                                    f"Signal sent for emergency shutdown of pump controller {id}."
                                )
                    else:
                        if controller_id and self.pc_connected[controller_id]:
                            self.pc_send_queue.put(f"{controller_id}:0:shutdown")
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
            self.pumps_shutdown(messageboxConfirmationNeeded=False)
            # update the status
            for id, connection_status in self.pc_connected.items():
                if connection_status:
                    self.update_status(controller_id=id)
                    for b in self.pc_id_to_widget_map[id]["disconnect_buttons"]:
                        b.configure(state="normal", hover=True)
            if self.autosampler.is_open:
                for b in self.autosampler_widget_map["disconnect_buttons"]:
                    b.configure(state="normal", hover=True)
            if self.potentiostat.is_open:
                for b in self.potentiostat_widget_map["disconnect_buttons"]:
                    b.configure(state="normal", hover=True)
            # disable the buttons
            self.stop_button.configure(state="disabled", hover=True)
            self.pause_button.configure(state="disabled", hover=True)
            self.continue_button.configure(state="disabled", hover=True)
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
            self.pause_button.configure(state="disabled", hover=True)
            self.continue_button.configure(state="normal", hover=True)
            self.end_time_value.configure(text="paused")
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
            self.pause_button.configure(state="normal", hover=True)
            self.continue_button.configure(state="disabled", hover=True)
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
        if not self.pc_send_queue.empty():
            controller_id = -1
            try:
                command = self.pc_send_queue.get(block=False)
                controller_id = int(command.split(":")[0])
                # assemble the command (everything after the first colon, the rest might also contain colons)
                command = command.split(":", 1)[1]
                if self.pc[
                    controller_id
                ].is_open:  # check if the controller is connected
                    self.pc[controller_id].write(f"{command}\n".encode())
                    if "time" not in command:
                        logging.debug(f"PC -> Pico {controller_id}: {command}")
                else:
                    logging.error(
                        f"Error: Trying to send command to disconnected controller {controller_id}"
                    )
            except serial.SerialException as e:
                self.disconnect_pc(controller_id, False)
                logging.error(f"Error: controller {controller_id} {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"Failed to send command to pump controller {controller_id} with error: {e}",
                )
            except Exception as e:
                self.disconnect_pc(controller_id, False)
                logging.error(f"Error: controller {controller_id} {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function send_command: {e}",
                )

    def send_command_as(self):
        try:
            if self.autosampler.is_open and not self.autosampler_send_queue.empty():
                command = self.autosampler_send_queue.get(block=False)
                self.autosampler.write(f"{command}\n".encode())
                if "gtime" not in command and "getPosition" not in command:
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

    def send_command_po(self):
        try:
            if self.potentiostat.is_open and not self.potentiostat_send_queue.empty():
                command = self.potentiostat_send_queue.get(block=False)
                self.potentiostat.write(f"{command}\n".encode())
                if "time" not in command:
                    logging.debug(f"PC -> Potentiostat: {command}")
        except serial.SerialException as e:
            self.disconnect_po(False)
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Failed to send command to Potentiostat with error: {e}",
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function send_command_po: {e}",
            )

    def read_serial(self):
        try:
            for controller_id, serial_port_obj in self.pc.items():
                if (
                    serial_port_obj
                    and serial_port_obj.is_open
                    and serial_port_obj.in_waiting
                ):
                    response = serial_port_obj.readline().decode("utf-8").strip()
                    if "RTC Time:" not in response:
                        logging.debug(f"Pico {controller_id} -> PC: {response}")
                    if "Info:" in response:
                        self.add_pump_widgets(controller_id, response)
                    elif "Name:" in response:
                        self.parse_controller_name(controller_id, response)
                    elif "Status:" in response:
                        self.update_pump_status(controller_id, response)
                    elif "RTC Time" in response:
                        self.parse_rtc_time(controller_id, response)
                    elif "Success:" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Success",
                            message=f"Pump Controller {controller_id}: {response}",
                        )
                    elif "Error:" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message=f"Pump Controller {controller_id}: {response}",
                        )
        except serial.SerialException as e:
            self.disconnect_pc(controller_id, False)  # type: ignore
            logging.error(f"Error: controller {controller_id} {e}")  # type: ignore
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Failed to read from pump controller {controller_id} with error: {e}",  # type: ignore
            )
        except Exception as e:
            self.disconnect_pc(controller_id, False)  # type: ignore
            logging.error(f"Error: controller {controller_id} {e}")  # type: ignore
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
                    self.pumps[pump_id]["power_label"].configure(
                        text=f"Power Status: {power_status}"
                    )
                    self.pumps[pump_id]["direction_label"].configure(
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
                for id, connection_status in self.pc_connected.items():
                    if connection_status:
                        self.query_pump_info(controller_id=id)
                logging.error(
                    f"We received a status update for a pump {pump_id} that does not exist from controller {controller_id}. Re-querying all pump info."
                )

    def read_serial_as(self):
        if self.autosampler.is_open:
            try:
                if self.autosampler.in_waiting:
                    response = self.autosampler.readline().decode("utf-8").strip()

                    if (
                        "RTC Time" not in response
                        and "Current position" not in response
                    ):
                        logging.debug(f"Autosampler -> PC: {response}")

                    if "INFO: Slots configuration: " in response:
                        self.parse_autosampler_config(response)
                    elif "INFO: Current position: " in response:
                        self.parse_autosampler_position(response)
                    elif "RTC Time" in response:
                        self.parse_rtc_time(
                            controller_id=None, response=response, is_Autosampler=True
                        )
                    elif "ERROR" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message=f"Autosampler: {response}",
                        )
                    elif "SUCCESS" in response:
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

    def read_serial_po(self):
        if self.potentiostat.is_open:
            try:
                if self.potentiostat.in_waiting:
                    response = self.potentiostat.readline().decode("utf-8").strip()
                    if "RTC Time" not in response:
                        logging.debug(f"Potentiostat -> PC: {response}")

                    if "Info:" in response:
                        self.parse_potentiostat_config(response)
                    if "Status:" in response:
                        self.parse_potentiostat_status(response)
                    elif "RTC Time" in response:
                        self.parse_rtc_time(
                            controller_id=None,
                            response=response,
                            is_Potentiostat=True,
                        )
                    elif "ERROR" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message=f"Potentiostat: {response}",
                        )
                    elif "SUCCESS" in response:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Success",
                            message=f"Potentiostat: {response}",
                        )
            except serial.SerialException as e:
                self.disconnect_po(False)
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"Failed to read from Potentiostat with error: {e}",
                )
            except Exception as e:
                self.disconnect_po(False)
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function read_serial_po: {e}",
                )

    def goto_position_as(self, position=None):
        if self.autosampler.is_open:
            try:
                if position is None:
                    position = self.position_entry_as.get().strip()
                if position and position.isdigit():
                    command = f"moveTo:{position}"
                    self.autosampler_send_queue.put(command)
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
        if self.autosampler.is_open:
            try:
                if slot is None:
                    slot = self.slot_combobox_as.get().strip()
                if slot:
                    command = f"moveToSlot:{slot}"
                    self.autosampler_send_queue.put(command)
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function goto_slot_as: {e}",
                )

    def stop_movement_as(self):
        if self.autosampler.is_open:
            try:
                self.autosampler_send_queue.put("stop")
                logging.info("Stopping Autosampler movement")
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function stop_movement_as: {e}",
                )

    def set_position_as(self, position=None):
        if self.autosampler.is_open:
            try:
                if position is None:
                    position = self.position_entry_as.get().strip()
                if position and position.isdigit():
                    command = f"setPosition:{position}"
                    self.autosampler_send_queue.put(command)
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
                    message=f"An error occurred in function set_position_as: {e}",
                )

    def delete_slot_as(self, slot=None):
        if self.autosampler.is_open:
            try:
                if slot is None:
                    slot = self.slot_combobox_as.get().strip()
                if slot:
                    command = f"deleteSlot:{slot}"
                    self.autosampler_send_queue.put(command)
                    self.autosampler_send_queue.put("dumpSlotsConfig")
                    logging.info(f"Autosampler command sent: {command}")
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function delete_slot_as: {e}",
                )

    def update_slot_as(self, slot=None, position=None):
        if self.autosampler.is_open:
            try:
                # either provide both slot and position or use the current values from the UI
                if slot is None:
                    slot = self.update_slot_slotname_as.get().strip()
                if not slot or slot == "":
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="empty slot name is not allowed.",
                    )
                    return
                if position is None:
                    position = self.update_slot_position_as.get().strip()
                if not position or not position.isdigit():
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error",
                        message="Invalid position, please enter a valid integer value.",
                    )
                    return
                command = f"setSlotPosition:{slot}:{int(position)}"
                self.autosampler_send_queue.put(command)
                self.autosampler_send_queue.put("dumpSlotsConfig")
                logging.info(f"Updating Autosampler slot {slot} to position {position}")
            except Exception as e:
                logging.error(f"Error: {e}")
                non_blocking_messagebox(
                    parent=self.root,
                    title="Error",
                    message=f"An error occurred in function update_slot_as: {e}",
                )

    def on_slot_combobox_selected(self, event=None):
        selected_slot = self.slot_combobox_as.get()
        if selected_slot in self.autosampler_slots:
            self.slot_position_value_as.configure(
                text=f"{self.autosampler_slots[selected_slot]}"
            )
        else:
            self.slot_position_value_as.configure(text="N/A")

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
                    pump_frame = ttk.LabelFrame(
                        self.pumps_frame,
                        labelanchor="n",
                        labelwidget=ctk.CTkLabel(
                            self.pumps_frame,
                            text=f"Pump {pump_id}, Power pin: {power_pin}, Direction pin: {direction_pin}",
                        ),
                    )
                    pump_frame.grid(
                        row=(pump_id - 1) // self.pumps_per_row,
                        column=(pump_id - 1) % self.pumps_per_row,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NSWE",
                    )
                    # first row in the pump frame
                    power_label = label(
                        pump_frame, f"Power Status: {power_status}", 0, 0
                    )
                    direction_label = label(
                        pump_frame, f"Direction Status: {direction_status}", 0, 1
                    )
                    # second row in the pump frame
                    power_button = button(
                        pump_frame,
                        "Toggle Power",
                        1,
                        0,
                        lambda pid=pump_id: self.toggle_power(pid),
                        state="disabled" if power_pin == "-1" else "normal",
                    )
                    direction_button = button(
                        pump_frame,
                        "Toggle Direction",
                        1,
                        1,
                        lambda pid=pump_id: self.toggle_direction(pid),
                        state="disabled" if direction_pin == "-1" else "normal",
                    )
                    # third row in the pump frame
                    button(
                        pump_frame,
                        "Remove",
                        2,
                        0,
                        lambda pid=pump_id: self.remove_pump(
                            remove_all=False, pump_id=pid
                        ),
                    )
                    button(
                        pump_frame,
                        "Edit",
                        2,
                        1,
                        lambda pid=pump_id: self.edit_pump(pid),
                    )
                    self.pumps[pump_id] = {
                        "power_pin": power_pin,
                        "direction_pin": direction_pin,
                        "initial_power_pin_value": initial_power_pin_value,
                        "initial_direction_pin_value": initial_direction_pin_value,
                        "power_status": power_status,
                        "direction_status": direction_status,
                        "pump_frame": pump_frame,
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
                    pump_frame = self.pumps[pump_id]["pump_frame"]
                    pump_frame.grid(
                        row=(pump_id - 1) // self.pumps_per_row,
                        column=(pump_id - 1) % self.pumps_per_row,
                        padx=global_pad_x,
                        pady=global_pad_y,
                        sticky="NSWE",
                    )
                    self.pumps[pump_id]["power_label"].configure(
                        text=f"Power Status: {power_status}"
                    )
                    self.pumps[pump_id]["direction_label"].configure(
                        text=f"Direction Status: {direction_status}"
                    )
                    self.pumps[pump_id]["power_button"].configure(
                        state="normal" if power_pin != "-1" else "disabled"
                    )
                    self.pumps[pump_id]["direction_button"].configure(
                        state="normal" if direction_pin != "-1" else "disabled"
                    )
                    self.pumps[pump_id]["pump_frame"].configure(
                        text=f"Pump {pump_id}, Power pin: {power_pin}, Direction pin: {direction_pin}"
                    )
                else:  # we have a pump with the same id but different controller
                    non_blocking_messagebox(
                        parent=self.root,
                        title="Error: Duplicate Pump Id",
                        message=f"Pump {pump_id} in controller {controller_id} already exists in controller {self.pump_ids_to_controller_ids[pump_id]}!\nDuplicate pump ids are not allow!\nConnect ONLY to one of the above controllers and remove the duplicated pump id to resolve this issue.",
                    )
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
            self.pumps.clear()
            self.pump_ids_to_controller_ids.clear()
            self.controller_ids_to_pump_ids.clear()
        else:
            if pump_id:  # we now remove a specific pump
                if pump_id in self.pumps:
                    self.pumps[pump_id]["pump_frame"].destroy()
                    self.pumps.pop(pump_id)
                    controller_id = self.pump_ids_to_controller_ids.pop(pump_id)
                    self.controller_ids_to_pump_ids[controller_id].remove(pump_id)
            elif controller_id:  # we now remove all pumps under a specific controller
                if controller_id in self.controller_ids_to_pump_ids:
                    for pump_id in self.controller_ids_to_pump_ids[controller_id]:
                        self.pumps[pump_id]["pump_frame"].destroy()
                        self.pumps.pop(pump_id)
                        self.pump_ids_to_controller_ids.pop(pump_id)
                    self.controller_ids_to_pump_ids.pop(controller_id)

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
                    try:
                        temp_df = pd.read_excel(
                            file_path,
                            sheet_name="Do Not Edit (Export Settings)",
                            keep_default_na=False,
                            dtype=object,
                        )
                    except Exception as _:
                        non_blocking_messagebox(
                            parent=self.root,
                            title="Error",
                            message="The recipe file does not contain a 'Do Not Edit (Export Settings)' sheet.",
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
                    # record the index of the first time point that is not in order
                    for index, value in enumerate(
                        self.recipe_df[recipe_header].values[:-1]
                    ):
                        if value > self.recipe_df[recipe_header].values[index + 1]:
                            self.recipe_df_time_header_index = index
                            break
                    raise ValueError(
                        f"Time points are required in monotonically increasing order, at index {self.recipe_df_time_header_index} with value {self.recipe_df[recipe_header].values[self.recipe_df_time_header_index]} VS next value {self.recipe_df[recipe_header].values[self.recipe_df_time_header_index + 1]}.\n Please check the recipe file."
                    )

                # check if there is duplicate time points
                if self.recipe_df[recipe_header].duplicated().any():
                    raise ValueError("Duplicate time points are not allowed.")

                # Setup the table to display the data
                columns = list(self.recipe_df.columns) + [
                    "Progress",
                    "Remaining Time",
                ]
                # delete the original recipe table
                for child in self.recipe_table_frame.winfo_children():
                    child.destroy()
                self.create_recipe_sequence_table(self.recipe_table_frame, columns)

                for col in columns:
                    self.recipe_table.heading(col, text=col)
                    self.recipe_table.column(
                        col,
                        width=int(len(col) * 10 * getScalingFactor()),
                        anchor="center",
                    )

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
                # set width for the notes column if it exists
                if "Notes" in columns:
                    self.recipe_table.column("Notes", width=150, anchor="center")

                # Enable the start button
                self.start_button.configure(state="normal", hover=True)
                self.clear_recipe_button.configure(state="normal", hover=True)

                # now setup the eChem table
                for child in self.eChem_sequence_table_frame.winfo_children():
                    child.destroy()
                columns = list(self.eChem_sequence_df.columns)
                self.create_eChem_sequence_table(
                    self.eChem_sequence_table_frame, columns
                )

                for col in columns:
                    self.eChem_sequence_table.heading(col, text=col)
                    self.eChem_sequence_table.column(
                        col,
                        width=int(len(col) * 10 * getScalingFactor()),
                        anchor="center",
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
                    self.generate_sequence_button.configure(state="normal", hover=True)
                    non_blocking_custom_messagebox(
                        parent=self.root,
                        title="Convert to GSequence?",
                        message="Convert EChem sequence to a GSequence file?",
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
            for child in self.recipe_table_frame.winfo_children():
                child.destroy()
            # recreate the recipe table
            self.create_recipe_sequence_table(self.recipe_table_frame)
            # clear the progress bar
            self.total_progress_bar.set(0)
            self.remaining_time_value.configure(text="")
            self.end_time_value.configure(text="")

            # clear the eChem table
            self.eChem_sequence_df = None
            self.generate_sequence_button.configure(state="disabled", hover=True)
            self.eChem_sequence_df_time_header_index = -1
            for child in self.eChem_sequence_table_frame.winfo_children():
                child.destroy()
            # recreate the eChem table
            self.create_eChem_sequence_table(self.eChem_sequence_table_frame)

            # disable all procedure buttons
            self.clear_recipe_button.configure(state="disabled", hover=True)
            self.start_button.configure(state="disabled", hover=True)
            self.stop_button.configure(state="disabled", hover=True)
            self.pause_button.configure(state="disabled", hover=True)
            self.continue_button.configure(state="disabled", hover=True)
            logging.info("Recipe cleared successfully.")
        except Exception as e:
            logging.error(f"Error: {e}")
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"An error occurred in function clear_recipe: {e}",
            )

    def start_procedure(self, confirmation=False):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        # require at least one MCU connection
        if (
            not self.autosampler.is_open
            and not self.potentiostat.is_open
            and not any(self.pc_connected.values())
        ):
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message="No controller connection. Please connect to at least one controller to continue.",
            )
            return
        # warning if only one MCU is connected
        if (
            not self.autosampler.is_open
            or not self.potentiostat.is_open
            or not any(self.pc_connected.values())
        ):
            if not confirmation:

                def callback(choice):
                    if choice == "Yes":
                        self.start_procedure(confirmation=True)

                non_blocking_custom_messagebox(
                    parent=self.root,
                    title="Warning",
                    message="Only one type of controller connected. Continue?",
                    buttons=["Yes", "No"],
                    callback=callback,
                )
                return
        logging.info("Starting procedure...")
        try:
            self.stop_button.configure(state="normal", hover=True)
            self.pause_button.configure(state="normal", hover=True)
            self.continue_button.configure(state="disabled", hover=True)
            # disable the disconnect button for connected controllers
            for (
                controller_id,
                connection_status,
            ) in self.pc_connected.items():
                if connection_status:
                    for b in self.pc_id_to_widget_map[controller_id][
                        "disconnect_buttons"
                    ]:
                        b.configure(state="disabled", hover=True)
            if self.autosampler.is_open:
                for b in self.autosampler_widget_map["disconnect_buttons"]:
                    b.configure(state="disabled", hover=True)
            if self.potentiostat.is_open:
                for b in self.potentiostat_widget_map["disconnect_buttons"]:
                    b.configure(state="disabled", hover=True)
            self.pause_timepoint_ns = -1  # clear the stop time and pause time
            if self.scheduled_task:  # cancel the scheduled task if it exists
                self.root.after_cancel(self.scheduled_task)
                self.scheduled_task = None
            # calculate the total procedure time, max time point in the first column
            self.total_procedure_time_ns = convert_minutes_to_ns(
                float(self.recipe_df.iloc[:, self.recipe_df_time_header_index].max())
            )
            # clear the "Progress Bar" and "Remaining Time" columns in the recipe table
            if type(self.recipe_table) is ttk.Treeview:
                for _, child in self.recipe_rows:
                    self.recipe_table.set(child, "Progress", "")
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
                logging.info("Procedure completed.")
                self.update_progress()  # update progress bar and remaining time
                self.stop_procedure(message=False)
                non_blocking_messagebox(
                    parent=self.root,
                    title="Procedure Complete",
                    message=f"The procedure has been completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                )
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
            def extract_by_pattern(row, pattern):
                return {
                    col: row[col]
                    for col in row.index
                    if re.search(pattern, col, re.IGNORECASE)
                }

            pump_actions = extract_by_pattern(row, r"Pump")
            valve_actions = extract_by_pattern(row, r"Valve")
            potentiostat_actions = extract_by_pattern(row, r"Potentiostat")
            auto_sampler_actions_slots = extract_by_pattern(
                row, r"^(?!.*position).*Autosampler.*(slot)?$"
            )
            auto_sampler_actions_positions = extract_by_pattern(
                row, r"^(?!.*slot).*Autosampler.*(position)$"
            )
            logging.debug(f"Pump actions: {pump_actions}")
            logging.debug(f"Valve actions: {valve_actions}")
            logging.debug(f"Autosampler actions (slots): {auto_sampler_actions_slots}")
            logging.debug(
                f"Autosampler actions (positions): {auto_sampler_actions_positions}"
            )
            logging.debug(f"Potentiostat actions: {potentiostat_actions}")

            # issue a one-time status update for all pumps and autosampler
            for id, connection_status in self.pc_connected.items():
                if connection_status:
                    self.update_status(controller_id=id)
            self.execute_actions(
                index,
                pump_actions,
                valve_actions,
                auto_sampler_actions_slots,
                auto_sampler_actions_positions,
                potentiostat_actions,
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
        potentiostat_actions,
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

        for _, action in potentiostat_actions.items():
            if pd.isna(action) or action == "":
                continue
            # this is a bit counterintuitive
            # but when on, we want to set the trigger pin to low to signal the potentiostat to start
            if action.lower() == "on":
                self.set_trigger_po(state="high")
            elif action.lower() == "off":
                self.set_trigger_po(state="low")

        # update status for all pumps and autosampler
        for id, connection_status in self.pc_connected.items():
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
            total_progress = 0
            remaining_time_ns = 0
        else:
            total_progress = min(0, (elapsed_time_ns / self.total_procedure_time_ns))
            remaining_time_ns = max(
                0,
                self.total_procedure_time_ns - elapsed_time_ns,
            )

        self.total_progress_bar.set(int(total_progress))
        self.remaining_time_value.configure(
            text=f"{convert_ns_to_timestr(int(remaining_time_ns))}"
        )
        end_time = datetime.now() + timedelta(
            seconds=remaining_time_ns / NANOSECONDS_PER_SECOND
        )
        formatted_end_time = end_time.strftime("%Y-%m-%d %a %H:%M:%S")
        self.end_time_value.configure(text=f"{formatted_end_time}")

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

                if type(self.recipe_table) is ttk.Treeview:
                    # Update only the "Progress Bar" and "Remaining Time" columns
                    self.recipe_table.set(child, "Progress", f"{row_progress}%")
                    self.recipe_table.set(
                        child,
                        "Remaining Time",
                        f"{convert_ns_to_timestr(int(remaining_time_row_ns))}",
                    )

    def add_pump(self):
        # if we have any connected pump controller, we can add a pump
        if not any(self.pc_connected.values()):
            non_blocking_messagebox(
                parent=self.root, title="Error", message="Not connected to Pico."
            )
            return

        try:
            controller_list = [
                f"Controller {id}"
                for id, connected in self.pc_connected.items()
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
                "placeholder_text": "Enter Power Pin (e.g., 17)",
            },
            {
                "label": "Direction Pin",
                "type": "text",
                "initial_value": int(pump["direction_pin"]),
                "placeholder_text": "Enter Direction Pin (e.g., 18)",
            },
            {
                "label": "Initial Power Pin Value",
                "type": "text",
                "initial_value": int(pump["initial_power_pin_value"]),
                "placeholder_text": "Enter Initial Power Pin Value (0 or 1)",
            },
            {
                "label": "Initial Direction Pin Value",
                "type": "text",
                "initial_value": int(pump["initial_direction_pin_value"]),
                "placeholder_text": "Enter Initial Direction Pin Value (0 or 1)",
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
        result_var = ctk.StringVar(value="")

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
                message="Quit or minimize to tray?",
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
        for id, connection_status in self.pc_connected.items():
            if connection_status:
                self.disconnect_pc(id, show_message=False)
        if self.autosampler.is_open:
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
                init_dir = self.gSquence_save_path_entry.get()
                if not os.path.exists(init_dir):
                    init_dir = os.getcwd()
                save_path = filedialog.asksaveasfilename(
                    title="Save GSequence File",
                    defaultextension=".GSequence",
                    filetypes=[
                        ("GSequence files", "*.GSequence"),
                        ("All files", "*.*"),
                    ],
                    initialdir=init_dir,
                    initialfile=f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} Auto Echem Sequence.GSequence",
                )
                if save_path:
                    new_method_tree.write(
                        save_path, encoding="utf-8", xml_declaration=True
                    )
                    # update the config file with the new path
                    save_dir = os.path.dirname(save_path)
                    temp_dir_list = self.config.get("gSequence_save_dir_history", [])
                    if save_dir not in temp_dir_list:
                        temp_dir_list.insert(0, save_dir)
                    self.config["gSequence_save_dir_history"] = temp_dir_list
                    self.gSquence_save_path_entry["values"] = temp_dir_list
                    self.gSquence_save_path_entry.set(temp_dir_list[0])
                    save_config(self.config)
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

    def set_gSequence_save_path(self):
        """
        Set the GSequence save path to the selected directory.
        """
        try:
            # Get the selected directory
            selected_directory = filedialog.askdirectory(
                title="Select GSequence Save Directory"
            )
            if selected_directory:
                # Update the config file with the new path
                temp_dir_list = self.config.get("gSequence_save_dir_history", [])
                if selected_directory not in temp_dir_list:
                    temp_dir_list.insert(0, selected_directory)
                self.config["gSequence_save_dir_history"] = temp_dir_list
                self.gSquence_save_path_entry["values"] = temp_dir_list
                self.gSquence_save_path_entry.set(temp_dir_list[0])
                save_config(self.config)
                non_blocking_messagebox(
                    parent=self.root,
                    title="Success",
                    message=f"GSequence save path set to {selected_directory}",
                )
        except Exception as e:
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Error setting GSequence save path: {e}",
            )

    def clear_gSequence_save_path_history(self):
        """
        Clear the history of saved GSequence paths from the configuration file and from the combo box.
        """
        try:
            self.config["gSequence_save_dir_history"] = []
            self.gSquence_save_path_entry["values"] = []
            self.gSquence_save_path_entry.set("")
            save_config(self.config)
            non_blocking_messagebox(
                parent=self.root,
                title="Success",
                message="GSequence save path history cleared.",
            )
        except Exception as e:
            non_blocking_messagebox(
                parent=self.root,
                title="Error",
                message=f"Error clearing GSequence save path history: {e}",
            )

    def update_directory_history(self, event):
        """
        reorder the self.config["gSequence_save_dir_history"] to make the currently selected item to be at the top
        """
        try:
            selected_directory = self.gSquence_save_path_entry.get()
            if selected_directory and selected_directory != "":
                temp_dir_list = self.config.get("gSequence_save_dir_history", [])
                if selected_directory in temp_dir_list:
                    temp_dir_list.remove(selected_directory)
                temp_dir_list.insert(0, selected_directory)
                self.config["gSequence_save_dir_history"] = temp_dir_list
                self.gSquence_save_path_entry["values"] = temp_dir_list
        except Exception as e:
            logging.error(f"Error updating GSequence save path history: {e}")


# set dpi awareness to avoid scaling issues
ctk.set_default_color_theme("dark-blue")

ctk.set_appearance_mode("light")
setProcessDpiAwareness()
root = ctk.CTk()
root.resizable(True, True)
check_lock_file(root)
root.iconbitmap(resource_path(os.path.join("icons", "icons-red.ico")))
app = PicoController(root)
root.deiconify()
root.geometry(f"+{root.winfo_screenwidth() // 8}+{root.winfo_screenheight() // 8}")
root.protocol("WM_DELETE_WINDOW", app.on_closing)
root.mainloop()
remove_lock_file()
