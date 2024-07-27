# pyserial imports
import serial
import serial.tools.list_ports

# gui imports
import sys
from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QInputDialog

# other library
import os
import re
import time
import logging
from datetime import datetime
from queue import Queue
import pandas as pd

# Import the converted UI file
from mainwindow import Ui_MainWindow
from pump_frame import Ui_GroupBox

# Define Pi Pico vendor ID
pico_vid = 0x2E8A


class PicoController(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.pump_frame_setup = Ui_GroupBox()
        self.ui.setupUi(self)

        # port refresh timer
        self.last_port_refresh = -1
        self.port_refresh_interval = 5  # Refresh rate for COM ports when not connected
        self.timeout = 1  # Serial port timeout in seconds
        self.main_loop_interval = 10  # Main loop interval in milliseconds

        # instance fields for the serial port and queue
        self.serial_port = None
        self.current_port = None

        # a queue to store commands to be sent to the Pico
        self.send_command_queue = Queue()

        # Dictionary to store pump information
        self.pumps = {}

        self.recipe_df = pd.DataFrame()
        self.recipe_rows = []

        # time stamp for the start of the procedure
        self.start_time = -1
        self.total_procedure_time = -1
        self.current_index = -1
        self.pause_timepoint = -1
        self.pause_duration = 0
        self.scheduled_task = None

        runtime = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.mkdir("log")
        except FileExistsError:
            pass
        log_filename = os.path.join("log", f"pico_controller_run_{runtime}.log")
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s: %(message)s [%(funcName)s]",
            handlers=[logging.FileHandler(log_filename), logging.StreamHandler()],
        )

        self.create_widgets()
        self.refresh_ports()
        self.start_main_loop()

    def create_widgets(self):
        self.ui.connectButton.clicked.connect(self.connect_to_pico)
        self.ui.disconnectButton.clicked.connect(self.disconnect_pico)
        self.ui.loadRecipeButton.clicked.connect(self.load_recipe)
        self.ui.startButton.clicked.connect(self.start_procedure)
        self.ui.stopButton.clicked.connect(self.stop_procedure)
        self.ui.pauseButton.clicked.connect(self.pause_procedure)
        self.ui.continueButton.clicked.connect(self.continue_procedure)
        self.ui.addPumpButton.clicked.connect(self.add_pump)
        self.ui.clearPumpsButton.clicked.connect(self.clear_pumps)

        self.ui.remainingTimeLabel.setText(
            QtCore.QCoreApplication.translate(
                "MainWindow",
                "Remaining Time: " + time.strftime("%H:%M:%S", time.gmtime(0)),
            )
        )

    def start_main_loop(self):
        self.refresh_ports()
        self.read_serial()
        self.send_command()
        self.update_progress()
        QtCore.QTimer.singleShot(self.main_loop_interval, self.start_main_loop)

    def refresh_ports(self):
        if not self.serial_port:
            if time.time() - self.last_port_refresh < self.port_refresh_interval:
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

            self.ui.portComboBox.clear()
            self.ui.portComboBox.addItems(ports)
            self.last_port_refresh = time.time()

    def connect_to_pico(self):
        selected_port = self.ui.portComboBox.currentText()
        if selected_port:
            # Check if already connected
            if self.serial_port:
                # if already connected, pop a confirmation message before disconnecting
                if (
                    QMessageBox.question(
                        self,
                        "Disconnect",
                        "Disconnect from current port?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                ):
                    # suppress the message for the disconnect
                    self.disconnect_pico(show_message=False)
                else:
                    return

            # Attempt to connect to the selected port
            try:
                parsed_port = selected_port.split("(")[0].strip()
                self.serial_port = serial.Serial(parsed_port, timeout=self.timeout)
                self.current_port = selected_port
                self.ui.statusLabel.setText(f"Status: Connected to {parsed_port}")

                logging.info(f"Connected to {selected_port}")
                QMessageBox.information(
                    self,
                    "Connection Status",
                    f"Successfully connected to {parsed_port}",
                )

                # issue a pump info query
                self.query_pump_info()
                # enable the disconnect button
                self.ui.disconnectButton.setEnabled(True)

            except serial.SerialException as e:
                self.ui.statusLabel.setText("Status: Not connected")
                logging.error(f"Error: {e}")
                QMessageBox.critical(
                    self, "Connection Status", f"Failed to connect to {selected_port}"
                )

    def disconnect_pico(self, show_message=True):
        if self.serial_port:
            # close the serial port connection
            self.serial_port.close()
            self.serial_port = None
            self.current_port = None

            # update UI
            self.ui.statusLabel.setText("Status: Not connected")

            # clear the pumps widgets
            self.clear_pumps_widgets()
            # clear the recipe table
            self.clear_recipe()

            # disable the disconnect button
            self.ui.disconnectButton.setEnabled(False)

            # refresh the port list immediately
            self.refresh_ports()

            logging.info("Disconnected from Pico")
            if show_message:
                QMessageBox.information(
                    self, "Connection Status", "Disconnected from Pico"
                )

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
            command = f"{pump_id}:reg:{power_pin}:{direction_pin}:{initial_power_pin_value}:{initial_direction_pin_value}:{initial_power_status}:{initial_direction_status}"
            self.send_command_queue.put(command)
            self.update_status()

    def clear_pumps(self):
        if self.serial_port:
            if (
                QMessageBox.question(
                    self,
                    "Clear Pumps",
                    "Clear all pumps?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.send_command_queue.put("0:clr")
                self.clear_pumps_widgets()

    def stop_procedure(self):
        if self.scheduled_task:
            # kill the timer
            logging.debug(
                f"kill timer at index {self.current_index} with remaining time: {self.scheduled_task.remainingTime()}"
            )
            self.scheduled_task.stop()
            self.scheduled_task = None
        self.start_time = -1
        self.total_procedure_time = -1
        self.current_index = -1
        self.pause_timepoint = -1
        self.pause_duration = 0
        # disable the buttons
        self.ui.stopButton.setEnabled(False)
        self.ui.pauseButton.setEnabled(False)
        self.ui.continueButton.setEnabled(False)
        logging.info("Procedure stopped.")
        QMessageBox.information(
            self, "Procedure Stopped", "The procedure has been stopped."
        )

    def pause_procedure(self):
        if self.scheduled_task:
            logging.debug(
                f"kill timer at index {self.current_index} with remaining time: {self.scheduled_task.remainingTime()}"
            )
            self.scheduled_task.stop()
            self.scheduled_task = None
        self.pause_timepoint = time.time()
        self.ui.pauseButton.setEnabled(False)
        self.ui.continueButton.setEnabled(True)
        logging.info("Procedure paused.")

    def continue_procedure(self):
        if self.pause_timepoint != -1:
            self.pause_duration += time.time() - self.pause_timepoint
            self.pause_timepoint = -1
        self.ui.pauseButton.setEnabled(True)
        self.ui.continueButton.setEnabled(False)
        self.execute_procedure(self.current_index)
        logging.info("Procedure continued.")

    # send_command will remove the first item from the queue and send it
    def send_command(self):
        try:
            if self.serial_port and not self.send_command_queue.empty():
                command = self.send_command_queue.get(block=True, timeout=None)
                self.serial_port.write(f"{command}\n".encode())
                logging.info(f"PC -> Pico: {command}")
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Error: {e}")
            QMessageBox.critical(
                self,
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Send_command: An error occurred: {e}")
            logging.error(f"Error: {e}")
            # call disconnect_pico to clear the serial port
            self.disconnect_pico()

    def read_serial(self):
        try:
            if self.serial_port and self.serial_port.in_waiting:
                response = self.serial_port.readline().decode("utf-8").strip()
                logging.info(f"Pico -> PC: {response}")
                if "Info" in response:
                    self.add_pump_widgets(response)
                elif "Status" in response:
                    self.update_pump_status(response)
                elif "Error" in response:
                    QMessageBox.critical(self, "Error", response)
                    logging.error(f"Error: {response}")
        except serial.SerialException as e:
            self.disconnect_pico(False)
            logging.error(f"Error: {e}")
            QMessageBox.critical(
                self,
                "Connection Error",
                "Connection to Pico lost. Please reconnect to continue.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Read_serial: An error occurred: {e}")
            logging.error(f"Error: {e}")
            # call disconnect_pico to clear the serial port
            self.disconnect_pico()

    def add_pump_widgets(self, response):
        info_pattern = re.compile(
            r"Pump(\d+) Info: Power Pin: (-?\d+), Direction Pin: (-?\d+), Initial Power Pin Value: (\d+), Initial Direction Pin Value: (\d+), Current Power Status: (ON|OFF), Current Direction Status: (CW|CCW)"
        )
        matches = info_pattern.findall(response)

        # sort the matches by pump_id in ascending order
        matches = sorted(matches, key=lambda x: int(x[0]))

        # get the existing count of pumps widgets
        count = self.ui.manualControl_second.count()

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
            else:
                pump_frame = QtWidgets.QGroupBox(self.ui.manualControl_2)
                # use the Ui_GroupBox class to set up the pump frame
                pump_frame_struct_class = Ui_GroupBox()
                pump_frame_struct_class.setupUi(pump_frame)
                pump_frame.setTitle(f"Pump {pump_id}")

                # resize the manualControl_sec widget to fit the new frame
                self.ui.manualControl_2.resize(
                    50 + pump_frame.minimumWidth() * (count % 3),
                    50 + pump_frame.minimumHeight() * (count // 3),
                )

                self.ui.manualControl_second.addWidget(
                    pump_frame, count // 3, count % 3
                )

                self.pumps[pump_id] = {
                    "frame": pump_frame,
                    "struct_class": pump_frame_struct_class,
                    "power_pin": power_pin,
                    "direction_pin": direction_pin,
                    "initial_power_pin_value": initial_power_pin_value,
                    "initial_direction_pin_value": initial_direction_pin_value,
                    "power_status": power_status,
                    "direction_status": direction_status,
                }

                count += 1

            # Update contents of the pump frame
            self.update_pump_frame(pump_id, pump_frame_struct_class)

    # Function to update the pump frame with the latest information from the dictionary
    def update_pump_frame(self, pump_id, pump_frame_struct_class):

        pump_label = pump_frame_struct_class.pump_label
        pump_label.setText(
            f"Power pin: {'N/A' if self.pumps[pump_id]['power_pin'] == '-1' else self.pumps[pump_id]['power_pin']}, Direction pin: {'N/A' if self.pumps[pump_id]['direction_pin'] == '-1' else self.pumps[pump_id]['direction_pin']}"
        )

        status_label = pump_frame_struct_class.status_label
        status_label.setText(
            f"Power Status: {self.pumps[pump_id]['power_status']} Direction Status: {self.pumps[pump_id]['direction_status']}"
        )

        power_button = pump_frame_struct_class.power_button
        power_button.setEnabled(self.pumps[pump_id]["power_pin"] != "-1")
        power_button.clicked.connect(lambda: self.toggle_power(pump_id))

        direction_button = pump_frame_struct_class.direction_button
        direction_button.setEnabled(self.pumps[pump_id]["direction_pin"] != "-1")
        direction_button.clicked.connect(lambda: self.toggle_direction(pump_id))

        edit_button = pump_frame_struct_class.edit_button
        edit_button.clicked.connect(lambda: self.edit_pump(pump_id))

    def clear_pumps_widgets(self):
        layout = self.ui.manualControl_second
        while layout.count():
            child = layout.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()
        self.pumps = {}

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
                self.update_pump_frame(pump_id, self.pumps[pump_id]["struct_class"])

    def load_recipe(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Recipe File", "", "CSV/Excel Files (*.xlsx *.xls *.csv);; ()"
        )
        if file_path:
            try:
                self.clear_recipe()
                if file_path.endswith(".csv"):
                    self.recipe_df = pd.read_csv(
                        file_path, keep_default_na=False, engine="python"
                    )
                elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                    self.recipe_df = pd.read_excel(
                        file_path, keep_default_na=False, engine="openpyxl"
                    )
                else:
                    raise ValueError("Invalid file format.")

                if self.recipe_df is None or self.recipe_df.empty:
                    logging.error("No recipe data to display.")
                    return

                self.ui.recipeTable.setRowCount(len(self.recipe_df))
                self.ui.recipeTable.setColumnCount(len(self.recipe_df.columns) + 2)
                self.ui.recipeTable.setHorizontalHeaderLabels(
                    list(self.recipe_df.columns) + ["Progress Bar", "Remaining Time"]
                )

                for index, row in self.recipe_df.iterrows():
                    for col_index, value in enumerate(row):
                        self.ui.recipeTable.setItem(
                            index, col_index, QtWidgets.QTableWidgetItem(str(value))
                        )

                self.ui.recipeTable.horizontalHeader().setVisible(True)
                self.ui.recipeTable.horizontalHeader().setCascadingSectionResizes(True)
                self.ui.recipeTable.horizontalHeader().setDefaultSectionSize(100)
                self.ui.recipeTable.horizontalHeader().setMinimumSectionSize(50)
                self.ui.recipeTable.horizontalHeader().setSortIndicatorShown(True)
                self.ui.recipeTable.horizontalHeader().setStretchLastSection(True)
                self.ui.recipeTable.verticalHeader().setVisible(True)
                self.ui.recipeTable.verticalHeader().setCascadingSectionResizes(True)
                self.ui.recipeTable.verticalHeader().setHighlightSections(True)
                self.ui.recipeTable.verticalHeader().setSortIndicatorShown(True)
                self.ui.recipeTable.verticalHeader().setStretchLastSection(False)

                self.ui.startButton.setEnabled(True)

                logging.info(f"Recipe file loaded successfully: {file_path}")
                QMessageBox.information(
                    self, "File Load", f"Recipe file loaded successfully: {file_path}"
                )

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "File Load Error",
                    f"Failed to load recipe file {file_path}: {e}",
                )
                logging.error(f"Failed to load recipe file {file_path}: {e}")

    def clear_recipe(self):
        self.recipe_df = None
        self.recipe_rows = []
        self.ui.recipeTable.setRowCount(0)
        self.ui.recipeTable.setColumnCount(0)
        self.ui.recipeTable.clear()

        self.ui.totalProgressBar.setValue(0)
        self.ui.remainingTimeLabel.setText(
            QtCore.QCoreApplication.translate("MainWindow", "Remaining Time: 00:00:00")
        )

        self.ui.startButton.setEnabled(False)
        self.ui.stopButton.setEnabled(False)
        self.ui.pauseButton.setEnabled(False)
        self.ui.continueButton.setEnabled(False)

    def start_procedure(self):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        if self.recipe_df is None:
            QMessageBox.critical(self, "Error", "No recipe file loaded.")
            return

        if not self.serial_port:
            QMessageBox.critical(self, "Error", "Not connected to Pico.")
            return

        logging.info("Starting procedure...")
        self.ui.stopButton.setEnabled(True)
        self.ui.pauseButton.setEnabled(True)
        self.ui.continueButton.setEnabled(False)

        self.pause_timepoint = -1
        self.total_procedure_time = self.recipe_df["Time point (min)"].max() * 60

        for i, row in self.recipe_df.iterrows():
            for col_index, value in enumerate(row):
                self.ui.recipeTable.setItem(
                    i, col_index, QtWidgets.QTableWidgetItem(str(value))
                )

        self.start_time = time.time() - self.pause_duration
        self.current_index = 0
        self.execute_procedure()

    def execute_procedure(self, index=0):
        if self.recipe_df is None or self.recipe_df.empty:
            logging.error("No recipe data to execute.")
            return
        if index >= len(self.recipe_df):
            # call update progress one last time to set the progress to 100%
            self.update_progress()
            self.start_time = -1
            self.total_procedure_time = -1
            self.current_index = -1
            logging.info("Procedure completed.")
            QMessageBox.information(
                self, "Procedure Complete", "The procedure has been completed."
            )
            self.ui.stopButton.setEnabled(False)
            self.ui.pauseButton.setEnabled(False)
            self.ui.continueButton.setEnabled(False)
            return

        self.current_index = index
        row = self.recipe_df.iloc[index]
        target_time = float(row["Time point (min)"]) * 60

        elapsed_time = time.time() - self.start_time - self.pause_duration
        current_step_remaining_time = target_time - elapsed_time
        # set the sleep time to half of the remaining time for each scheduled timer
        # minimum sleep time is 1 ms
        intended_sleep_time = max(1, int(current_step_remaining_time * 1000 / 2))
        if elapsed_time < target_time:
            # initiate a normal timer and convert it to singleShot timer so that we have the reference to it
            self.scheduled_task = QtCore.QTimer()
            self.scheduled_task.setSingleShot(True)
            self.scheduled_task.timeout.connect(lambda: self.execute_procedure(index))
            logging.debug(
                f"init timer for {intended_sleep_time} ms, remaining time: {current_step_remaining_time * 1000} ms"
            )
            self.scheduled_task.start(intended_sleep_time)
            return

        logging.info(f"Executing step at index {index}")

        pump_actions = {col: row[col] for col in row.index if col.startswith("Pump")}
        valve_actions = {col: row[col] for col in row.index if col.startswith("Valve")}

        self.update_status()
        self.execute_actions(index, pump_actions, valve_actions)

    def execute_actions(self, index, pump_actions, valve_actions):
        for pump, action in pump_actions.items():
            if pd.isna(action) or action == "":
                continue

            match = re.search(r"\d+", pump)
            if not match:
                logging.error(f"No valid pump ID found in {pump_actions}")
                continue
            else:
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
            if not match:
                logging.error(f"No valid valve ID found in {valve_actions}")
                continue
            else:
                valve_id = int(match.group())

            if (
                valve_id in self.pumps
                and action.upper() != self.pumps[valve_id]["direction_status"].upper()
            ):
                logging.info(
                    f"At index {index}, valve_id {valve_id} status: {self.pumps[valve_id]['direction_status']}, intended status: {action}, toggling direction."
                )
                self.toggle_direction(valve_id, update_status=False)

        # issue a status update after executing the actions
        self.update_status()
        self.execute_procedure(index + 1)

    def update_progress(self):
        if (
            self.total_procedure_time == -1
            or self.recipe_df is None
            or self.recipe_df.empty
            or self.pause_timepoint != -1
        ):
            return
        elapsed_time = time.time() - self.start_time - self.pause_duration
        total_progress = int((elapsed_time / self.total_procedure_time) * 100)
        self.ui.totalProgressBar.setValue(total_progress)
        remaining_time = int(self.total_procedure_time - elapsed_time)
        time_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))
        self.ui.remainingTimeLabel.setText(f"Remaining Time: {time_str}")

        for i, row in self.recipe_df.iterrows():
            time_stamp = float(row["Time point (min)"]) * 60
            if elapsed_time < time_stamp:
                break
            else:
                if i < len(self.recipe_df) - 1:
                    next_row = self.recipe_df.iloc[i + 1]
                    next_time_stamp = float(next_row["Time point (min)"]) * 60
                    time_interval = next_time_stamp - time_stamp
                    row_progress = min(
                        100, int(((elapsed_time - time_stamp) / time_interval) * 100)
                    )
                    remaining_time_row = max(0, int(next_time_stamp - elapsed_time))
                else:
                    row_progress = 100
                    remaining_time_row = 0
                for col_index, value in enumerate(row):
                    self.ui.recipeTable.setItem(
                        i, col_index, QtWidgets.QTableWidgetItem(str(value))
                    )
                self.ui.recipeTable.setItem(
                    i, len(row), QtWidgets.QTableWidgetItem(f"{row_progress}%")
                )
                self.ui.recipeTable.setItem(
                    i,
                    len(row) + 1,
                    QtWidgets.QTableWidgetItem(f"{remaining_time_row}s"),
                )

    def add_pump(self):
        if not self.serial_port:
            QMessageBox.critical(self, "Error", "Not connected to Pico.")
            return

        pump_id = len(self.pumps) + 1
        self.add_pump_widgets(
            f"Pump{pump_id} Info: Power Pin: -1, Direction Pin: -1, Initial Power Pin Value: 0, Initial Direction Pin Value: 0, Current Power Status: OFF, Current Direction Status: CCW"
        )

    def edit_pump(self, pump_id):
        pump = self.pumps[pump_id]
        power_pin, ok = QInputDialog.getInt(
            self, "Power Pin", "Enter power pin ID:", int(pump["power_pin"])
        )
        if not ok:
            return
        direction_pin, ok = QInputDialog.getInt(
            self, "Direction Pin", "Enter direction pin ID:", int(pump["direction_pin"])
        )
        if not ok:
            return
        initial_power_pin_value, ok = QInputDialog.getInt(
            self,
            "Initial Power Pin Value",
            "Enter initial power pin value (0/1):",
            int(pump["initial_power_pin_value"]),
            0,
            1,
        )
        if not ok:
            return
        initial_direction_pin_value, ok = QInputDialog.getInt(
            self,
            "Initial Direction Pin Value",
            "Enter initial direction pin value (0/1):",
            int(pump["initial_direction_pin_value"]),
            0,
            1,
        )
        if not ok:
            return
        initial_power_status, ok = QInputDialog.getItem(
            self,
            "Initial Power Status",
            "Enter initial power status (ON/OFF):",
            ["ON", "OFF"],
            0,
            False,
        )
        if not ok:
            return
        initial_direction_status, ok = QInputDialog.getItem(
            self,
            "Initial Direction Status",
            "Enter initial direction status (CW/CCW):",
            ["CW", "CCW"],
            0,
            False,
        )
        if not ok:
            return

        self.register_pump(
            pump_id,
            power_pin,
            direction_pin,
            initial_power_pin_value,
            initial_direction_pin_value,
            initial_power_status,
            initial_direction_status,
        )
        self.query_pump_info()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = PicoController()
    window.show()
    sys.exit(app.exec())
