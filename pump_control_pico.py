from machine import Pin, WDT
import sys
import select
import _thread

# Initialize GPIO pins, the led on by default
led = Pin("LED", Pin.OUT, value=1)

# each pump class will have a power and direction pin, defined at initialization
class Pump:
    def __init__(self, power_pin, direction_pin):
        # both pins are set to low to prevent current flow
        self.power_pin = Pin(power_pin, Pin.OUT, value=0)
        self.direction_pin = Pin(direction_pin, Pin.OUT, value=0)
        self.power_status = False
        self.direction_status = False
    
    def toggle_power(self):
        self.power_status = not self.power_status
        self.power_pin.value(self.power_status)
    
    def toggle_direction(self):
        self.direction_status = not self.direction_status
        self.direction_pin.value(self.direction_status)

    def get_status(self):
        power_status_str = 'ON' if self.power_status else 'OFF'
        direction_status_str = 'CW' if self.direction_status else 'CCW'
        return f"Power: {power_status_str}, Direction: {direction_status_str}"
    
def send_status():
    status = ", ".join([f"Pump{i} {pump.get_status()}" for i, pump in pumps.items()])
    sys.stdout.write(f"{status}\n")

def send_status_specific(pump_name):
    if pump_name in pumps:
        sys.stdout.write(f"Pump{pump_name} Status: {pumps[pump_name].get_status()}\n")

def write_message(message):
    sys.stdout.write(f"{message}\n")

# Create pump instances
pumps = {
    1: Pump(14, 15),
    2: Pump(12, 13),
    3: Pump(10, 11),
}

# Define a dictionary for the commands
commands = {
    'pw': 'toggle_power',
    'di': 'toggle_direction',
    'st': 'status',
}

# Create a poll object to monitor stdin, which will block until there is input for reading
poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

# Initialize Watchdog Timer with a timeout of 1000ms
wdt = WDT(timeout=1000)

def main():
    while True:
        # Feed the watchdog timer to prevent reset
        wdt.feed()
        
        # Wait for input on stdin, timeout is set to 100ms
        poll_results = poll_obj.poll(100)
        
        if poll_results:
            # Read the data from stdin (PC console input) and strip the newline character
            data = sys.stdin.readline().strip()
            
            # Validate the input data
            if not data or data == '':
                _thread.start_new_thread(write_message, ("Invalid input: No data received",))
                continue
            if ':' not in data:
                _thread.start_new_thread(write_message, ("Invalid input: Expected format 'pump_number:command'",))
                continue

            # Split the data into pump number and command
            parts = data.split(':')
            if len(parts) != 2:
                _thread.start_new_thread(write_message, ("Invalid input: Expected format 'pump_number:command'",))
                continue
            try:
                pump_num = int(parts[0])
            except ValueError:
                _thread.start_new_thread(write_message, ("Invalid input: Pump number must be an integer",))
                continue
            command = parts[1].strip().lower()
            
            # check the input and call the appropriate function
            if pump_num in pumps:
                # get the pump instance
                pump = pumps[pump_num]
                
                # check if the command is valid
                if command in commands:
                    if command == 'st':
                        _thread.start_new_thread(send_status_specific, (pump_num,))
                    else:
                        method = getattr(pump, commands[command], None)
                        if method:
                            method()
                else:
                    _thread.start_new_thread(write_message, ("Invalid command: Use 'pw', 'di' or 'st'",))
            else:
                _thread.start_new_thread(write_message, (f"Invalid pump number '{pump_num}', available pumps are: " + ", ".join(map(str, pumps.keys())),))

# Run the main loop
if __name__ == '__main__':
    main()