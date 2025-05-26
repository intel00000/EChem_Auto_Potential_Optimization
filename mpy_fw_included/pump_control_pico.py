import os
import sys
import json
import select
import machine
from bootloader_util import set_bootloader_mode

# a dictionary to store the pumps, the key is the pump number and the value is the pump instance
rtc = machine.RTC()
pumps = {}
config = {}
version = "1.00"
SAVE_FILE = "pumps_config.json"
CONFIG_FILE = "pump_control_config.json"


# generic function to write a message to the console
def write_message(message):
    sys.stdout.write(f"{message}\n")


# Each pump class will have a power and direction Pin, defined at initialization
class Pump:
    def __init__(
        self,
        power_pin_id,
        direction_pin_id,
        initial_power_pin_value=0,
        initial_direction_pin_value=0,
        initial_power_status="OFF",
        initial_direction_status="CCW",
    ):
        # both pins are set to low to prevent current flow
        self.power_pin = machine.Pin(
            power_pin_id,
            machine.Pin.OUT,
            value=initial_power_pin_value,
            pull=machine.Pin.PULL_DOWN,
        )
        self.direction_pin = machine.Pin(
            direction_pin_id,
            machine.Pin.OUT,
            value=initial_direction_pin_value,
            pull=machine.Pin.PULL_DOWN,
        )

        self.power_pin_id = power_pin_id
        self.direction_pin_id = direction_pin_id
        self.initial_power_pin_value = initial_power_pin_value
        self.initial_direction_pin_value = initial_direction_pin_value

        self.initial_power_status = initial_power_status.upper()
        self.power_status = self.initial_power_status
        self.initial_direction_status = initial_direction_status.upper()
        self.direction_status = self.initial_direction_status

    def toggle_power(self):
        # flip the power Pin value and update the power status
        self.power_pin.value(not self.power_pin.value())
        # update the power status
        if self.power_status == "ON":
            self.power_status = "OFF"
        else:
            self.power_status = "ON"

    def set_power(self, status: str):
        status = status.upper()
        if status not in ["ON", "OFF"]:
            write_message("Error: Invalid power status, expected 'ON' or 'OFF'")
            return
        if status == self.initial_power_status:
            self.power_pin.value(self.initial_power_pin_value)
        else:
            self.power_pin.value(not self.initial_power_pin_value)
        self.power_status = status

    def toggle_direction(self):
        self.direction_pin.value(not self.direction_pin.value())
        if self.direction_status == "CW":
            self.direction_status = "CCW"
        else:
            self.direction_status = "CW"

    def set_direction(self, direction: str):
        direction = direction.upper()
        if direction not in ["CW", "CCW"]:
            write_message("Error: Invalid direction status, expected 'CW' or 'CCW'")
            return
        if direction == self.initial_direction_status:
            self.direction_pin.value(self.initial_direction_pin_value)
        else:
            self.direction_pin.value(not self.initial_direction_pin_value)
        self.direction_status = direction

    def hard_reset(self):
        write_message("Info: Performing hard reset.")
        machine.reset()

    # function to perform shutdown
    def shutdown(self):
        self.set_power("OFF")

    def get_status(self):
        return f"Power: {self.power_status}, Direction: {self.direction_status}"

    def get_info(self):
        return f"Power Pin: {self.power_pin_id}, Direction Pin: {self.direction_pin_id}, Initial Power Pin Value: {self.initial_power_pin_value}, Initial Direction Pin Value: {self.initial_direction_pin_value}, Current Power Status: {self.power_status}, Current Direction Status: {self.direction_status}"

    def to_dict(self):
        return {
            "power_pin_id": self.power_pin_id,
            "direction_pin_id": self.direction_pin_id,
            "initial_power_pin_value": self.power_pin.value(),
            "initial_direction_pin_value": self.direction_pin.value(),
            "power_status": self.power_status,
            "direction_status": self.direction_status,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            power_pin_id=data["power_pin_id"],
            direction_pin_id=data["direction_pin_id"],
            initial_power_pin_value=data["initial_power_pin_value"],
            initial_direction_pin_value=data["initial_direction_pin_value"],
            initial_power_status=data["power_status"],
            initial_direction_status=data["direction_status"],
        )


