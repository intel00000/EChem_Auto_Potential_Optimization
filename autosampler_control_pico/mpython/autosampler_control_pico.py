import sys
import time
import json
import array
import select
import machine
import pwm_dma_fade_onetime
from uctypes import addressof
from neopixel import NeoPixel
from bootloader_util import set_bootloader_mode

# this is a program to control a stepper motor
MAX_POSITION = 16000
CONFIG_FILE = "autosampler_config.json"
STATUS_FILE = "autosampler_status.txt"
PULSE_PIN = 12
DIRECTION_PIN = 14
ENABLE_PIN = 15


class Autosampler:
    def __init__(self, pulse_pin, direction_pin, enable_pin):
        # Initialize pins
        self.pulse = machine.Pin(
            pulse_pin, machine.Pin.OUT, machine.Pin.PULL_UP, value=0
        )
        self.direction = machine.Pin(
            direction_pin, machine.Pin.OUT, machine.Pin.PULL_UP, value=0
        )
        self.enable = machine.Pin(
            enable_pin, machine.Pin.OUT, machine.Pin.PULL_UP, value=1
        )

        # Initialize autosampler state
        # current position of the autosampler, current_position = 0 is the rightmost position
        self.current_position = -1
        # fail safe position of the autosampler
        self.fail_safe_position = 0

        # direction value 1 is to the left, 0 is to the right, default is to the left
        self.current_direction = 1
        # direction value 1 is to the left, 0 is to the right, current_position = 0 is the rightmost position
        self.direction_map = {0: "Right", 1: "Left"}

        # the autosampler_config is a dictionary that stores a predefined set of positions for the autosampler
        self.autosampler_config = {}
        # power status of the autosampler
        self.is_power_on = False

        # time interval between steps in milliseconds
        self.time_interval_between_steps_ms = 5

        self.rtc = machine.RTC()  # RTC setup

        self.version = "0.01"  # version of the autosampler control program

        # Load configuration and status
        self.load_config()
        self.load_status()

    def write_message(self, message) -> None:
        sys.stdout.write(f"{message}\n")

    def send_status(self) -> None:
        status = f"Autosampler Status: position: {self.current_position}, direction: {self.direction_map[self.current_direction]}"
        self.write_message(f"{status}")

    def send_config(self) -> None:
        # assemble in json format
        self.write_message(
            f"Autosampler Configuration: {json.dumps(self.autosampler_config)}"
        )

    def ping(self) -> None:
        self.write_message(f"PING: Pico Autosampler Control Version {self.version}")

    def hard_reset(self) -> None:
        self.write_message("Success: Performing hard reset.")
        machine.reset()

    def save_status(self, write_message=True) -> None:
        try:
            with open(STATUS_FILE, "w") as f:
                output = f"{self.current_position}, {self.current_direction}, {self.direction_map[self.current_direction]}"
                f.write(output)
        except Exception as e:
            self.write_message(f"Error: Could not save status, {e}")

    def load_status(self) -> None:
        try:
            with open(STATUS_FILE, "r") as f:
                first_line = f.readline().strip().split(",")
                self.current_position = int(first_line[0])
                self.current_direction = int(first_line[1])
            self.write_message(
                f"Success: Status loaded: {self.current_position}, {self.current_direction}"
            )
        except OSError:
            # create a new status file
            with open(STATUS_FILE, "w") as f:
                f.write("")
            self.current_position = -1
            self.current_direction = 1
            self.write_message(
                "Warning: Status file not found. Initialized with defaults."
            )
        except Exception as e:
            self.write_message(f"Error: Could not load status, {e}")

    def save_config(self) -> None:
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.autosampler_config, f)
            self.write_message(
                f"Success: Configuration saved: {self.autosampler_config}"
            )
        except Exception as e:
            self.write_message(f"Error: Could not save configuration, {e}")

    def load_config(self) -> None:
        try:
            with open(CONFIG_FILE, "r") as f:
                self.autosampler_config = json.load(f)
                self.fail_safe_position = self.autosampler_config.get("fail_safe", 0)
            self.write_message(
                f"Success: Configuration loaded: {self.autosampler_config}"
            )
        except OSError:
            with open(CONFIG_FILE, "w") as f:
                json.dump({}, f)
            self.autosampler_config = {}
            self.fail_safe_position = 0
            self.write_message(
                "Warning: Config file not found. Initialized with defaults."
            )
        except Exception as e:
            self.write_message(f"Error: Could not load configuration, {e}")

    def get_time(self) -> None:
        try:
            year, month, day, _, hour, minute, second, _ = self.rtc.datetime()
            self.write_message(
                f"RTC Time: {year}-{month}-{day} {hour}:{minute}:{second}"
            )
        except Exception as e:
            self.write_message(f"Error: Could not get RTC time, {e}")

    def set_time(self, year, month, day, hour, minute, second) -> None:
        try:
            self.rtc.datetime((year, month, day, 0, hour, minute, second, 0))
            self.write_message(
                f"Success: RTC Time set to {year}-{month}-{day} {hour}:{minute}:{second}"
            )
        except Exception as e:
            self.write_message(f"Error: Could not set RTC time, {e}")

    def move_auto_sampler(self, steps) -> None:
        try:
            if steps > 0:
                self.current_direction = 1  # move to the left
            else:
                self.current_direction = 0  # move to the right
            self.direction.value(self.current_direction)

            self.is_power_on = True
            self.enable.value(0)
            for _ in range(abs(steps)):
                self.pulse.value(0)
                self.pulse.value(1)

                self.current_position -= 1 * (1 - 2 * self.current_direction)
                time.sleep_ms(self.time_interval_between_steps_ms)
                if not self.is_power_on:
                    break
            self.save_status()
            self.enable.value(1)
            self.is_power_on = False
        except Exception as e:
            self.write_message(f"Error: move_auto_sampler, {e}")
            self.enable.value(1)
            self.is_power_on = False

    def move_to_position(self, position) -> None:
        if position:
            position = int(position)
            # clamp position to valid range
            position = max(0, min(position, MAX_POSITION))

            initial_position = self.current_position
            start_time = time.ticks_us()
            self.move_auto_sampler(position - self.current_position)
            end_time = time.ticks_us()
            self.write_message(
                f"Info: moved to position {position} in {time.ticks_diff(end_time, start_time) / 1000000} seconds. relative position: {position - initial_position}"
            )
        else:
            self.write_message("Error: Invalid position input.")

    def move_to_slot(self, slot) -> None:
        if slot:
            if slot not in self.autosampler_config:
                self.write_message(f"Error: Slot {slot} not found in the configuration")
                return
            position = int(self.autosampler_config[slot])

            initial_position = self.current_position
            start_time = time.ticks_us()
            self.move_to_position(position)
            end_time = time.ticks_us()
            self.write_message(
                f"Info: moved to slot {slot} in {time.ticks_diff(end_time, start_time) / 1000000} seconds. relative position: {position - initial_position}"
            )
        else:
            self.write_message(
                f"Error: Invalid slot input, available slots: {list(self.autosampler_config.keys())}"
            )

    def shutdown(self) -> None:
        self.move_auto_sampler(-self.current_position)
        self.current_position = 0
        self.write_message("Success: Autosampler position reset to initial position.")

    def setCurrentPosition(self, position) -> None:
        if position:
            new_position = max(0, min(int(position), MAX_POSITION))
            self.current_position = new_position
            self.save_config()
            self.write_message(f"SUCCESS: Position set to: {self.current_position}")
        else:
            self.write_message("Error: Invalid position input.")

    def getCurrentPosition(self) -> None:
        self.write_message(f"INFO: Current position: {self.current_position}")

    def setCurrentDirection(self, direction: str) -> None:
        if direction:
            if direction.upper() == "LEFT":
                self.current_direction = 1
            elif direction.upper() == "RIGHT":
                self.current_direction = 0
            self.write_message(
                f"INFO: Direction set to: {self.direction_map[self.current_direction]}"
            )
        else:
            self.write_message("Error: Invalid direction input, must be LEFT or RIGHT.")

    def getCurrentDirection(self) -> None:
        self.write_message(
            f"INFO: Current direction: {self.direction_map[self.current_direction]}"
        )

    def getFailSafePosition(self) -> None:
        self.write_message(f"INFO: Fail safe position: {self.fail_safe_position}")

    def setFailSafePosition(self, position) -> None:
        if position:
            new_position = max(0, min(int(position), MAX_POSITION))
            self.fail_safe_position = new_position
            self.autosampler_config["fail_safe"] = self.fail_safe_position
            self.save_config()
            self.write_message(
                f"INFO: Fail safe position set to: {self.fail_safe_position}"
            )

    def moveToLeftMost(self) -> None:
        self.move_to_position(MAX_POSITION)

    def moveToRightMost(self) -> None:
        self.move_to_position(0)

    def dumpSlotsConfig(self) -> None:
        self.write_message(
            f"INFO: Slots configuration: {json.dumps(self.autosampler_config)}"
        )

    def setSlotPosition(self, slot, position) -> None:
        if slot and position:
            # clamp position to valid range
            position = max(0, min(int(position), MAX_POSITION))
            self.autosampler_config[slot] = int(position)
            if slot in self.autosampler_config:
                self.save_config()
                self.write_message(f"SUCCESS: Slot {slot} position set to {position}")
            else:
                self.save_config()
                self.write_message(
                    f"SUCCESS: Slot {slot} position updated to {position}"
                )

    def deleteSlot(self, slot) -> None:
        if slot in self.autosampler_config:
            self.autosampler_config.pop(slot)
            self.save_config()
            self.write_message(f"SUCCESS: Slot {slot} deleted.")
        else:
            self.write_message(f"Error: Slot {slot} not found.")


