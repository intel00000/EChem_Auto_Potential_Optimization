from machine import Pin, I2C, ADC
import sys
import select
import time
import _thread

# Initialize GPIO pins, the led on by default
# both pins are set to low to prevent current flow
led = Pin("LED", Pin.OUT, value=1)
pin0 = Pin(0, Pin.OUT, value=0)
pin1 = Pin(1, Pin.OUT, value=0)

power_status = False
direction_status = False

poll_obj = select.poll()
poll_obj.register(sys.stdin, select.POLLIN)

def power():
    global power_status
    
    # if the power status is True, set the pin to low to allow current to flow
    if power_status:
        pin0.low()
    else:
        pin0.high()
        
    # flip the power status
    power_status = not power_status

# same for the direction
def direction():
    global direction_status
    
    if direction_status:
        pin1.low()
    else:
        pin1.high()
        
    direction_status = not direction_status

def send_status():
    sys.stdout.write(f"Power: {'ON' if power_status else 'OFF'}, Direction: {'CW' if direction_status else 'CCW'}\n")
    
def write_message(message):
    sys.stdout.write(f"{message}\n")

def main():
    
    while True:
        # Wait for input on stdin
        poll_results = poll_obj.poll()
        
        if poll_results:
            # Read the data from stdin (PC console input) and strip the newline character
            data = sys.stdin.readline('\n').strip()
            
            # check the input and call the appropriate function
            if data.lower().startswith('power'):
                power()
            elif data.lower().startswith('direction'):
                direction()
            elif data.lower().startswith('status'):
                _thread.start_new_thread(send_status, ())
            else:
                _thread.start_new_thread(write_message, ("Invalid input, send 'power', 'direction' or 'status'",))

# Run the main loop
if __name__ == '__main__':
    main()