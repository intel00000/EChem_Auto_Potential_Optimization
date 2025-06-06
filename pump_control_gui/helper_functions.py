# gui imports
import customtkinter as ctk
import tkinter_helpers as tk_helpers

# other library
import os
import re
import sys
import ctypes
import json
import psutil
import logging
import datetime
import pandas as pd
import xml.etree.ElementTree as ET

# LOCK_FILE = os.path.join(str(os.getenv("pump_control")), "lockfile.txt")
if os.name == "nt":
    LOCK_FILE = os.path.join(str(os.getenv("APPDATA")), "pump_control", "lockfile.txt")
    CONFIG_FILE = os.path.join(str(os.getenv("APPDATA")), "pump_control", "config.json")
else:
    LOCK_FILE = os.path.join("log", "lockfile.txt")
    CONFIG_FILE = os.path.join("log", "config.json")

NANOSECONDS_PER_DAY = 24 * 60 * 60 * 1_000_000_000
NANOSECONDS_PER_HOUR = 60 * 60 * 1_000_000_000
NANOSECONDS_PER_MINUTE = 60 * 1_000_000_000
NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MILLISECOND = 1_000_000
NANOSECONDS_PER_MICROSECOND = 1_000


def check_lock_file(parent: ctk.CTk) -> None:
    # check if the folder exists first
    if not os.path.exists(os.path.dirname(LOCK_FILE)):
        os.makedirs(os.path.dirname(LOCK_FILE))
    # check if the lock file exists
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            # If the process exists, show a message box and exit
            tk_helpers.non_blocking_messagebox(
                parent,
                "Already Running",
                "Another instance of this program is already running, check your taskbar!",
            )
            sys.exit(0)
        else:
            # If the process doesn't exist, the lock file is stale; remove it
            os.remove(LOCK_FILE)
    # If no valid lock file or stale lock file, create a new one
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_lock_file() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        print(f"Error removing lock file: {e}")


def resource_path(relative_path) -> str:
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def convert_minutes_to_ns(minutes: float) -> int:
    return int(minutes * 60 * NANOSECONDS_PER_SECOND)


def convert_ns_to_timestr(ns: int) -> str:
    days = ns // NANOSECONDS_PER_DAY
    ns %= NANOSECONDS_PER_DAY
    hours = ns // NANOSECONDS_PER_HOUR
    ns %= NANOSECONDS_PER_HOUR
    minutes = ns // NANOSECONDS_PER_MINUTE
    ns %= NANOSECONDS_PER_MINUTE
    seconds = ns / NANOSECONDS_PER_SECOND
    # Build the formatted time string, hiding fields with 0 values
    time_parts = []
    if days > 0:
        time_parts.append(f"{days} days")
    if hours > 0:
        time_parts.append(f"{hours} hours")
    if minutes > 0:
        time_parts.append(f"{minutes} minutes")
    if seconds > 0:
        time_parts.append(f"{seconds:.1f} seconds")
    return ", ".join(time_parts)


def process_pump_actions(
    pumps, index, actions, action_type, status_key, toggle_function
):
    """
    Process pump actions such as power or direction toggling.

    Args:
        index (int): The current index of execution.
        actions (dict): A dictionary of pumps and their intended actions.
        action_type (str): The type of action (e.g., "power", "direction").
        status_key (str): The key in the pump dictionary to check current status.
        toggle_function (callable): The function to call to toggle the action.
    """
    for pump, action in actions.items():
        if pd.isna(action) or action == "":
            continue
        match = re.search(r"\d+", pump)
        if match:
            pump_id = int(match.group())
            if pump_id in pumps:
                current_status = pumps[pump_id][status_key].lower()
                intended_status = action.lower()
                if intended_status != current_status:
                    logging.debug(
                        f"At index {index}, pump_id {pump_id} {action_type}: {current_status}, "
                        f"intended {action_type}: {intended_status}, toggling."
                    )
                    toggle_function(pump_id, update_status=False)
            else:
                logging.error(f"Warning: pump_id {pump_id} not found at index {index}")


