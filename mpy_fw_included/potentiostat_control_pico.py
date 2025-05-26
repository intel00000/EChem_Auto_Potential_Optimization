import os
import sys
import json
import select
import machine
from bootloader_util import set_bootloader_mode

# a dictionary to store the potentiostat config
rtc = machine.RTC()
potentiostats = {}
version = "0.01"
SAVE_FILE = "potentiostat_config.json"
CONFIG_FILE = "potentiostat_control_config.json"


# generic function to write a message to the console
def write_message(message):
    sys.stdout.write(f"{message}\n")


# Each Potentiostat class will have only a trigger pin
class Potentiostat:
    def __init__(
        self,
        trigger_pin_id,
        initial_trigger_pin_value=0,
        initial_trigger_status="LOW",
    ):
        self.trigger_pin = machine.Pin(
            trigger_pin_id,
            machine.Pin.OUT,
            value=initial_trigger_pin_value,
            pull=machine.Pin.PULL_DOWN,
        )
        self.trigger_pin_id = trigger_pin_id
        self.initial_trigger_pin_value = initial_trigger_pin_value
        self.trigger_status = initial_trigger_status

    def toggle_trigger(self):
        # flip the trigger pin value and update the trigger status
        self.trigger_pin.value(not self.trigger_pin.value())
        # update the trigger status
        if self.trigger_status == "LOW":
            self.trigger_status = "HIGH"
        else:
            self.trigger_status = "LOW"

    def get_status(self):
        return f"Trigger: {self.trigger_status}"

    def get_info(self):
        return f"Trigger Pin: {self.trigger_pin_id}, Initial Trigger Pin Value: {self.initial_trigger_pin_value}, Current Trigger Status: {self.trigger_status}"

    def to_dict(self):
        return {
            "trigger_pin_id": self.trigger_pin_id,
            "initial_trigger_pin_value": self.trigger_pin.value(),
            "trigger_status": self.trigger_status,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["trigger_pin_id"],
            data["initial_trigger_pin_value"],
            data["trigger_status"],
        )


# functions to assemble and send status, when potentiostat_name is 0, it will send status/info for all potentiostats
def send_status(potentiostat_name):
    global potentiostats
    if potentiostat_name == 0:
        status = ", ".join(
            [
                f"Potentiostat{i} Status: {potentiostat.get_status()}"
                for i, potentiostat in potentiostats.items()
            ]
        )
        write_message(status)
    elif potentiostat_name in potentiostats:
        write_message(
            f"Potentiostat{potentiostat_name} Status: {potentiostats[potentiostat_name].get_status()}"
        )


# functions to assemble and send info, when potentiostat_name is 0, it will send status/info for all potentiostats
def send_info(potentiostat_name):
    global potentiostats
    if potentiostat_name == 0:
        info = ", ".join(
            [
                f"Potentiostat{i} Info: {potentiostat.get_info()}"
                for i, potentiostat in potentiostats.items()
            ]
        )
        write_message(info)
    elif potentiostat_name in potentiostats:
        write_message(
            f"Potentiostat{potentiostat_name} Info: {potentiostats[potentiostat_name].get_info()}"
        )


# function to register a potentiostat, if a potentiostat already exists, it will update the pins
def register_potentiostat(
    potentiostat_num,
    trigger_pin_id,
    initial_trigger_pin_value=0,
    initial_trigger_status="LOW",
):
    global potentiostats
    # if the potentiostat_num is 0, it will not be registered
    if potentiostat_num == 0:
        write_message("Error: potentiostat number 0 is reserved for all potentiostats.")
        return
    try:
        if potentiostat_num in potentiostats:
            # try to reinitialize the pins
            potentiostats[potentiostat_num].trigger_pin = machine.Pin(
                trigger_pin_id,
                machine.Pin.OUT,
                value=initial_trigger_pin_value,
                pull=machine.Pin.PULL_DOWN,
            )
            potentiostats[potentiostat_num].trigger_pin_id = trigger_pin_id
            potentiostats[
                potentiostat_num
            ].initial_trigger_pin_value = initial_trigger_pin_value
            potentiostats[potentiostat_num].trigger_status = initial_trigger_status
            write_message(f"Success: potentiostat {potentiostat_num} updated.")
        else:
            potentiostats[potentiostat_num] = Potentiostat(
                trigger_pin_id,
                initial_trigger_pin_value,
                initial_trigger_status,
            )
            write_message(f"Success: potentiostat {potentiostat_num} registered.")
    except Exception as e:
        write_message(f"Error: registering potentiostat {potentiostat_num} failed, {e}")


