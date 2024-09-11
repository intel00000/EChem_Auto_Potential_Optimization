import machine
import time


# this is a program to control a stepper motor
# define pins
pulse = machine.Pin(12, machine.Pin.OUT, machine.Pin.PULL_UP)
direction = machine.Pin(14, machine.Pin.OUT, machine.Pin.PULL_UP)
enable = machine.Pin(15, machine.Pin.OUT, machine.Pin.PULL_UP)

time_sleep_in_between = 5

# now we will start from one end, make five stops, each equal distance and stop for 5 seconds

# enable the motor
enable.value(0)

# set the direction
direction.value(0)

for i in range(5):
    start_time = time.ticks_ms()
    for j in range(3000):
        if j % 100 == 0:
            print(j)
        pulse.value(0)
        time.sleep_ms(2)
        pulse.value(1)
        time.sleep_ms(2)
    print(f"Step {i} reached, sleeping for {time_sleep_in_between} seconds")
    end_time = time.ticks_ms()
    print(f"Time taken for this step: {time.ticks_diff(end_time, start_time)}")
    for k in range(time_sleep_in_between):
        print(f"seconds left: {time_sleep_in_between-k}")
        time.sleep(1)
    
# go all the way back
direction.value(1)

print("Going reverse now!")

for i in range(5):
    start_time = time.ticks_ms()
    for j in range(3000):
        if j % 100 == 0:
            print(j)
        pulse.value(0)
        time.sleep_ms(2)
        pulse.value(1)
        time.sleep_ms(2)
    print(f"Step {i} reached, sleeping for {time_sleep_in_between} seconds")
    end_time = time.ticks_ms()
    print(f"Time taken for this step: {time.ticks_diff(end_time, start_time)}")
    for k in range(time_sleep_in_between):
        print(f"seconds left: {time_sleep_in_between-k}")
        time.sleep(1)
    
    
# disable the motor
enable.value(1)