# functions to assemble and send status, when pump_name is 0, it will send status/info for all pumps
def pump_status(pump_name=0):
    global pumps
    if pump_name == 0:
        status = ", ".join(
            [f"Pump{i} Status: {pump.get_status()}" for i, pump in pumps.items()]
        )
        write_message(status)
    elif pump_name in pumps:
        write_message(f"Pump{pump_name} Status: {pumps[pump_name].get_status()}")


# functions to assemble and send info, when pump_name is 0, it will send status/info for all pumps
def pump_info(pump_name=0):
    global pumps
    if pump_name == 0:
        info = ", ".join(
            [f"Pump{i} Info: {pump.get_info()}" for i, pump in pumps.items()]
        )
        write_message(info)
    elif pump_name in pumps:
        write_message(f"Pump{pump_name} Info: {pumps[pump_name].get_info()}")


# function to register a pump, if the pump already exists, it will update the pins
def register_pump(
    pump_num,
    power_pin,
    direction_pin,
    initial_power_pin_value=0,
    initial_direction_pin_value=0,
    initial_power_status="OFF",
    initial_direction_status="CCW",
):
    global pumps
    # if the pump_num is 0, it will not be registered
    if pump_num == 0:
        write_message("Error: Pump number 0 is reserved for all pumps.")
        return
    try:
        if pump_num in pumps:
            # try to reinitialize the pins
            pumps[pump_num].power_pin = machine.Pin(
                power_pin, machine.Pin.OUT, value=initial_power_pin_value
            )
            pumps[pump_num].direction_pin = machine.Pin(
                direction_pin, machine.Pin.OUT, value=initial_direction_pin_value
            )

            pumps[pump_num].power_pin_id = power_pin
            pumps[pump_num].direction_pin_id = direction_pin
            pumps[pump_num].initial_power_pin_value = initial_power_pin_value
            pumps[pump_num].initial_direction_pin_value = initial_direction_pin_value
            pumps[pump_num].power_status = initial_power_status
            pumps[pump_num].direction_status = initial_direction_status
            write_message(f"Success: Pump {pump_num} updated.")
        else:
            pumps[pump_num] = Pump(
                power_pin,
                direction_pin,
                initial_power_pin_value,
                initial_direction_pin_value,
                initial_power_status,
                initial_direction_status,
            )
            write_message(f"Success: Pump {pump_num} registered.")
    except Exception as e:
        write_message(f"Error: registering pump {pump_num} failed, {e}")


# function to reset the controller, it will remove all pumps
def clear_pumps(pump_num=0):
    global pumps
    if pump_num == 0:
        pumps.clear()
        write_message("Success: All pumps removed.")
    elif pump_num in pumps:
        # remove the pump from the dictionary
        pumps.pop(pump_num)
        write_message(f"Success: Pump {pump_num} removed.")


# function to perform global shutdown, it will turn off all pumps
def global_shutdown():
    global pumps
    for pump in pumps.values():
        try:
            pump.shutdown()
        except Exception as e:
            write_message(f"Error: Could not shutdown pump {pump}, {e}")
    write_message("Info: Shutdown complete, all pumps are off.")


# function to return the version of the script
def ping():
    global version
    write_message(f"Ping: Pico Pump Control Version {version}")


# function to save the current state of the pumps to a JSON file
def save_pumps(pump_num=0):
    global pumps, SAVE_FILE
    try:
        if pump_num == 0:
            # Overwrite the file completely when saving all pumps
            data = {str(num): pump.to_dict() for num, pump in pumps.items()}
            with open(SAVE_FILE, "w") as file:
                json.dump(data, file)
            write_message(f"Success: All pumps saved to {SAVE_FILE}.")
        else:
            # Save a specific pump, check if it's new or existing
            pump_data = {str(pump_num): pumps[pump_num].to_dict()}
            files = os.listdir(os.getcwd())

            if SAVE_FILE in files:
                with open(SAVE_FILE, "r") as file:
                    existing_data = json.load(file)
            else:
                existing_data = {}

            # Update the entire file
            existing_data.update(pump_data)
            with open(SAVE_FILE, "w") as file:
                json.dump(existing_data, file)

            write_message(f"Success: Pump {pump_num} saved to {SAVE_FILE}.")
    except Exception as e:
        write_message(f"Error: Could not save pumps, {e}")


