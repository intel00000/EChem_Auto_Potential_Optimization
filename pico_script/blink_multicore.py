from machine import Pin, Timer, ADC
import _thread
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
    temperature = 27 - (raw_temp * conversion_factor - 0.706) / 0.001721

    return temperature

def convert_celcius_to_fahrenheit(celcius: float) -> float:
    return (celcius * 9/5) + 32

count = 1

# blink the LED
def blink(timer) -> None:
    global count
    led.toggle()
    print(f"Count: {count}")
    count += 1

def start_blinking(time_interval_ms = 1000) -> None:
    # Create a timer object using Timer class
    timer = Timer()

    time_interval = time_interval_ms

    print(f"Starting blink.py")
    print(f"Blinking LED every {time_interval}ms")
    # Call the blink function every 1000ms
    timer.init(period=time_interval, mode=Timer.PERIODIC, callback=blink)

# Temperature reading task to run on the second core
def read_temperature_task(time_interval = 1):
    while True:
        temperature_celsius = read_temp_celcius()
        temperature_fahrenheit = convert_celcius_to_fahrenheit(temperature_celsius)
        print(f"RP2040 Temperature in Celsius: {temperature_celsius} C")
        print(f"RP2040 Temperature in Fahrenheit: {temperature_fahrenheit} F")
        print(f"Device time: {time.time()}")
        time.sleep(time_interval)

def start_both_tasks():
    # Do the blinking on the second core
    _thread.start_new_thread(start_blinking, ())

    # Start the temperature reading task on the current core
    read_temperature_task()
