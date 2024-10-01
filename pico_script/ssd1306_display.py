from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
import time
import gc

# Number of samples to average, for boxcar filtering
NUM_SAMPLES = const(8)
# Accumulators for boxcar filtering
adc2_sum = 0
temp_sum = 0
# Averages for boxcar filtering
adc2_avg = 0
temp_avg = 0
# a count for slower console output
count = 0

# ADC definitions
ADC2 = ADC(2)
adc2_voltage = 0

# internal temperature sensor definition
temp_sensor = ADC(4)
conversion_factor = 3.3 / (65535)
temp_celsius = 0
temp_fahrenheit = 0

# Record the start time
start_time = time.time_ns()


# Function to scan I2C bus and return the list of addresses
def i2c_scan(i2c):
    print("Scanning I2C bus...")
    devices = i2c.scan()
    if len(devices) == 0:
        print("No I2C devices found.")
    else:
        print("I2C devices found:", [hex(device) for device in devices])
    return devices


# Initialize I2C
i2c = I2C(0, scl=Pin(1), sda=Pin(0))

# Scan the I2C bus
devices = i2c_scan(i2c)
if len(devices) == 0:
    raise Exception("No I2C devices found. Please check your connections.")

# Assuming the first device found is the OLED display
oled_address = devices[0]

# Initialize the OLED display
width = 128
height = 64
oled = SSD1306_I2C(width, height, i2c, addr=oled_address)


# Function to display elapsed time since boot
def display_elapsed_time():
    global start_time, adc2_sum, temp_sum, adc2_avg, temp_avg, count, adc2_voltage, temp_celsius
    oled.fill(0)  # clear the display
    oled.show()
    oled.fill(1)  # fill the display with white
    oled.show()  # show the display
    oled.fill(0)  # clear the display
    oled.show()

    while True:
        elapsed_time = (time.time_ns() - start_time) / 1e9
        oled.fill(0)
        oled.text("Elapsed Time:", 0, 0)
        # first limit to 3 decimal places
        # then convert to string
        # print the elapsed time, to 3 decimal places
        oled.text(f"{elapsed_time:.3f}s", 0, 16)
        # free heap memory
        oled.text(f"Mem Status (free/total): ", 0, 27)
        oled.text(f"{gc.mem_free()}/{gc.mem_free() + gc.mem_alloc()}", 0, 35)

        # print the ADC values
        oled.text(f"ADC2:{adc2_voltage:.3f} mV", 0, 45)
        # print the temperature in Celsius
        oled.text(f"Temp:{temp_celsius:.3f} C", 0, 55)

        oled.show()

        adc2_sum += ADC2.read_u16()
        temp_sum += temp_sensor.read_u16()
        count += 1

        if count >= NUM_SAMPLES:
            adc2_avg = adc2_sum / NUM_SAMPLES
            temp_avg = temp_sum / NUM_SAMPLES
            adc2_sum = 0
            temp_sum = 0
            count = 0

            # scale between 0 and 3300 mV
            adc2_voltage = adc2_avg * conversion_factor * 1000

            # convert the internal temperature sensor value to Celsius and Fahrenheit
            temp_celsius = 27 - (temp_avg * conversion_factor - 0.706) / 0.001721
            temp_fahrenheit = (temp_celsius * 9 / 5) + 32


# Run the function to display elapsed time
display_elapsed_time()