# function to load the pumps state from a JSON file
def load_pumps():
    global pumps, SAVE_FILE
    try:
        # Check if the file exists using os.listdir() and os.getcwd()
        files = os.listdir(os.getcwd())
        if SAVE_FILE in files:
            with open(SAVE_FILE, "r") as file:
                data = json.load(file)
                for key, value in data.items():
                    pumps[int(key)] = Pump.from_dict(value)
        else:
            write_message(
                f"Info: No save file found ({SAVE_FILE}). Starting with default pumps."
            )
            pumps[1] = Pump(
                power_pin_id=0,
                direction_pin_id=1,
                initial_power_pin_value=0,
                initial_direction_pin_value=0,
                initial_power_status="OFF",
                initial_direction_status="CCW",
            )
            save_pumps(1)  # Save the default pump to the file
    except Exception as e:
        write_message(f"Error: Could not load pumps, {e}")


# function to load the configuration from a JSON file
def load_config():
    global config, CONFIG_FILE
    try:
        # Check if the file exists using os.listdir() and os.getcwd()
        files = os.listdir(os.getcwd())
        if CONFIG_FILE in files:
            with open(CONFIG_FILE, "r") as file:
                data = json.load(file)
                config = data
                # set the RTC time to the config time
                rtc.datetime(
                    (
                        config["year"],
                        config["month"],
                        config["day"],
                        0,
                        config["hour"],
                        config["minute"],
                        config["second"],
                        0,
                    )
                )
        else:
            config = {
                "name": "Not Set",
                "year": 2025,
                "month": 1,
                "day": 1,
                "hour": 0,
                "minute": 0,
                "second": 0,
            }
            save_config()
            write_message(
                f"Info: No config file found ({CONFIG_FILE}). Starting with default config."
            )
    except Exception as e:
        write_message(f"Error: Could not load config, {e}")


# function to save the current configuration to a JSON file
def save_config():
    global config, CONFIG_FILE
    try:
        with open(CONFIG_FILE, "w") as file:
            year, month, day, _, hour, minute, second, _ = rtc.datetime()
            config["year"] = year
            config["month"] = month
            config["day"] = day
            config["hour"] = hour
            config["minute"] = minute
            config["second"] = second
            json.dump(config, file)
        write_message("Info: Config saved.")
    except Exception as e:
        write_message(f"Error: Could not save config, {e}")


# function to get the current RTC time
def get_time():
    try:
        year, month, day, _, hour, minute, second, _ = rtc.datetime()
        write_message(f"RTC Time: {year}-{month}-{day} {hour}:{minute}:{second}")
    except Exception as e:
        write_message(f"Error: Could not get RTC time, {e}")


# function to set the RTC time
def set_time(year, month, day, hour, minute, second):
    try:
        rtc.datetime((year, month, day, 0, hour, minute, second, 0))
        save_config()
        write_message(
            f"Info: RTC Time set to {year}-{month}-{day} {hour}:{minute}:{second}"
        )
    except Exception as e:
        write_message(f"Error: Could not set RTC time, {e}")


def get_name():
    try:
        name = config.get("name", "Not Set")
        write_message(f"Name: {name}")
    except Exception as e:
        write_message(f"Error: Could not get name, {e}")


def set_name(name):
    try:
        config["name"] = name
        save_config()
        write_message(f"Success: Name set to {name}")
    except Exception as e:
        write_message(f"Error: Could not set name, {e}")


# Define a dictionary for pump specific commands
commands = {
    "toggle_power": "toggle_power",
    "set_power": "set_power",
    "toggle_direction": "toggle_direction",
    "set_direction": "set_direction",
    "reset": "hard_reset",
}


