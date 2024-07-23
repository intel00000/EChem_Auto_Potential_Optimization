from machine import Pin, SPI, ADC
import time

# Define pin connections
start_stop_pin = Pin(0, Pin.OUT)
cw_ccw_pin = Pin(1, Pin.OUT)
local_remote_input_pin = Pin(2, Pin.IN, Pin.PULL_UP)
motor_running_pin = Pin(3, Pin.IN, Pin.PULL_UP)
ad5761_sdo = Pin(4, Pin.IN)
ad5761_sync = Pin(5, Pin.OUT)
ad5761_sclk = Pin(6, Pin.OUT)
ad5761_sdi = Pin(7, Pin.OUT)
prime_pin = Pin(8, Pin.OUT)
open_head_sensor_pin = Pin(9, Pin.IN, Pin.PULL_UP)
general_alarm_pin = Pin(10, Pin.IN, Pin.PULL_UP)
local_remote_output_pin = Pin(11, Pin.IN, Pin.PULL_UP)
ad5761_alert = Pin(12, Pin.IN, Pin.PULL_UP)
tach_output_pin = Pin(22, Pin.IN, Pin.PULL_UP)
speed_signal_voltage_adc = ADC(26)

# SPI configuration
spi = SPI(
    0,
    baudrate=5000000,
    polarity=1,
    phase=1,
    sck=ad5761_sclk,
    mosi=ad5761_sdi,
    miso=ad5761_sdo,
)

# Initialize pins
ad5761_sync.value(1)  # Deselect DAC
ad5761_alert.irq(trigger=Pin.IRQ_FALLING, handler=lambda t: print("Alert detected!"))


# Function to write to the control register
def write_control_register():
    command = 0x040000  # Command to write to control register with all bits don't care
    high_byte = (command >> 16) & 0xFF
    mid_byte = (command >> 8) & 0xFF
    low_byte = command & 0xFF
    ad5761_sync.value(0)  # Select DAC
    spi.write(bytearray([high_byte, mid_byte, low_byte]))  # Write data
    ad5761_sync.value(1)  # Deselect DAC
    time.sleep(0.01)  # Ensure proper timing


# Function to write and update the DAC register with a 16-bit value
def write_and_update_dac(value):
    command = 0x030000 | (value & 0xFFFF)  # Command to write and update DAC register
    high_byte = (command >> 16) & 0xFF
    mid_byte = (command >> 8) & 0xFF
    low_byte = command & 0xFF
    ad5761_sync.value(0)  # Select DAC
    write_content = bytearray([high_byte, mid_byte, low_byte])
    spi.write(write_content)  # Write data
    # print the binary value of the data written
    print(
        f"Binary value written to DAC: {write_content[0]:08b} {write_content[1]:08b} {write_content[2]:08b}"
    )
    ad5761_sync.value(1)  # Deselect DAC
    time.sleep(0.01)  # Ensure proper timing


# Function to read back from the DAC register
def read_dac():
    command = 0xA00000  # Command to readback DAC register
    ad5761_sync.value(0)  # Select DAC
    # print the binary value of the command
    print(f"Binary command sent to DAC: {command:024b}")
    spi.write(
        bytearray([(command >> 16) & 0xFF, (command >> 8) & 0xFF, command & 0xFF])
    )
    ad5761_sync.value(1)  # Deselect DAC
    time.sleep(0.01)
    ad5761_sync.value(0)  # Select DAC again for read
    read_data = spi.read(3)  # Read 24 bits
    ad5761_sync.value(1)  # Deselect DAC
    return read_data


# Toggle output functions
def toggle_start_stop():
    start_stop_pin.value(not start_stop_pin.value())


def toggle_cw_ccw():
    cw_ccw_pin.value(not cw_ccw_pin.value())


def toggle_prime():
    prime_pin.value(not prime_pin.value())


# Print summary of inputs
def print_summary():
    motor_running = motor_running_pin.value() == 0
    open_head_sensor = open_head_sensor_pin.value() == 0
    general_alarm = general_alarm_pin.value() == 0
    local_remote_output = local_remote_output_pin.value() == 0
    local_remote_input = local_remote_input_pin.value() == 0

    # Read Tach Output and convert to RPM
    pulse_count = 0

    def count_pulse(pin):
        nonlocal pulse_count
        pulse_count += 1

    tach_output_pin.irq(trigger=Pin.IRQ_RISING, handler=count_pulse)
    time.sleep(1)
    tach_output_pin.irq(handler=None)  # Disable IRQ after counting
    rpm = pulse_count * 6  # Since 10 Hz per RPM

    # Read Speed Signal Voltage and convert to mV and percentage
    speed_signal_voltage = speed_signal_voltage_adc.read_u16()
    voltage_mV = (
        speed_signal_voltage / 65535
    ) * 2500  # Convert 0-65535 ADC value to 0-2500 mV
    voltage_percentage = (
        voltage_mV / 2500
    ) * 100  # Convert mV to percentage of 0-2.5V range

    print("Summary of Inputs:")
    print(f"Motor Running: {'Yes' if motor_running else 'No'}")
    print(f"Open Head Sensor: {'Activated' if open_head_sensor else 'Deactivated'}")
    print(f"General Alarm: {'On' if general_alarm else 'Off'}")
    print(f"Local/Remote Output: {'Remote' if local_remote_output else 'Local'}")
    print(f"Local/Remote Input: {'Remote' if local_remote_input else 'Local'}")
    print(f"Tach Output (RPM): {rpm}")
    print(f"Speed Signal Voltage: {voltage_mV:.2f} mV ({voltage_percentage:.2f}%)")


# Main loop
def main():
    write_control_register()  # Write to the control register first
    while True:
        # Example usage: toggle and print summary every 5 seconds
        toggle_start_stop()
        toggle_cw_ccw()
        toggle_prime()
        print_summary()
        # Example of setting a DAC value
        write_and_update_dac(0x8000)  # Mid-scale value for 16-bit DAC
        time.sleep(5)


# Run the main loop
if __name__ == "__main__":
    main()