def wait_for_digital(
    template_method_tree: ET.ElementTree,
    DIGIN0: str,
    DIGIN1: str,
    DIGIN2: str,
    DIGIN3: str,
) -> ET.ElementTree:
    """
    Modifies the 'Wait for Digital In' element block in the XML template tree based on user inputs for digital inputs.
    There are 4 digital inputs, DIGIN0, DIGIN1, DIGIN2, DIGIN3, and we expect user to specify either Low or High for each input.
    Args:
        template_method_tree (ET.ElementTree): The XML template tree containing the method definitions.
        DIGIN0 (str): User input for Digital Input 0, expected values are 'Low' or 'High'.
        DIGIN1 (str): User input for Digital Input 1, expected values are 'Low' or 'High'.
        DIGIN2 (str): User input for Digital Input 2, expected values are 'Low' or 'High'.
        DIGIN3 (str): User input for Digital Input 3, expected values are 'Low' or 'High'.

    Returns:
        ET.ElementTree: A new ElementTree with the root being the modified 'Wait for Digital In' element.

    Raises:
        ValueError: If the 'Wait for Digital In' element block is not found in the template.
    """
    # Locate the 'Wait for Digital In' element block in the XML tree
    wait_for_digital_in = template_method_tree.find(
        ".//element[name='Wait for Digital In']"
    )
    if wait_for_digital_in is None:
        raise ValueError("'Wait for Digital In' not found in the methods template.")

    # Modify the digital inputs according to user input
    parameters = wait_for_digital_in.find("parameters")
    if parameters is not None:
        for param in parameters.findall("explain_selector"):
            tag = param.attrib.get("tag")
            # Determine which index corresponds to "High" and "Low"
            item0 = param.attrib.get("item0")
            index_high = "0" if item0 == "High" else "1"
            index_low = "1" if item0 == "High" else "0"
            # Set the index based on the user input
            if tag == "DIGIN0":
                param.set("index", index_high if DIGIN0 == "High" else index_low)
            elif tag == "DIGIN1":
                param.set("index", index_high if DIGIN1 == "High" else index_low)
            elif tag == "DIGIN2":
                param.set("index", index_high if DIGIN2 == "High" else index_low)
            elif tag == "DIGIN3":
                param.set("index", index_high if DIGIN3 == "High" else index_low)

    # Create a new ElementTree with the modified element block as the root
    new_tree = ET.ElementTree(wait_for_digital_in)
    ET.indent(new_tree)
    return new_tree


def group_data_files(
    template: ET.ElementTree,
    group_name: str,
    group_type_index: int = 0,
    runtime_setup_checked: bool = False,
) -> ET.ElementTree:
    """
    Modify the "Group Data Files" element in the XML template.

    Args:
        template (ET.ElementTree): The XML template tree.
        group_name (str): The value for the `GROUPNAME` parameter.
        group_type_index (int): The index for the `GROUPTYPE` parameter.
        runtime_setup_checked (bool): The state (True/False) for `RUNTIMESETUP`.

    Returns:
        ET.ElementTree: The new tree with the modified "Group Data Files" element.
    """
    # Find the "Group Data Files" element block
    group_data_files_element = template.find(".//element[name='Group Data Files']")
    if group_data_files_element is None:
        raise ValueError("'Group Data Files' not found in the template.")

    # Modify parameters within the element
    parameters = group_data_files_element.find("parameters")
    if parameters is not None:
        for param in parameters:
            tag = param.attrib.get("tag")
            if tag == "GROUPTYPE":
                param.set("index", str(group_type_index))  # Set index value
            elif tag == "GROUPNAME":
                param.set("value", group_name)  # Set group name
            elif tag == "RUNTIMESETUP":
                param.set(
                    "checked", "True" if runtime_setup_checked else "False"
                )  # Set runtime setup state

    # Modify the usecount
    usecount = group_data_files_element.find("usecount")
    if usecount is not None:
        usecount.text = "1"

    # Create a new ElementTree with the modified element block as the root
    new_tree = ET.ElementTree(group_data_files_element)
    ET.indent(new_tree)
    return new_tree


