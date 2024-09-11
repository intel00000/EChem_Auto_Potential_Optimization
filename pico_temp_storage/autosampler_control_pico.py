from machine import Pin, reset, RTC
from uctypes import addressof, struct, UINT32
import pwm_dma_fade_onetime
import array
import sys
import select
import gc
import json
import os
import time

# this is a program to control a stepper motor
# define pins
pulse = machine.Pin(12, machine.Pin.OUT, machine.Pin.PULL_UP, value=0)
direction = machine.Pin(14, machine.Pin.OUT, machine.Pin.PULL_UP, value=0)
enable = machine.Pin(15, machine.Pin.OUT, machine.Pin.PULL_UP, value=1)

# a dictionary to store the status of the autosampler
rtc = RTC()
version = "0.01"
time_interval_between_steps_ms = 5
autosampler_config = {}
# the autosampler_config is a dictionary that stores a predefined set of positions for the autosampler
# the key is the position number and the value is the position in steps
# for example, autosampler_config = {1: 1000, 2: 2000, 3: 3000}
CONFIG_FILE = "autosampler_config.json"
# the current_position is just a number that stores the current position of the autosampler
current_position = -1
# direction value 1 is to the left, 0 is to the right, current_position = 0 is the rightmost position
direction_map = {0: "Right", 1: "Left"}
# default direction is to the left
current_direction = 1
STATUS_FILE = "autosampler_status.json"
is_power_on = False

print(list(direction_map.keys()))

def write_message(message):
    sys.stdout.write(f"{message}\n")

# functions to assemble and send status of the autosampler, currently we will send the current position
def send_status():
    global current_position
    status = f"Autosampler Status: position: {current_position}, direction: {direction_map[current_direction]}"
    write_message(f"{status}")

# functions to send the configuration of the autosampler, basically sending all the positions and the current position
def send_config():
    global autosampler_config
    config = f"Autosampler Configuration: {autosampler_config}"
    write_message(f"{config}")

# function to return the version of the script
def ping():
    global version
    write_message(f"Ping: Pico Autosampler Control Version {version}")

# a function to reset the device, equivalent to a hard reset
def hard_reset():
    write_message("Success: Performing hard reset.")
    reset()

# function to save the current status of the autosampler, it will be one line with the format
# "current_position, current_direction"
def save_status():
    global current_position, current_direction
    try:
        with open(STATUS_FILE, "w") as f:
            print(f"current_position: {current_position}, current_direction: {current_direction}")
            output = f"{current_position}, {current_direction}, {direction_map[current_direction]}"
            f.write(output)
        write_message(f"Success: Status saved: {output}")
    except Exception as e:
        write_message(f"Error: Could not save status, {e}")
def load_status():
    global current_position, current_direction
    try:
        with open(STATUS_FILE, "r") as f:
            # just read the first line, split by comma and assign to the variables
            first_line = f.readline().strip().split(",")
            current_position = int(first_line[0])
            current_direction = int(first_line[1])
        write_message(f"Success: Status loaded: {current_position}, {current_direction}")
    except Exception as e:
        write_message(f"Error: Could not load status, {e}")
# function to save the predefined positions of the autosampler
def save_config():
    global autosampler_config
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(autosampler_config, f)
        write_message(f"Success: Configuration saved: {autosampler_config}")
    except Exception as e:
        write_message(f"Error: Could not save configuration, {e}")
def load_config():
    global autosampler_config
    try:
        with open(CONFIG_FILE, "r") as f:
            autosampler_config = json.load(f)
        write_message(f"Success: Configuration loaded: {autosampler_config}")
    except Exception as e:
        write_message(f"Error: Could not load configuration, {e}")

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

def move_auto_sampler(steps):
    global current_position, pulse, direction, enable, is_power_on, current_direction
    if steps > 0:
        # we move to the left
        current_direction = 1
    else:
        current_direction = 0
    direction.value(current_direction)
    
    # set the power on
    is_power_on = True
    # redefine pulse pin
    pulse = machine.Pin(12, machine.Pin.OUT, machine.Pin.PULL_UP)
    enable.value(0)
    
    for i in range(abs(steps)):
        pulse.value(0)
        pulse.value(1)
        current_position -= 1 * (1 - 2 * current_direction)
        time.sleep_ms(time_interval_between_steps_ms)
        if not is_power_on:
            break

    save_status()
    enable.value(1)
    is_power_on = False
    
# a function to move the autosampler to a specific position
def move_to_position(position):
    global current_position, autosampler_config
    # position cannot be negative
    if position < 0:
        write_message(f"Error: Position cannot be negative, you are trying to move to {position}")
        return
    
    print(f"relative position: {position - current_position}")
    move_auto_sampler(position - current_position)
    print(f"Success: Autosampler moved to position {position}")
        
# function to toggle the direction of the autosampler
def toggle_direction():
    global current_direction
    current_direction = 1 - current_direction
    save_status()
    write_message(f"Success: Direction toggled to {direction_map[current_direction]}")
    
# function to reset position of the autosampler to 0
def reset_position():
    global current_position
    # move the autosampler to the 0 position
    move_auto_sampler(-current_position)
    write_message("Success: Autosampler position reset to 0")


# Define a dictionary for the commands
commands = {
    "position": "move_to_position",
    "direction": "toggle_direction",
    
    "send_position": "send_position",
    "config": "send_config",
    
    "shutdown": "reset_position",
    
    
    "reset": "hard_reset",
    "ping": "ping",
    "save": "save_config",
    "time": "get_time",
    "stime": "set_time",
}

# Create a poll object to monitor stdin, which will block until there is input for reading
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)


def main():
    # assemble a mapping from key to value in the commands dictionary
    commands_mapping_string = ", ".join(
        [f"'{key}': '{value}'" for key, value in commands.items()]
    )

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
    # Load the configuration and status
    load_config()
    load_status()

    while True:
        # Wait for input on stdin
        poll_results = poll_obj.poll()

        if poll_results:
            # Read the data from stdin (PC console input) and strip the newline character
            data = sys.stdin.readline().strip()
            dma_secondary.active(1)

            # Validate the input data
            if not data or data == "":
                write_message("Error: Empty input.")
                continue
            # Split the data by semicolon, there semicolumn might not be present in a valid command
            print(f"Received: {data}")
            
            parts = data.split(":")
            command = parts[0].strip().lower()

            # check the input and call the appropriate function
            if command == "time":
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
            elif command == "position":
                if len(parts) == 2:
                    position = int(parts[1])
                    move_to_position(position)
                else:
                    write_message(
                        "Error: Invalid input, expected format '0:position:position'"
                    )
            elif command == "direction":
                toggle_direction()
            elif command == "send_position":
                send_status()
            elif command == "config":
                send_config()
            elif command == "shutdown":
                reset_position()
            elif command == "reset":
                hard_reset()
            elif command == "ping":
                ping()
            elif command == "save":
                save_config()
            else:
                write_message(
                    f"Error: Invalid command, available commands: {commands_mapping_string}"
                )


# Run the main loop
if __name__ == "__main__":
    main()