# function to reset the controller, it will remove all potentiostats
def clear_potentiostats(potentiostat_num):
    global potentiostats
    if potentiostat_num == 0:
        potentiostats.clear()
        write_message("Success: All potentiostats removed.")
    elif potentiostat_num in potentiostats:
        # remove the potentiostat from the dictionary
        potentiostats.pop(potentiostat_num)
        write_message(f"Success: potentiostat {potentiostat_num} removed.")


# function to perform an shutdown
def shutdown():
    global potentiostats
    for _, potentiostat in potentiostats.items():
        if potentiostat.trigger_status != "LOW":
            potentiostat.toggle_trigger()
    write_message("Success: Emergency Shutdown, all potentiostats are set to LOW.")


# function to return the version of the script
def ping():
    global version
    write_message(f"Ping: Pico Potentiostats Control Version {version}")


# a function to reset the device, equivalent to a hard reset
def hard_reset():
    write_message("Success: Performing hard reset.")
    machine.reset()


# function to save the current state of the potentiostats to a JSON file
def save_potentiostats(potentiostat_num=0):
    global potentiostats, SAVE_FILE
    try:
        if potentiostat_num == 0:
            # Overwrite the file completely when saving all potentiostats
            data = {
                str(num): potentiostat.to_dict()
                for num, potentiostat in potentiostats.items()
            }
            with open(SAVE_FILE, "w") as file:
                json.dump(data, file)
            write_message(f"Success: All potentiostats saved to {SAVE_FILE}.")
        else:
            # Save a specific potentiostat, check if it's new or existing
            potentiostat_data = {
                str(potentiostat_num): potentiostats[potentiostat_num].to_dict()
            }
            files = os.listdir(os.getcwd())
            if SAVE_FILE in files:
                with open(SAVE_FILE, "r") as file:
                    existing_data = json.load(file)
            else:
                existing_data = {}

            # Update the entire file
            existing_data.update(potentiostat_data)
            with open(SAVE_FILE, "w") as file:
                json.dump(existing_data, file)

            write_message(
                f"Success: Potentiostat {potentiostat_num} saved to {SAVE_FILE}."
            )
    except Exception as e:
        write_message(f"Error: Could not save potentiostats, {e}")


# function to load the potentiostats state from a JSON file
def load_potentiostats():
    global potentiostats, SAVE_FILE
    try:
        # Check if the file exists using os.listdir() and os.getcwd()
        files = os.listdir(os.getcwd())
        if SAVE_FILE in files:
            with open(SAVE_FILE, "r") as file:
                data = json.load(file)
                for key, value in data.items():
                    potentiostats[int(key)] = Potentiostat.from_dict(value)
            write_message(f"Success: Loaded potentiostats data from {SAVE_FILE}.")
        else:
            write_message(
                f"No save file found ({SAVE_FILE}). Starting with default potentiostats."
            )
            potentiostats[1] = Potentiostat(
                trigger_pin_id=0,
                initial_trigger_pin_value=0,
                initial_trigger_status="LOW",
            )
            save_potentiostats(1)
    except Exception as e:
        write_message(f"Error: Could not load potentiostats, {e}")


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
        write_message(
            f"Success: RTC Time set to {year}-{month}-{day} {hour}:{minute}:{second}"
        )
    except Exception as e:
        write_message(f"Error: Could not set RTC time, {e}")