def charge(
    template: ET.ElementTree,
    title: str,
    output: str,
    capacity: float,
    cell_type_index: int,
    working_connection_index: int,
    expected_max_v: float,
    charge_mode_value: float,
    charge_mode_index: int,
    max_charge_time_index: int,
    max_charge_time_value: float,
    sample_time_value: float,
    charge_stop_at1_index: int,
    charge_stop_at1_value: float,
    charge_stop_at2_index: int,
    charge_stop_at2_value: float,
    voltage_finish_checked: bool,
    ir_comp_checked: bool,
    capacity_variable: str = "None",
    expected_max_v_variable: str = "None",
    charge_mode_variable: str = "None",
    max_charge_time_variable: str = "None",
    sample_time_variable: str = "None",
    charge_stop_at1_variable: str = "None",
    charge_stop_at2_variable: str = "None",
    voltage_finish_variable: str = "None",
) -> ET.ElementTree:
    """
    Modify the "Charge" element in the XML template.

    Args:
        template (ET.ElementTree): The XML template tree.
        title (str): The value for the `TITLE` parameter (e.g., "PWR Charge 1").
        output (str): The value for the `OUTPUT` parameter (e.g., "PWRCHARGE 1.DTA").
        capacity (float): The value for the `CAPACITY` parameter (A-hr).
        cell_type_index (int): The index for the `CELLTYPE` parameter (0: Half Cell, 1: Full Cell, 2: Both).
        working_connection_index (int): The index for the `WORKINGCONNECTION` parameter (0: Positive, 1: Negative).
        expected_max_v (float): The value for the `EXPECTEDMAXV` parameter (e.g., 10.0).
        charge_mode_value (float): The value for the `CHARGEMODE` parameter (e.g., 0.01).
        charge_mode_index (int): The index for the `CHARGEMODE` parameter (0: Constant Current, 1: Capacity * N, 2: Capacity / N).
        max_charge_time_index (int): The index for the `MAXCHARGETIME` parameter (0: Seconds, 1: Minutes, 2: Hours, 3: Days).
        max_charge_time_value (float): The value for the `MAXCHARGETIME` parameter.
        sample_time_value (float): The value for the `SAMPLETIME` parameter (e.g., 10.0).
        charge_stop_at1_index (int): The index for the `CHARGESTOPAT1` parameter.
        charge_stop_at1_value (float): The value for the `CHARGESTOPAT1` parameter.
        charge_stop_at2_index (int): The index for the `CHARGESTOPAT2` parameter.
        charge_stop_at2_value (float): The value for the `CHARGESTOPAT2` parameter.
        voltage_finish_checked (bool): Whether the `VOLTAGEFINISH` parameter is checked.
        ir_comp_checked (bool): Whether the `IRCOMP` parameter is checked.
        voltage_finish_variable (str): Variable for `VOLTAGEFINISH`.
        capacity_variable (str): Variable for `CAPACITY`.
        charge_mode_variable (str): Variable for `CHARGEMODE`.
        max_charge_time_variable (str): Variable for `MAXCHARGETIME`.
        sample_time_variable (str): Variable for `SAMPLETIME`.
        charge_stop_at1_variable (str): Variable for `CHARGESTOPAT1`.
        charge_stop_at2_variable (str): Variable for `CHARGESTOPAT2`.

    Returns:
        ET.ElementTree: The new tree with the modified "Charge" element.
    """
    # Find the "Charge" element block
    charge_element = template.find(".//element[name='Charge']")
    if charge_element is None:
        raise ValueError("'Charge' element not found in the template.")

    # Modify parameters within the element
    parameters = charge_element.find("parameters")
    if parameters is not None:
        for param in parameters:
            tag = param.attrib.get("tag")
            if tag == "TITLE":
                param.set("value", title)
            elif tag == "OUTPUT":
                param.set("value", output)
            elif tag == "CAPACITY":
                param.set("value", str(capacity))
                param.set("variable", capacity_variable)
            elif tag == "CELLTYPE":
                param.set("index", str(cell_type_index))
            elif tag == "WORKINGCONNECTION":
                param.set("index", str(working_connection_index))
            elif tag == "EXPECTEDMAXV":
                param.set("value", str(expected_max_v))
                param.set("variable", expected_max_v_variable)
            elif tag == "CHARGEMODE":
                param.set("value", str(charge_mode_value))
                param.set("index", str(charge_mode_index))
                param.set("variable", charge_mode_variable)
            elif tag == "MAXCHARGETIME":
                param.set("index", str(max_charge_time_index))
                param.set("value", str(max_charge_time_value))
                param.set("variable", max_charge_time_variable)
            elif tag == "SAMPLETIME":
                param.set("value", str(sample_time_value))
                param.set("variable", sample_time_variable)
            elif tag == "CHARGESTOPAT1":
                param.set("index", str(charge_stop_at1_index))
                param.set("value", str(charge_stop_at1_value))
                param.set("variable", charge_stop_at1_variable)
            elif tag == "CHARGESTOPAT2":
                param.set("index", str(charge_stop_at2_index))
                param.set("value", str(charge_stop_at2_value))
                param.set("variable", charge_stop_at2_variable)
            elif tag == "VOLTAGEFINISH":
                param.set("checked", "True" if voltage_finish_checked else "False")
                param.set("variable", voltage_finish_variable)
            elif tag == "IRCOMP":
                param.set("checked", "True" if ir_comp_checked else "False")

    # Create a new ElementTree with the modified element block as the root
    new_tree = ET.ElementTree(charge_element)
    ET.indent(new_tree)
    return new_tree


