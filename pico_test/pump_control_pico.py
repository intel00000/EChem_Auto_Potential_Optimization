from machine import Pin
import sys
import select

# Initialize GPIO pins, the led on by default
led = Pin("LED", Pin.OUT, value=1)

# Each pump class will have a power and direction pin, defined at initialization
class Pump:
    def __init__(self, power_pin_id, direction_pin_id, initial_power_pin_value = 0, initial_direction_pin_value = 0, initial_power_status = "OFF", initial_direction_status = "CCW"):
        # both pins are set to low to prevent current flow
        self.power_pin = Pin(power_pin_id, Pin.OUT, value = initial_power_pin_value)
        self.direction_pin = Pin(direction_pin_id, Pin.OUT, value = initial_direction_pin_value)
        
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

# functions to assemble and send status, when pump_name is 0, it will send status/info for all pumps
def send_status(pump_name):
    if pump_name == 0:
        status = ", ".join([f"Pump{i} Status: {pump.get_status()}" for i, pump in pumps.items()])
        sys.stdout.write(f"{status}\n")
    elif pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Status: {pumps[pump_name].get_status()}\n")

# functions to assemble and send info, when pump_name is 0, it will send status/info for all pumps
def send_info(pump_name):
    if pump_name == 0:
        info = ", ".join([f"Pump{i} Info: {pump.get_info()}" for i, pump in pumps.items()])
        sys.stdout.write(f"{info}\n")
    elif pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Info: {pumps[pump_name].get_info()}\n")

# generic function to write a message to the console
def write_message(message):
    sys.stdout.write(f"{message}\n")

# function to register a pump, if the pump already exists, it will update the pins
def register_pump(pump_num, power_pin, direction_pin, initial_power_pin_value=0, initial_direction_pin_value=0, initial_power_status="OFF", initial_direction_status="CCW"):
    # if the pump_num is 0, it will not be registered
    if pump_num == 0:
        write_message("Error: Pump number 0 is reserved for all pumps.")
        return
    try:
        if pump_num in pumps:
            # try to reinitialize the pins
            pumps[pump_num].power_pin = Pin(power_pin, Pin.OUT, value=initial_power_pin_value)
            pumps[pump_num].direction_pin = Pin(direction_pin, Pin.OUT, value=initial_direction_pin_value)
            
            pumps[pump_num].power_pin_id = power_pin
            pumps[pump_num].direction_pin_id = direction_pin
            pumps[pump_num].initial_power_pin_value = initial_power_pin_value
            pumps[pump_num].initial_direction_pin_value = initial_direction_pin_value
            pumps[pump_num].power_status = initial_power_status
            pumps[pump_num].direction_status = initial_direction_status
            write_message(f"Success: Pump {pump_num} updated successfully.")
        else:
            pumps[pump_num] = Pump(power_pin, direction_pin, initial_power_pin_value, initial_direction_pin_value, initial_power_status, initial_direction_status)
            write_message(f"Success: Pump {pump_num} registered successfully.")
    except Exception as e:
        write_message(f"Error: registering pump {pump_num} failed, {e}")

# function to reset the controller, it will remove all pumps
def clear_pumps(pump_num):
    if pump_num == 0:
        pumps.clear()
        write_message("Success: All pumps removed.")
    elif pump_num in pumps:
        # remove the pump from the dictionary
        pumps.pop(pump_num)
        write_message(f"Success: Pump {pump_num} removed.")

# Create default pumps objects
pumps = {
    1: Pump(power_pin_id=18, direction_pin_id=17, initial_power_pin_value=0, initial_direction_pin_value=0, initial_power_status="OFF", initial_direction_status="CCW"),
    2: Pump(power_pin_id=16, direction_pin_id=14, initial_power_pin_value=0, initial_direction_pin_value=0, initial_power_status="OFF", initial_direction_status="CCW"),
    3: Pump(power_pin_id=7, direction_pin_id=15, initial_power_pin_value=0, initial_direction_pin_value=0, initial_power_status="OFF", initial_direction_status="CCW"),
}

# Define a dictionary for the commands
commands = {
    'pw': 'toggle_power',
    'di': 'toggle_direction',
    'st': 'status',
    'info': 'info',
    'reg': 'register',
    'clr': 'clear_pumps',
}

# Create a poll object to monitor stdin, which will block until there is input for reading
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

def main():
    # assemble a mapping from key to value in the commands dictionary
    commands_mapping_string = ", ".join([f"'{key}': '{value}'" for key, value in commands.items()])
    
    while True:
        # Wait for input on stdin
        poll_results = poll_obj.poll()
        
        if poll_results:
            # Read the data from stdin (PC console input) and strip the newline character
            data = sys.stdin.readline().strip()
            
            # Validate the input data
            if not data or data == '':
                write_message("Error: Empty input.")
                continue
            # Split the data into pump id and command
            parts = data.split(':')
            if len(parts) < 2:
                write_message("Error: Invalid input, expected basic format 'pump_number:command...'")
                continue
            pump_num = int(parts[0])
            command = parts[1].strip().lower()
            
            # check the input and call the appropriate function
            if command == 'reg':
                if len(parts) == 8:
                    power_pin = int(parts[2])
                    direction_pin = int(parts[3])
                    initial_power_pin_value = int(parts[4])
                    initial_direction_pin_value = int(parts[5])
                    # check if the initial power status is valid
                    if parts[6].upper() not in ["ON", "OFF"]:
                        write_message("Error: Invalid initial power status, expected 'ON' or 'OFF'")
                        continue
                    initial_power = parts[6]
                    # check if the initial direction status is valid
                    if parts[7].upper() not in ["CW", "CCW"]:
                        write_message("Error: Invalid initial direction status, expected 'CW' or 'CCW'")
                        continue
                    initial_direction = parts[7]
                    
                    register_pump(pump_num, power_pin, direction_pin, initial_power_pin_value, initial_direction_pin_value, initial_power, initial_direction)
                else:
                    write_message("Error: Invalid input, expected format 'pump_number:reg:power_pin:direction_pin:initial_power_pin_value:initial_direction_pin_value:initial_power_status:initial_direction_status'")
            
            elif pump_num == 0:
                if command == 'st':
                    send_status(0)
                elif command == 'info':
                    send_info(0)
                elif command == 'clr':
                    clear_pumps(0)
                elif command in commands:
                    for pump in pumps.values():
                        method = getattr(pump, commands[command], None)
                        if method:
                            method()
                else:
                    write_message(f"Error: Invalid command for pump 0 '{command}', available commands are: " + commands_mapping_string)
            
            elif pump_num in pumps:
                # get the pump instance
                pump = pumps[pump_num]
                
                # check if the command is valid
                if command in commands:
                    if command == 'st':
                        send_status(pump_num)
                    elif command == 'info':
                        send_info(pump_num)
                    elif command == 'clr':
                        clear_pumps(pump_num)
                    else:
                        method = getattr(pump, commands[command], None)
                        if method:
                            method()
                else:
                    write_message(f"Error: Invalid command for pump '{pump_num}', available commands are: " + commands_mapping_string)
            else:
                write_message(f"Error: Invalid pump number '{pump_num}', available pumps are: " + ", ".join(map(str, pumps.keys())))

# Run the main loop
if __name__ == "__main__":
    main()