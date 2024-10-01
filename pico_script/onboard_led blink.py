from machine import Pin, Timer, ADC
import time

# Define the onboard LED pin
led = Pin('LED', Pin.OUT)

# Define internal temperature sensor
temp_sensor = ADC(4)
conversion_factor = 3.3 / (65535)

def read_temp_celcius() -> float:
    # Read the temperature sensor value
    raw_temp = temp_sensor.read_u16() * conversion_factor

    # Convert the raw temperature value to Celsius
    temperature = 27 - (raw_temp - 0.706) / 0.001721

    return temperature

def convert_celcius_to_fahrenheit(celcius: float) -> float:
    return (celcius * 9/5) + 32

count = 1

# Combined task for blinking LED and reading temperature
def combined_task(timer) -> None:
    global count
    # Blink the LED
    led.toggle()
    print(f"Count: {count}")
    
    # Read and print temperature
    temperature_celsius = read_temp_celcius()
    temperature_fahrenheit = convert_celcius_to_fahrenheit(temperature_celsius)
    print(f"RP2040 Temperature in Celsius: {temperature_celsius:.2f} C")
    print(f"RP2040 Temperature in Fahrenheit: {temperature_fahrenheit:.2f} F")
    print(f"Device time: {time.time()}")
    
    count += 1

def start_tasks():
    # Create a timer object using Timer class
    timer = Timer()

    time_interval = 1000 #1000ms

    print(f"Starting blink.py")
    print(f"Executing combined task every {time_interval}ms")
    # Call the combined_task function every 1000ms
    timer.init(period=time_interval, mode=Timer.PERIODIC, callback=combined_task)