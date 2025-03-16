import os
import gc
import sys
import json
import time
import array
import select
import pwm_dma_fade_onetime
from neopixel import NeoPixel
from uctypes import addressof
from machine import Pin, reset, RTC
from bootloader_util import set_bootloader_mode

# a dictionary to store the pumps, the key is the pump number and the value is the pump instance
rtc = RTC()
pumps = {}
version = "0.01"
SAVE_FILE = "pumps_config.json"


# Each pump class will have a power and direction pin, defined at initialization
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
        self.power_pin = Pin(
            power_pin_id, Pin.OUT, value=initial_power_pin_value, pull=Pin.PULL_DOWN
        )
        self.direction_pin = Pin(
            direction_pin_id,
            Pin.OUT,
            value=initial_direction_pin_value,
            pull=Pin.PULL_DOWN,
        )

        self.power_pin_id = power_pin_id
        self.direction_pin_id = direction_pin_id
        self.initial_power_pin_value = initial_power_pin_value
        self.initial_direction_pin_value = initial_direction_pin_value

        self.power_status = initial_power_status
        self.direction_status = initial_direction_status

    def toggle_power(self):
        # flip the power pin value and update the power status
        self.power_pin.value(not self.power_pin.value())
        # update the power status
        if self.power_status == "ON":
            self.power_status = "OFF"
        else:
            self.power_status = "ON"

    def toggle_direction(self):
        self.direction_pin.value(not self.direction_pin.value())
        if self.direction_status == "CW":
            self.direction_status = "CCW"
        else:
            self.direction_status = "CW"

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
def send_status(pump_name):
    global pumps
    if pump_name == 0:
        status = ", ".join(
            [f"Pump{i} Status: {pump.get_status()}" for i, pump in pumps.items()]
        )
        free_mem = gc.mem_free()
        total_mem = gc.mem_alloc() + gc.mem_free()
        status += f", Heap status (free/total): {free_mem}/{total_mem} bytes"
        sys.stdout.write(f"{status}\n")
    elif pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Status: {pumps[pump_name].get_status()}\n")


# functions to assemble and send info, when pump_name is 0, it will send status/info for all pumps
def send_info(pump_name):
    global pumps
    if pump_name == 0:
        info = ", ".join(
            [f"Pump{i} Info: {pump.get_info()}" for i, pump in pumps.items()]
        )
        free_mem = gc.mem_free()
        total_mem = gc.mem_alloc() + gc.mem_free()
        info += f", Heap status (free/total): {free_mem}/{total_mem} bytes"
        sys.stdout.write(f"{info}\n")
    elif pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Info: {pumps[pump_name].get_info()}\n")


