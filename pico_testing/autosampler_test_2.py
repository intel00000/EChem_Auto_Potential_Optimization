import machine
import time


# this is a program to control a stepper motor
# define pins
pulse = machine.Pin(12, machine.Pin.OUT, machine.Pin.PULL_UP)
direction = machine.Pin(14, machine.Pin.OUT, machine.Pin.PULL_UP)
enable = machine.Pin(15, machine.Pin.OUT, machine.Pin.PULL_UP)

time_interval_between_steps = 5

# now we will start from one end and go to the other end

current_position = 0
direction_value = 1

# enable the motor
enable.value(0)

# set the direction
direction.value(direction_value)

start_time = time.ticks_ms()
for i in range(100):
    print(f"Current position: {current_position}")
    pulse.value(0)
    pulse.value(1)
    time.sleep_ms(time_interval_between_steps)
    current_position += 1
end_time = time.ticks_ms()
print(f"Time taken for this step: {time.ticks_diff(end_time, start_time)}")

# disable the motor
enable.value(1)

# go in the other direction
enable.value(0)
direction.value(not direction_value)

start_time = time.ticks_ms()
for i in range(100):
    print(f"Current position: {current_position}")
    pulse.value(0)
    pulse.value(1)
    time.sleep_ms(time_interval_between_steps)
    current_position -= 1

end_time = time.ticks_ms()

print(f"Time taken for this step: {time.ticks_diff(end_time, start_time)}")

enable.value(1)
