from machine import Pin, PWM
import time

time_sleep_in_between = 5


# now we will start from one end, make five stops, each equal distance and stop for 5 seconds
def main():
    # this is a program to control a stepper motor
    # define pins
    pulse = machine.Pin(12, machine.Pin.OUT, machine.Pin.PULL_UP, value=0)
    direction = machine.Pin(14, machine.Pin.OUT, machine.Pin.PULL_UP, value=0)
    enable = machine.Pin(15, machine.Pin.OUT, machine.Pin.PULL_UP, value=1)

    # enable the motor
    enable.value(0)
    direction.value(0)

    print("Starting the motor")
    start_time = time.ticks_ms()
    print("break point")
    for i in range(10000):
        pulse.value(0)
        pulse.value(1)
        time.sleep_ms(5)
    end_time = time.ticks_ms()
    print(f"Time taken for this step: {time.ticks_diff(end_time, start_time)}")

    # disable the motor
    enable.value(1)


# Run the main loop
if __name__ == "__main__":
    main()