# generic function to write a message to the console
def write_message(message):
    sys.stdout.write(f"{message}\n")


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
            pumps[pump_num].power_pin = Pin(
                power_pin, Pin.OUT, value=initial_power_pin_value
            )
            pumps[pump_num].direction_pin = Pin(
                direction_pin, Pin.OUT, value=initial_direction_pin_value
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
def clear_pumps(pump_num):
    global pumps
    if pump_num == 0:
        pumps.clear()
        write_message("Success: All pumps removed.")
    elif pump_num in pumps:
        # remove the pump from the dictionary
        pumps.pop(pump_num)
        write_message(f"Success: Pump {pump_num} removed.")


# function to perform an emergency shutdown
def emergency_shutdown():
    global pumps
    for _, pump in pumps.items():
        if pump.power_status != "OFF":
            pump.toggle_power()
    write_message("Success: Emergency Shutdown, all pumps are off.")


# function to return the version of the script
def ping():
    global version
    write_message(f"Ping: Pico Pump Control Version {version}")


# a function to reset the device, equivalent to a hard reset
def hard_reset():
    write_message("Success: Performing hard reset.")
    reset()


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
            write_message(f"Success: Loaded pump data from {SAVE_FILE}.")
        else:
            write_message(
                f"No save file found ({SAVE_FILE}). Starting with default pumps."
            )
    except Exception as e:
        write_message(f"Error: Could not load pumps, {e}")


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
    "pw": "toggle_power",
    "di": "toggle_direction",
    "st": "status",
    "info": "info",
    "reg": "register",
    "clr": "clear_pumps",
    "shutdown": "emergency_shutdown",
    "reset": "hard_reset",
    "ping": "ping",
    "save": "save_pumps",
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

    led_mode = -1
    try:  # first method, DMA fade, only avilable on regular Pico
        fade_buffer = array.array(
            "I",
            [(i * i) << 16 for i in range(0, 256, 1)],
        )
        secondary_config_data = bytearray(16)
        (dma_main, dma_secondary) = pwm_dma_fade_onetime.pwm_dma_led_fade(
            fade_buffer_addr=addressof(fade_buffer),
            fade_buffer_len=len(fade_buffer),
            secondary_config_data_addr=addressof(secondary_config_data),
            frequency=10240,
        )
        led_mode = 0
    except Exception as _:
        pass
    if led_mode == -1:  # second method is for the led with NeoPixel
        try:
            led = Pin("LED", Pin.OUT)
            np = NeoPixel(led, 1)
            # set to red
            np[0] = (0, 10, 0)
            np.write()
            led_mode = 1
        except Exception as _:
            pass
    if led_mode == -1:  # third method is for the led on single GPIO pin
        try:
            led = Pin("LED", Pin.OUT)
            led.value(1)
            led_mode = 2
        except Exception as _:
            pass

    # Load the pumps at startup
    load_pumps()
    while True:
        try:
            # Wait for input on stdin
            poll_results = poll_obj.poll()

            if poll_results:
                # Read the data from stdin (PC console input) and strip the newline character
                data = sys.stdin.readline().strip()
                if led_mode == 0:
                    dma_secondary.active(1)
                elif led_mode == 1:
                    np[0] = (0, 0, 0)
                    np.write()
                    time.sleep_ms(25)
                    np[0] = (0, 10, 0)
                    np.write()
                elif led_mode == 2:
                    led.value(0)
                    time.sleep_ms(25)
                    led.value(1)

                # Validate the input data
                if not data or data == "":
                    write_message("Error: Empty input.")
                    continue
                # Split the data into pump id and command
                parts = data.split(":")
                if len(parts) < 2:
                    write_message(
                        "Error: Invalid input, expected basic format 'pump_number:command...'"
                    )
                    continue
                pump_num = int(parts[0])
                command = parts[1].strip().lower()

                # check the input and call the appropriate function
                try:
                    if command == "reg":
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
                        if len(parts) == 3:
                            mode = str(parts[2])
                            try:
                                set_bootloader_mode(mode)
                                write_message(f"Success: bootloader set to {mode} mode")
                            except Exception as e:
                                write_message(f"Error: {e}")
                        else:
                            write_message(
                                "Error: Invalid input, expected format '0:set_mode:mode', mode can be either 'pump' or 'autosampler' or 'update_firmware'"
                            )
                    elif pump_num == 0:
                        if command == "st":
                            send_status(0)
                        elif command == "info":
                            send_info(0)
                        elif command == "clr":
                            clear_pumps(0)
                        elif command == "shutdown":
                            emergency_shutdown()
                        elif command == "save":
                            save_pumps()
                        elif command in commands:
                            if command == "ping":
                                ping()
                            elif command == "reset":
                                hard_reset()
                            else:
                                for pump in pumps.values():
                                    method = getattr(pump, commands[command], None)
                                    if method:
                                        method()
                        else:
                            write_message(
                                f"Error: Invalid command for pump '0' '{command}', available commands are: "
                                + commands_mapping_string
                            )

                    elif pump_num in pumps:
                        # get the pump instance
                        pump = pumps[pump_num]

                        # check if the command is valid
                        if command in commands:
                            if command == "st":
                                send_status(pump_num)
                            elif command == "info":
                                send_info(pump_num)
                            elif command == "clr":
                                clear_pumps(pump_num)
                            elif command == "save":
                                save_pumps(pump_num)
                            else:
                                method = getattr(pump, commands[command], None)
                                if method:
                                    method()
                                else:
                                    write_message(
                                        f"Error: No corresponding method for command '{command}'"
                                    )
                        else:
                            write_message(
                                f"Error: Invalid command for pump '{pump_num}', available commands are: "
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
            emergency_shutdown()
            write_message(f"Error: {e}")
            write_message("Error: critical error, emergency shutdown.")


# Run the main loop
if __name__ == "__main__":
    main()
