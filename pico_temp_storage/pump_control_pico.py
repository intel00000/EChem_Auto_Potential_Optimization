from machine import Pin
import sys
import select

# Initialize GPIO pins, the led on by default
led = Pin("LED", Pin.OUT, value=1)

# Each pump class will have a power and direction pin, defined at initialization
class Pump:
    def __init__(self, power_pin_id, direction_pin_id, initial_power_pin_value = 0, initial_direction_pin_value = 0):
        # both pins are set to low to prevent current flow
        self.power_pin_id = power_pin_id
        self.direction_pin_id = direction_pin_id
        self.initial_power_pin_value = initial_power_pin_value
        self.initial_direction_pin_value = initial_direction_pin_value
        
        self.power_pin = Pin(power_pin_id, Pin.OUT, value = initial_power_pin_value)
        self.direction_pin = Pin(direction_pin_id, Pin.OUT, value = initial_direction_pin_value)
        self.power_status = False
        self.direction_status = False
    
    def toggle_power(self):
        # flip the power pin value and update the power status
        self.power_pin.value(not self.power_pin.value())
        self.power_status = not self.power_status
    
    def toggle_direction(self):
        self.direction_pin.value(not self.direction_pin.value())
        self.direction_status = not self.direction_status

    def get_status(self):
        return f"Power: {'ON' if self.power_status else 'OFF'}, Direction: {'CW' if self.direction_status else 'CCW'}"
    
    def get_info(self):
        return f"Power Pin ID: {self.power_pin_id}, Direction Pin ID: {self.direction_pin_id}, Initial Power Status: {'ON' if self.power_status else 'OFF'}, Initial Direction Status: {'CW' if self.direction_status else 'CCW'}"

def send_status(pump_name):
    if pump_name == 0:
        status = ", ".join([f"Pump{i} Status: {pump.get_status()}" for i, pump in pumps.items()])
        sys.stdout.write(f"{status}\n")
    elif pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Status: {pumps[pump_name].get_status()}\n")

def send_info(pump_name):
    if pump_name == 0:
        info = ", ".join([f"Pump{i} Info: {pump.get_info()}" for i, pump in pumps.items()])
        sys.stdout.write(f"{info}\n")
    elif pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Info: {pumps[pump_name].get_info()}\n")

def write_message(message):
    sys.stdout.write(f"{message}\n")

# Create pump instances
pumps = {
    1: Pump(power_pin_id=15, direction_pin_id=14, initial_power_pin_value=0, initial_direction_pin_value=0),
    2: Pump(power_pin_id=13, direction_pin_id=18, initial_power_pin_value=0, initial_direction_pin_value=0),
    3: Pump(power_pin_id=17, direction_pin_id=16, initial_power_pin_value=0, initial_direction_pin_value=0),
}

# Define a dictionary for the commands
commands = {
    'pw': 'toggle_power',
    'di': 'toggle_direction',
    'st': 'status',
    'info': 'info',
}

# Create a poll object to monitor stdin, which will block until there is input for reading
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

def main():
    while True:
        # Wait for input on stdin
        poll_results = poll_obj.poll()
        
        if poll_results:
            # Read the data from stdin (PC console input) and strip the newline character
            data = sys.stdin.readline().strip()
            
            # Validate the input data
            if not data or data == '':
                write_message("Invalid input: No data received")
                continue
            # Split the data into pump number and command
            parts = data.split(':')
            if len(parts) != 2:
                write_message("Invalid input: Expected format 'pump_number:command'")
                continue
            pump_num = int(parts[0])
            command = parts[1].strip().lower()
            
            # check the input and call the appropriate function
            if pump_num == 0:
                if command == 'st':
                    send_status(0)
                elif command == 'info':
                    send_info(0)
                elif command in commands:
                    for pump in pumps.values():
                        method = getattr(pump, commands[command], None)
                        if method:
                            method()
                else:
                    write_message(f"Invalid command for pump 0 '{command}', available commands are: 'st', 'info', 'pw', 'di'")
            elif pump_num in pumps:
                # get the pump instance
                pump = pumps[pump_num]
                
                # check if the command is valid
                if command in commands:
                    if command == 'st':
                        send_status(pump_num)
                    elif command == 'info':
                        send_info(pump_num)
                    else:
                        method = getattr(pump, commands[command], None)
                        if method:
                            method()
                else:
                    write_message(f"Invalid command: '{command}', available commands are: 'pw', 'di', 'st', 'info'")
            else:
                write_message(f"Invalid pump number '{pump_num}', available pumps are: " + ", ".join(map(str, pumps.keys())))

# Run the main loop
if __name__ == "__main__":
    main()