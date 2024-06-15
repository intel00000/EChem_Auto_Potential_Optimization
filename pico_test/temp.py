from machine import ADC
import time

# Define internal temperature sensor
temp_sensor = ADC(4)
conversion_factor = 3.3 / (65535)

def read_temp_celsius() -> float:
    # Read the temperature sensor value
    raw_temp = temp_sensor.read_u16() * conversion_factor

    # Convert the raw temperature value to Celsius
    temperature = (raw_temp - 0.706) / 0.001721

    return temperature

def convert_celsius_to_fahrenheit(celsius: float) -> float:
    return (celsius * 9/5) + 32

print("Starting temp.py")

# Define a flag to control the temperature reading
temp_flag = True

# Read and print the temperature every second
while temp_flag:
    temp_celsius = read_temp_celsius()
    temp_fahrenheit = convert_celsius_to_fahrenheit(temp_celsius)
    print(f"RP2040 Temperature in Celsius: {temp_celsius:.2f} C")
    print(f"RP2040 Temperature in Fahrenheit: {temp_fahrenheit:.2f} F")
    print(f"Device time: {time.time()}")
    time.sleep(1)

print("Stopped temp.py")