def help(simple=True):
    # assemble commands help text
    help_text_simple = (
        "Info: General format for commands:\n"
        "  - [pump_number]:[command]:[additional_parameters]\n"
    )
    help_text = (
        "Available commands:\n"
        "  - ping: Check if the controller is responsive.\n"
        "  - reg: Register a pump with the specified parameters.\n"
        "  - time: Get the current RTC time.\n"
        "  - stime: Set the RTC time in the format 'year:month:day:hour:minute:second'.\n"
        "  - set_mode: Set the bootloader mode.\n"
        "  - bootsel: Enter BOOTSEL mode for firmware updates.\n"
        "  - blink_en: Enable LED blinking mode.\n"
        "  - blink_dis: Disable LED blinking mode.\n"
        "  - get_name: Get the current name of the controller.\n"
        "  - set_name:name: Set the name of the controller.\n"
        "  - status: Get the status of a specific pump or all pumps (pump_number:0 for all).\n"
        "  - info: Get the info of a specific pump or all pumps (pump_number:0 for all).\n"
        "  - clear_pumps: Clear all pumps or a specific pump (pump_number:0 for all).\n"
        "  - save_pumps: Save the current state of all pumps or a specific pump (pump_number:0 for all).\n"
        "  - shutdown: Shutdown all pumps or a specific pump (pump_number:0 for all).\n"
        "  - toggle_power: Toggle the power of a specific pump.\n"
        "  - set_power: Set the power of a specific pump to 'ON' or 'OFF'.\n"
        "  - toggle_direction: Toggle the direction of a specific pump.\n"
        "  - set_direction: Set the direction of a specific pump to 'CW' or 'CCW'.\n"
        "  - reset: Perform a hard reset of the controller.\n"
        "  - help: Show this help message.\n"
        "Example usage:\n"
        "  - To register a pump: '1:reg:2:3:1:0:ON:CW'\n"
        "    (pump_number:1, power_pin:2, direction_pin:3, initial_power_pin_value:1, initial_direction_pin_value:0, initial_power_status:ON, initial_direction_status:CW)\n"
        "Note:\n"
        "  - global commands for pump 0: 'status', 'info', 'clear_pumps', 'save_pumps', 'shutdown'.\n"
        "  - pump specific commands for pump 0: 'toggle_power', 'set_power', 'toggle_direction', 'set_direction', 'reset'.\n"
    )
    if simple:
        write_message(help_text_simple)
    else:
        write_message(help_text_simple + help_text)


# Create a poll object to monitor stdin, which will block until there is input for reading
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)