def delay(
    template: ET.ElementTree,
    delay_value: float,
    delay_style_index: int,
    delay_variable: str = "None",
) -> ET.ElementTree:
    """
    Modify the "Delay" element in the XML template.

    Args:
        template (ET.ElementTree): The XML template tree.
        delay_value (float): The value for the `DELAY` parameter (e.g., 9.58).
        delay_style_index (int): The index for the `DELAYSTYLE` parameter (0: Hours, 1: Minutes, 2: Seconds).
        delay_variable (str): Variable for the `DELAY` parameter.

    Returns:
        ET.ElementTree: The new tree with the modified "Delay" element.
    """
    # Find the "Delay" element block
    delay_element = template.find(".//element[name='Delay']")
    if delay_element is None:
        raise ValueError("'Delay' element not found in the template.")

    # Modify parameters within the element
    parameters = delay_element.find("parameters")
    if parameters is not None:
        for param in parameters:
            tag = param.attrib.get("tag")
            if tag == "DELAY":
                param.set("value", f"{delay_value:.2f}")
                param.set("variable", delay_variable)
            elif tag == "DELAYSTYLE":
                param.set("index", str(delay_style_index))

    # Create a new ElementTree with the modified element block as the root
    new_tree = ET.ElementTree(delay_element)
    ET.indent(new_tree)
    return new_tree