def print_help_message():
    print(
        "Available commands:\n"
        "help - Show this help message\n"
        "ping - Ping the controller\n"
        "setPosition:position - Set the current position of the autosampler\n"
        "getPosition - Get the current position of the autosampler\n"
        "setDirection:LEFT/RIGHT - Set the current direction of the autosampler\n"
        "getDirection - Get the current direction of the autosampler\n"
        "getFailSafePosition - Get the fail-safe position of the autosampler\n"
        "setFailSafePosition:position - Set the fail-safe position of the autosampler\n"
        "moveTo:position - Move to a specific position\n"
        "moveToLeftMost - Move to the leftmost position\n"
        "moveToRightMost - Move to the rightmost position\n"
        "dumpSlotsConfig - Dump the current slots configuration\n"
        "moveToSlot:slot - Move to a predefined slot in the configuration\n"
        "setSlotPosition:slot:position - Set the position of a predefined slot\n"
        "deleteSlot:slot - Delete a predefined slot from the configuration\n"
        "gtime - Get the current RTC time\n"
        "stime:year:month:day:dayoftheweek:hour:minute:second - Set the RTC time\n"
        "reset - Perform a hard reset of the controller\n"
        "set_mode:mode - Set bootloader mode (pump, autosampler, update_firmware)\n"
        "below are old commands for compatibility\n"
        "status - Send current status of the autosampler\n"
        "config - Send current configuration of the autosampler\n"
        "save_config - Save current configuration to file\n"
        "save_status - Save current status to file\n"
        "shutdown - Shutdown and reset autosampler position\n"
    )


