import machine

def calculate_frequencies():
    # Get the CPU frequency in Hz
    cpu_frequency = machine.freq()

    # Calculate the maximum state machine frequency
    # For the RP2040, the PIO clock frequency is derived from the CPU clock
    # Assume the state machine runs at the same frequency as the CPU
    max_state_machine_frequency = cpu_frequency

    return {
        "cpu_frequency_hz": cpu_frequency,
        "max_state_machine_frequency_hz": max_state_machine_frequency
    }

# Example usage
frequencies = calculate_frequencies()
print(f"CPU Frequency: {frequencies['cpu_frequency_hz'] / 1_000_000} MHz")
print(f"Max State Machine Frequency: {frequencies['max_state_machine_frequency_hz'] / 1_000_000} MHz")