def generate_gsequence(df, template_method_path) -> ET.ElementTree | None:
    """
    Generate GSequence XML from the provided DataFrame and template method XML.

    Args:
        df (pd.DataFrame): DataFrame containing the methods to be included in the GSequence.
        template_method_path (str): Path to the template method XML file.

    Returns:
        ET.ElementTree: The generated GSequence XML tree.
    """
    # Read the template method XML file
    steps_header = df.columns[0]  # Get the first column name
    # Create the root element
    new_method_root = ET.Element("GamrySequence")
    name_tag = ET.SubElement(new_method_root, "name")
    name_tag.text = "Gamry Sequence"
    version_tag = ET.SubElement(new_method_root, "version")
    version_tag.text = "7.10.3.14563"
    charge_counter = 1  # filename counter for the output data files
    for _, row in df.iterrows():  # Add methods to the sequence
        with open(template_method_path, "r") as file:
            template_method_tree = ET.parse(file)
        method_name = row[steps_header]
        if method_name == "wait_for_digital":
            # "Wait for Digital In" method, hardcoded to wait for all inputs to be low
            method_tree = wait_for_digital(
                template_method_tree,
                DIGIN0="Low",
                DIGIN1="Low",
                DIGIN2="Low",
                DIGIN3="Low",
            )
            new_method_root.append(method_tree.getroot())
        elif method_name == "group_data_files":
            # Add "Group Data Files" method
            date_string = datetime.datetime.now().strftime("%Y-%m-%d")
            method_tree = group_data_files(
                template=template_method_tree,
                group_name=f"{date_string} Auto Echem Sequence",
                group_type_index=0,
                runtime_setup_checked=False,
            )
            new_method_root.append(method_tree.getroot())

        elif method_name == "charge":
            reaction_charge = float(row.get("Reaction Charge (mA h)", "None"))
            current = float(row.get("Current (A)", "None"))
            working_connection = row.get("Working Connection", "None")
            if (
                reaction_charge == "None"
                or current == "None"
                or working_connection == "None"
            ):
                raise ValueError(
                    "Missing at least one required values for charge method: "
                    "'Reaction Charge (mA h)', 'Current (A)', or 'Working Connection'."
                )
            # Add "Charge" method
            method_tree = charge(
                template=template_method_tree,
                title=f"PWR Charge {charge_counter}",
                output=f"PWRCHARGE {charge_counter}.DTA",
                capacity=10,
                cell_type_index=1,
                working_connection_index=1
                if "negative" in working_connection.lower()
                else 0,
                expected_max_v=10.0,
                charge_mode_value=current,
                charge_mode_index=0,
                max_charge_time_index=3,
                max_charge_time_value=2.0,
                sample_time_value=10.0,
                charge_stop_at1_index=7,
                charge_stop_at1_value=reaction_charge,
                charge_stop_at2_index=0,
                charge_stop_at2_value=0,
                voltage_finish_checked=False,
                ir_comp_checked=False,
            )
            new_method_root.append(method_tree.getroot())
            charge_counter += 1

        elif method_name == "delay":
            delay_value = float(row.get("Delays", "None"))
            if delay_value == "None":
                raise ValueError("Missing required value for delay method: 'Delays'.")
            # Add "Delay" method
            method_tree = delay(
                template=template_method_tree,
                delay_value=delay_value,
                delay_style_index=1,
                delay_variable="None",
            )
            new_method_root.append(method_tree.getroot())

        else:
            raise ValueError(f"Unknown method: {method_name}")

    # Create a new XML tree and return it
    new_method_tree = ET.ElementTree(new_method_root)
    ET.indent(new_method_root)
    return new_method_tree


def get_config() -> dict:
    """
    Load the configuration from the config.json file.

    Returns:
        dict: The configuration dictionary.
    """
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """
    Save the configuration to the config.json file.

    Args:
        config (dict): The configuration dictionary to save.
    """
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def setProcessDpiAwareness() -> None:
    """
    Set the DPI awareness for the application to ensure proper scaling on high-DPI displays.
    """
    if os.name == "nt":
        ProcessDpiAwarenessSet = False
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            ProcessDpiAwarenessSet = True
        except Exception as _:
            pass
        if not ProcessDpiAwarenessSet:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception as _:
                pass


def getScalingFactor() -> float:
    """
    Get the scaling factor for the application based on the current DPI settings.

    Returns:
        float: The scaling factor.
    """
    scaleFactor = 1.0
    if os.name == "nt":
        try:
            scaleFactor = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        except Exception as _:
            pass
    return scaleFactor