def main():
    autosampler = Autosampler(
        pulse_pin=PULSE_PIN, direction_pin=DIRECTION_PIN, enable_pin=ENABLE_PIN
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
            led = machine.Pin("LED", machine.Pin.OUT)
            np = NeoPixel(led, 1)
            # set to red
            np[0] = (0, 10, 0)
            np.write()
            led_mode = 1
        except Exception as _:
            pass
    if led_mode == -1:  # third method is for the led on single GPIO pin
        try:
            led = machine.Pin("LED", machine.Pin.OUT)
            led.value(1)
            led_mode = 2
        except Exception as _:
            pass

    # Create a poll object to monitor stdin, which will block until there is input for reading
    poll_obj = select.poll()
    poll_obj.register(sys.stdin, select.POLLIN)

    commands = {
        "ping": "ping",
        "setPosition": "setCurrentPosition",
        "getPosition": "getCurrentPosition",
        "setDirection": "setCurrentDirection",
        "getDirection": "getCurrentDirection",
        "getFailSafePosition": "getFailSafePosition",
        "setFailSafePosition": "setFailSafePosition",
        "moveTo": "move_to_position",
        "moveToLeftMost": "moveToLeftMost",
        "moveToRightMost": "moveToRightMost",
        "dumpSlotsConfig": "dumpSlotsConfig",
        "moveToSlot": "move_to_slot",
        "setSlotPosition": "setSlotPosition",
        "deleteSlot": "deleteSlot",
        "gtime": "get_time",
        "stime": "set_time",
        "reset": "hard_reset",
        "set_mode": "set_bootloader_mode",
        # old commands
        "status": "send_status",
        "config": "send_config",
        "save_config": "save_config",
        "save_status": "save_status",
        "shutdown": "shutdown",
    }
    commands_mapping_string = ", ".join(
        [f"{key} - {value}" for key, value in commands.items()]
    )

    while True:
        try:
            # Wait for input on stdin
            poll_results = poll_obj.poll()

            if poll_results:
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

                if not data or data == "":
                    autosampler.write_message("Error: Empty input.")
                    continue

                parts = data.split(":")
                # if the first item is a digit, then it's in format digit:command..., we don't care about the digit
                if parts[0].isdigit() and len(parts) > 1:
                    parts = parts[1:]
                command = parts[0].strip()

                if command == "stime":
                    if len(parts) == 8:  # Adjusted length
                        year = int(parts[1])
                        month = int(parts[2])
                        day = int(parts[3])
                        hour = int(parts[5])
                        minute = int(parts[6])
                        second = int(parts[7])
                        autosampler.set_time(year, month, day, hour, minute, second)
                    else:
                        autosampler.write_message(
                            "Error: Invalid input, expected format 'stime:year:month:day:dayoftheweek:hour:minute:second'"
                        )
                elif command == "set_mode":
                    if len(parts) >= 2:
                        mode = str(parts[1])
                    else:
                        mode = "None"
                    try:
                        set_bootloader_mode(mode)
                        autosampler.write_message(
                            f"Success: controller set to {mode} mode"
                        )
                    except Exception as e:
                        autosampler.write_message(f"Error: {e}")
                elif command == "help":
                    print_help_message()
                elif command in commands:
                    method = getattr(autosampler, commands[command], None)
                    if method:
                        if len(parts) > 1:
                            method(*parts[1:])
                        else:
                            method()
                    else:
                        autosampler.write_message(
                            f"Warning: Command '{command}' not found."
                        )
                else:
                    autosampler.write_message(f"Warning: Invalid command {command}")
        except Exception as e:
            autosampler.write_message(f"Error: An exception occurred - {str(e)}")


if __name__ == "__main__":
    main()
