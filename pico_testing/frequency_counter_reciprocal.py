from machine import Pin, PWM, freq
import rp2
from rp2 import asm_pio, StateMachine

PWM_OUTPUT_PIN_ABSOLUTE = 0
PWM_OUTPUT_PIN = Pin(PWM_OUTPUT_PIN_ABSOLUTE, Pin.OUT)
INPUT_PULSE_PIN_ABSOLUTE = 22
INPUT_PULSE_PIN = Pin(INPUT_PULSE_PIN_ABSOLUTE, Pin.IN, Pin.PULL_DOWN)

TIMING_PULSE_PIN_ABSOLUTE = 20
TIMING_PULSE_PIN = Pin(TIMING_PULSE_PIN_ABSOLUTE, Pin.OUT)

CPU_FREQUENCY = 125_000_000  # 125 MHz

STATE_MACHINE_ID = 7


# PIO program to count pulses
# Define the PIO program with a blocking FIFO on full
@asm_pio()
def pulse_counter_pio():
    label("start")
    set(x, 0)  # Reset counter, this is the counter register for the pulses

    # wait for low on the timing pulse pin
    wait(1, gpio, 20)
    wait(0, gpio, 20)
    # start counting the pulses
    label("count")
    wait(1, pin, 0)  # Wait for high pulse on input pin
    wait(0, pin, 0)  # Wait for low pulse on input pin
    jmp(x_dec, "check_pin")  # Decrement counter and jump to check pin
    label("check_pin")
    jmp(pin, "push")  # If pin is high, jump to the second counter
    jmp("count")  # If pin is low, continue counting pulses

    # Push the counter value to the FIFO
    label("push")
    mov(isr, x)  # Move the x register to the ISR
    push()  # Push the ISR to the FIFO
    jmp("start")  # Restart the program


# Class to handle the pulse counting
class PulseCounter:
    def __init__(self, sm_id, program, pulse_input_pin, timing_pulse_pin):
        self.sm_id = sm_id
        # this is the input pin for the waveform to be measured
        self.pulse_input_pin = pulse_input_pin
        # this is a timing pulse to be used to measure the frequency of the input signal
        self.timing_pulse_pin = timing_pulse_pin
        # Set the frequency to match the system clock
        self.sm = StateMachine(
            sm_id,
            program,
            freq=freq(),
            in_base=pulse_input_pin,
            jmp_pin=timing_pulse_pin,
        )
        # print the id of the state machine
        print(f"State Machine ID: {rp2.StateMachine(sm_id)}")

    def read(self):
        value = self.sm.get()  # Get the value from the FIFO
        # flip the value to get the correct count
        return (0x100000000 - value) & 0xFFFFFFFF

    def reset(self):
        self.sm.restart()

    def start(self):
        self.sm.active(1)

    def stop(self):
        self.sm.active(0)


def main():
    try:
        # clear all state machines
        sm = rp2.StateMachine(STATE_MACHINE_ID)
        sm.active(0)

        freq(CPU_FREQUENCY)  # Set the CPU frequency
        print(f"cpu frequency set to: {CPU_FREQUENCY} Hz")

        # Generate test PWM signal on PWM_OUTPUT_PIN
        pwm_test = PWM(PWM_OUTPUT_PIN)
        pwm_test.freq(5000)  # Set the frequency of the PWM signal
        pwm_test.duty_u16(32768)  # Set duty cycle to 50%
        print(f"Generated PWM Frequency: {pwm_test.freq()} Hz")

        # Generate the timing pulses on the TIMING_PULSE_PIN
        timing_pulse = PWM(TIMING_PULSE_PIN)
        timing_pulse.freq(8)  # Set the frequency of the timing pulses
        # Set duty cycle to 25%
        timing_pulse.duty_u16(16384)
        # the time interval should account for the duty cycle
        timing_interval_ms = (
            1000 / timing_pulse.freq() * (1 - timing_pulse.duty_u16() / 65536)
        )

        print(
            f"Timing Pulse Frequency: {timing_pulse.freq()} Hz, Timing Interval: {timing_interval_ms} ms"
        )

        # Initialize the pulse counter for the timer method
        pulse_counter = PulseCounter(
            sm_id=7,
            program=pulse_counter_pio,
            pulse_input_pin=INPUT_PULSE_PIN,
            timing_pulse_pin=TIMING_PULSE_PIN,
        )

        # start the pulse counter
        pulse_counter.reset()
        pulse_counter.start()

        while True:
            pio_reading = pulse_counter.read()
            print(
                f"Gate Time: {timing_interval_ms} ms, Generated PWM Frequency: {pwm_test.freq()} Hz, PIO raw count: {pio_reading}, Calculated Frequency: {pio_reading / timing_interval_ms * 1000} Hz"
            )

    except KeyboardInterrupt:
        pulse_counter.stop()
        print("Stopped the pulse counter")
        print("Exiting the program")


if __name__ == "__main__":
    main()
