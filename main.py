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

ADC1_value = 0
s7sAddress = 0x71  # I2C address of the Sparkfun Serial 7 Segment

i2c = I2C(1, scl=Pin(3), sda=Pin(2), freq=400000)
time.sleep_ms(100)

s7sAddress  = i2c.scan()[0]

led = Pin('LED', Pin.OUT)
ADC0 = ADC(Pin(26))
ADC1 = ADC(Pin(27))
ADC2 = ADC(Pin(28))

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
    
def s7s_send_string_i2c(toSend):
    data = bytearray(4)
    for i in range(4):
        data[i] = ord(toSend[i])
    i2c.writeto(s7sAddress, data)

def clear_display_i2c():
    i2c.writeto(s7sAddress, b'\x76')

def set_brightness_i2c(value):
    i2c.writeto(s7sAddress, b'\x7A' + bytes([value]))

def set_decimals_i2c(decimals):
    i2c.writeto(s7sAddress, b'\x77' + bytes([decimals]))

def serial_display_setup():
    clear_display_i2c()
    s7s_send_string_i2c("-HI-")
    set_decimals_i2c(0b00111111)  # Turn on all decimals, colon, apos

    set_brightness_i2c(0)  # Lowest brightness
    time.sleep(1)
    set_brightness_i2c(255)  # High brightness
    time.sleep(1)
    set_brightness_i2c(100)  # medium brightness
    time.sleep(1)

    clear_display_i2c()

def serial_display_loop():
    global ADC1_value
    ADC1_value = ADC1.read_u16()
    # scale between 0 and 9999
    ADC1_value = int(ADC1_value/65535*99999)
    
    tempString = "{:4d}".format(ADC1_value)
    s7s_send_string_i2c(tempString)
    
    print(f"ADC1: {ADC1.read_u16()},tempString: {tempString}, scaled ADC1_value: {ADC1_value}")

    if ADC1_value < 10000:
        set_decimals_i2c(0b00000100)  # Sets digit 3 decimal on
    else:
        set_decimals_i2c(0b00001000)

    ADC1_value += 1
    time.sleep_us(1)  # This will make the display update at 10Hz
    
def run_serial_display():
    serial_display_setup()
    while True:
        serial_display_loop()

def main():
    _thread.start_new_thread(run_serial_display, ())
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
                send_status()
            else:
                write_message("Invalid input, send 'power', 'direction' or 'status'")

# Run the main loop
if __name__ == '__main__':
    main()