def main():
    led = machine.Pin("LED", machine.Pin.OUT, value=1)  # Initialize the LED Pin

    def blink_led():
        led.toggle()

    timer = machine.Timer()  # Timer for blinking the LED
    led_blinking_mode = False

    # assemble a mapping from key to value in the commands dictionary
    commands_mapping_string = ", ".join(
        [f"'{key}': '{value}'" for key, value in commands.items()]
    )

    load_config()
    load_pumps()
    while True:
        try:
            if not led_blinking_mode:
                led.value(1)
            # Wait for input on stdin
            poll_results = poll_obj.poll()

            if poll_results:
                # Read the data from stdin (PC console input) and strip the newline character
                data = sys.stdin.readline().strip()
                if not led_blinking_mode:
                    led.value(0)

                # Validate the input data
                if not data or data == "":
                    write_message("Error: Empty input.")
                    continue
                parts = data.split(":")  # Split the data into pump id and command
                if parts[0].isdigit():
                    pump_num = int(parts[0])
                    command = parts[1].strip().lower()
                else:
                    pump_num = 0
                    command = parts[0].strip().lower()
                    # insert a 0 to the first position of parts
                    parts.insert(0, "0")

                # check the input and call the appropriate function
                try:
                    # general global commands
                    if command == "help":
                        help(simple=False)
                    elif command == "ping":
                        ping()
                    elif command == "reg":
                        if len(parts) == 8:
                            power_pin = int(parts[2])
                            direction_pin = int(parts[3])
                            initial_power_pin_value = int(parts[4])
                            initial_direction_pin_value = int(parts[5])
                            # check if the initial power status is valid
                            if parts[6].upper() not in ["ON", "OFF"]:
                                write_message(
                                    "Error: Invalid initial power status, expected 'ON' or 'OFF'"
                                )
                                continue
                            initial_power = parts[6]
                            # check if the initial direction status is valid
                            if parts[7].upper() not in ["CW", "CCW"]:
                                write_message(
                                    "Error: Invalid initial direction status, expected 'CW' or 'CCW'"
                                )
                                continue
                            initial_direction = parts[7]

                            register_pump(
                                pump_num,
                                power_pin,
                                direction_pin,
                                initial_power_pin_value,
                                initial_direction_pin_value,
                                initial_power,
                                initial_direction,
                            )
                        else:
                            write_message(
                                "Error: Invalid input, expected format 'pump_number:reg:power_pin:direction_pin:initial_power_pin_value:initial_direction_pin_value:initial_power_status:initial_direction_status'"
                            )
                    elif command == "time":
                        # Get current RTC time
                        get_time()
                    elif command == "stime":
                        if len(parts) == 8:  # Adjusted length
                            year = int(parts[2])
                            month = int(parts[3])
                            day = int(parts[4])
                            hour = int(parts[5])
                            minute = int(parts[6])
                            second = int(parts[7])
                            set_time(year, month, day, hour, minute, second)
                        else:
                            write_message(
                                "Error: Invalid input, expected format '0:stime:year:month:day:day_of_week:hour:minute:second'"
                            )
                    elif command == "set_mode":
                        if len(parts) >= 3:
                            mode = str(parts[2])
                        else:
                            mode = "None"
                        try:
                            set_bootloader_mode(mode)
                            write_message(f"Success: bootloader set to {mode} mode")
                        except Exception as e:
                            write_message(f"Error: {e}")
                    elif command == "bootsel":
                        try:
                            write_message("Success: Entering BOOTSEL mode")
                            machine.bootloader()
                        except Exception as e:
                            write_message(f"Error: {e}")
                    elif command == "blink_en":
                        if not led_blinking_mode:
                            led_blinking_mode = True
                            timer.init(
                                period=200,
                                mode=machine.Timer.PERIODIC,
                                callback=lambda t: blink_led(),
                            )
                            write_message("Info: LED blinking mode enabled.")
                        else:
                            write_message("Info: LED blinking mode is already enabled.")
                    elif command == "blink_dis":
                        if led_blinking_mode:
                            led_blinking_mode = False
                            timer.deinit()
                            led.value(1)
                            write_message("Info: LED blinking mode disabled.")
                    elif command == "get_name":
                        get_name()
                    elif command == "set_name":
                        if len(parts) == 3:
                            name = parts[2].strip()
                            set_name(name)
                        else:
                            write_message(
                                "Error: Invalid input, expected format '0:set_name:name'"
                            )
                    # start of global commands for pumps
                    elif command == "status":
                        pump_status(pump_num)
                    elif command == "info":
                        pump_info(pump_num)
                    elif command == "clear_pumps":
                        clear_pumps(pump_num)
                    elif command == "save_pumps":
                        save_pumps(pump_num)
                    # start of pump specific commands
                    elif pump_num == 0:
                        if command == "shutdown":
                            global_shutdown()
                        elif command in commands:
                            for pump in pumps.values():
                                method = getattr(pump, commands[command], None)
                                if method:
                                    if len(parts) > 2:
                                        method(*parts[2:])
                                    else:
                                        method()
                        else:
                            write_message(
                                f"Error: Invalid command for pump '0' '{command}', available commands are: "
                                + commands_mapping_string
                            )
                    elif pump_num in pumps:
                        pump = pumps[pump_num]  # get the pump instance
                        if command in commands:  # check if the command is valid
                            method = getattr(pump, commands[command], None)
                            if method:
                                if len(parts) > 2:
                                    method(*parts[2:])
                                else:
                                    method()
                            else:
                                write_message(
                                    f"Error: Invalid instance specific command '{command}'"
                                )
                        else:
                            write_message(
                                f"Error: Invalid global command for pump '{pump_num}', available commands are: "
                                + commands_mapping_string
                            )
                    else:
                        write_message(
                            f"Error: Invalid pump number '{pump_num}', available pumps are: "
                            + ", ".join(map(str, pumps.keys()))
                        )
                except Exception as cmd_error:
                    write_message(f"Error: {cmd_error}")
        except Exception as e:
            global_shutdown()
            write_message(f"Error: {e}")
            write_message("Error: critical error, perform shutdown.")


# Run the main loop
if __name__ == "__main__":
    main()
