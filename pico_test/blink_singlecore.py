from machine import Pin, Timer, ADC
import time

# Define the onboard LED pin
led = Pin('LED', Pin.OUT)

Power = Pin(0, Pin.OUT, Pin.PULL_DOWN)

direction = Pin(1, Pin.OUT, Pin.PULL_DOWN)
    
def start_tasks():
    # toggle the direction pin every 5 seconds
    # toggle the power pin every 2.5 seconds
    # toggle the led pin every 2.5 seconds
    while True:
        Power.toggle()
        direction.toggle()
        led.toggle()
        time.sleep(2.5)
        Power.toggle()
        led.toggle()
        time.sleep(2.5)
        Power.toggle()
        direction.toggle()
        led.toggle()
        
if __name__ == "__main__":
    start_tasks()