# Define a dictionary for the commands
commands = {
    "tr": "toggle_trigger",
    "st": "status",
    "info": "info",
    "reg": "register",
    "clr": "clear_potentiostats",
    "shutdown": "shutdown",
    "reset": "hard_reset",
    "ping": "ping",
    "save": "save_potentiostats",
    "time": "get_time",
    "stime": "set_time",
    "set_mode": "set_bootloader_mode",
}

# Create a poll object to monitor stdin, which will block until there is input for reading
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)


def main():
    # assemble a mapping from key to value in the commands dictionary
    commands_mapping_string = ", ".join(
        [f"'{key}': '{value}'" for key, value in commands.items()]
    )

    led = machine.Pin("LED", machine.Pin.OUT, value=1)  # Initialize the LED machine.Pin

    def blink_led():
        led.toggle()

    timer = machine.Timer()  # Timer for blinking the LED
    led_blinking_mode = False

    # Load the potentiostats at startup
    load_potentiostats()
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
                    potentiostat_num = int(parts[0])
                    command = parts[1].strip().lower()
                else:
                    potentiostat_num = 0
                    command = parts[0].strip().lower()
                    # insert a 0 to the first position of parts
                    parts.insert(0, "0")

                # check the input and call the appropriate function
                try:
                    if command == "ping":
                        ping()
                    elif command == "reg":
                        if len(parts) == 5:
                            trigger_pin_id = int(parts[2])
                            initial_trigger_pin_value = int(parts[3])
                            # check if the initial power status is valid
                            if parts[4].upper() not in ["LOW", "HIGH"]:
                                write_message(
                                    "Error: Invalid initial trigger status, expected 'LOW' or 'HIGH'"
                                )
                                continue
                            initial_trigger = parts[4].upper()

                            register_potentiostat(
                                potentiostat_num,
                                trigger_pin_id,
                                initial_trigger_pin_value,
                                initial_trigger,
                            )
                        else:
                            write_message(
                                "Error: Invalid input, expected format 'potentiostat_number:reg:trigger_pin_id:initial_trigger_pin_value:initial_trigger_status'"
                            )
                    elif command == "time":
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
                    elif potentiostat_num == 0:
                        if command == "st":
                            send_status(0)
                        elif command == "info":
                            send_info(0)
                        elif command == "clr":
                            clear_potentiostats(0)
                        elif command == "shutdown":
                            shutdown()
                        elif command == "save":
                            save_potentiostats()
                        elif command in commands:
                            if command == "ping":
                                ping()
                            elif command == "reset":
                                hard_reset()
                            else:
                                for potentiostat in potentiostats.values():
                                    method = getattr(
                                        potentiostat, commands[command], None
                                    )
                                    if method:
                                        method()
                        else:
                            write_message(
                                f"Error: Invalid command for potentiostat '0' '{command}', available commands are: "
                                + commands_mapping_string
                            )

                    elif potentiostat_num in potentiostats:
                        # get the pump instance
                        potentiostat = potentiostats[potentiostat_num]

                        # check if the command is valid
                        if command in commands:
                            if command == "st":
                                send_status(potentiostat_num)
                            elif command == "info":
                                send_info(potentiostat_num)
                            elif command == "clr":
                                clear_potentiostats(potentiostat_num)
                            elif command == "save":
                                save_potentiostats(potentiostat_num)
                            else:
                                method = getattr(potentiostat, commands[command], None)
                                if method:
                                    method()
                                else:
                                    write_message(
                                        f"Error: No corresponding method for command '{command}'"
                                    )
                        else:
                            write_message(
                                f"Error: Invalid command for potentiostat '{potentiostat_num}', available commands are: "
                                + commands_mapping_string
                            )
                    else:
                        write_message(
                            f"Error: Invalid potentiostat number '{potentiostat_num}', available pumps are: "
                            + ", ".join(map(str, potentiostats.keys()))
                        )
                except Exception as cmd_error:
                    write_message(f"Error: {cmd_error}")
        except Exception as e:
            shutdown()
            write_message(f"Error: {e}")
            write_message("Error: critical error, emergency shutdown.")


# Run the main loop
if __name__ == "__main__":
    main()
