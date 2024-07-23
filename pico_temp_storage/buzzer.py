"""
Kitronik Inventor's Kit Exp 6

Control the tone of a piezo buzzer with a pot.

We read the value of the analogue input A0, then rescale it to a different range.
The input is 0 - 65536, the output is scaled from 120Hz to 5kHz.
"""

import machine
import math
import time

buzzer = machine.PWM(
    machine.Pin(15)
)  # Setup GP15 as the pin controlling the buzzer with a PWM output
buzzer.freq(1000)  # set the frequency of the PWM signal driving the buzzer to 1 kHz
pot = machine.ADC(26)  # Setup the analogue (A0) on GP26 with a human-readable name


prevFrequency = 0
buzzer.duty_u16(
    32767
)  # Set a 50% duty cycle for the buzzer to produce a consistent tone


# Convert a value proportionally from one range to another
def scale(value, fromMin, fromMax, toMin, toMax):
    return toMin + ((value - fromMin) * ((toMax - toMin) / (fromMax - fromMin)))


while True:
    potValue = (
        pot.read_u16()
    )  # This variable reads the voltage that the potentiometer is adjusted to
    # Convert analogue input to frequency between 120Hz and 5kHz
    frequency = scale(potValue, 0, 65535, 120, 5000)
    # Only change the frequency if the new value is definitely different from the previous one
    # This keeps the buzzer sounding a constant pitch when the potentiometer isn't moving
    if (frequency < (prevFrequency - 50)) or (frequency > (prevFrequency + 50)):
        prevFrequency = frequency
        buzzer.freq(
            math.trunc(frequency)
        )  # Change the frequency of the buzzer to the value set by the potentiometer
        print(f"Frequency: {frequency}")
    time.sleep_ms(25)
