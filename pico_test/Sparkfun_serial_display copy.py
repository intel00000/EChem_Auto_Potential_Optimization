from machine import Pin, I2C, ADC, PWM
import time
import math

ADC1_value = 0  # This variable will count up to 65k
s7sAddress = 0x71  # I2C address of the Sparkfun Serial 7 Segment

i2c = I2C(1, scl=Pin(19), sda=Pin(18), freq=400000)
time.sleep_ms(100)

s7sAddress  = i2c.scan()[0]
print(f"Found device at address: {s7sAddress}")

led = Pin('LED', Pin.OUT)
ADC0 = ADC(0)
ADC1 = ADC(1)
ADC2 = ADC(2)
internal_temp_sensor = ADC(4)

servo = PWM(Pin(15))

servo.freq(50)

def s7s_send_string_i2c(toSend):
    data = bytearray(4)
    for i in range(4):
        data[i] = ord(toSend[i])
    i2c.writeto(s7sAddress, data)

def clear_display_i2c():
    # clear the display
    i2c.writeto(s7sAddress, b'\x76')

def set_brightness_i2c(value):
    i2c.writeto(s7sAddress, b'\x7A' + bytes([value]))

def set_decimals_i2c(decimals):
    i2c.writeto(s7sAddress, b'\x77' + bytes([decimals]))

# rate from 0 to 11
def set_baud_rate_i2c(rate):
    i2c.writeto(s7sAddress, b'\x7F' + bytes([rate]))
    
def factory_reset_i2c():
    i2c.writeto(s7sAddress, b'\x81')

def setup():
    clear_display_i2c()
    time.sleep(1)
    s7s_send_string_i2c("-HI-")
    # set_decimals_i2c(0b00111111)  # Turn on all decimals, colon, apos

    set_brightness_i2c(0)  # Lowest brightness
    time.sleep(1)
    set_brightness_i2c(100)  # High brightness
    time.sleep(1)
    set_brightness_i2c(25)  # medium brightness
    time.sleep(1)
    
    set_baud_rate_i2c(6)  # 57600 baud

    clear_display_i2c()

def read_temp_celcius(temp_sensor) -> float:
    conversion_factor = 3.3 / (65535)
    
    # Read the temperature sensor value
    raw_temp = temp_sensor.read_u16() * conversion_factor

    # Convert the raw temperature value to Celsius
    temperature = 27 - (raw_temp - 0.706) / 0.001721

    # format the output to 2 decimal places
    return round(temperature, 2)

def convert_celcius_to_fahrenheit(celcius: float) -> float:
    return round((celcius * 9/5) + 32)

def loop():
    global ADC1_value
    ADC1_value = ADC1.read_u16()
    # scale between 0 and 4096
    ADC1_value = int(ADC1_value/65535*9999)
    
    tempString = "{:4d}".format(ADC1_value)
    s7s_send_string_i2c(tempString)
    
    print(f"ADC1: {ADC1.read_u16()},tempString: {tempString}, scaled ADC1_value: {ADC1_value}")

    if ADC1_value < 10000:
        set_decimals_i2c(0b00001000)  # Sets digit 3 decimal on
    else:
        set_decimals_i2c(0b00000010)

    ADC1_value += 1
    led.toggle()
    time.sleep(0.2)  # This will make the display update at 5Hz
    # time.sleep_us(1)  # This will make the display update at 1kHz
    
"""     # print the internal temperature sensor
    internal_temp = read_temp_celcius(internal_temp_sensor)
    print(f"Internal Temp: {internal_temp} C, {convert_celcius_to_fahrenheit(internal_temp)} F")
    tempString = "{:4d}".format(int(internal_temp * 100))
    set_decimals_i2c(0b00000010)
    s7s_send_string_i2c(tempString)
    time.sleep(1.5)
    set_decimals_i2c(0b00000000) """
    
def run():
    setup()
    while True:
        loop()
    
if __name__ == "__main__":
    run()