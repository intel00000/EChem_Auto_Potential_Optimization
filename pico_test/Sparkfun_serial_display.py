from machine import Pin, I2C, ADC
import time

ADC1_value = 0  # This variable will count up to 65k
s7sAddress = 0x71  # I2C address of the Sparkfun Serial 7 Segment

i2c = I2C(1, scl=Pin(5), sda=Pin(4), freq=400000)
time.sleep_ms(100)

s7sAddress  = i2c.scan()[0]
print(f"Found device at address: {s7sAddress}")

led = Pin('LED', Pin.OUT)
ADC0 = ADC(Pin(26))
ADC1 = ADC(Pin(27))
ADC2 = ADC(Pin(28))

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

def setup():
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

def loop():
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
    
def run():
    setup()
    while True:
        loop()
    
if __name__ == "__main__":
    run()