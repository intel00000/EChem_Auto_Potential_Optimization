from machine import Pin, SPI, ADC
import time
from AD5761 import AD5761

# Define pin connections
start_stop_pin = Pin(0, Pin.OUT, value=0, pull=Pin.PULL_DOWN)
cw_ccw_pin = Pin(1, Pin.OUT, value=0, pull=Pin.PULL_DOWN)
local_remote_input_pin = Pin(2, Pin.IN, Pin.PULL_UP)
motor_running_pin = Pin(3, Pin.IN, Pin.PULL_UP)
prime_pin = Pin(8, Pin.OUT)
open_head_sensor_pin = Pin(9, Pin.IN, Pin.PULL_UP)
general_alarm_pin = Pin(10, Pin.IN, Pin.PULL_UP)
local_remote_output_pin = Pin(11, Pin.IN, Pin.PULL_UP)
tach_output_pin = Pin(22, Pin.IN, Pin.PULL_UP)
speed_signal_voltage_adc = ADC(26)

# Initialize AD5761 DAC
ad5761 = AD5761(
    spi_id=0, sclk_pin=6, sdi_pin=7, sdo_pin=4, sync_pin=5, alert_pin=12, debug=True, baudrate=1_000_000,
)

# Toggle output functions
def toggle_start_stop():
    start_stop_pin.value(not start_stop_pin.value())
    print(f"Start/Stop Pin toggled to {start_stop_pin.value()}")
    time.sleep(1)
    print(f"Motor Running: {'Yes' if motor_running_pin.value() == 0 else 'No'}")


def toggle_cw_ccw():
    cw_ccw_pin.value(not cw_ccw_pin.value())
    print(f"CW/CCW Pin toggled to {cw_ccw_pin.value()}")
    time.sleep(1)
    print(f"Motor Running: {'Yes' if motor_running_pin.value() == 0 else 'No'}")


def toggle_prime():
    prime_pin.value(not prime_pin.value())
    print(f"Prime Pin toggled to {prime_pin.value()}")
    time.sleep(1)
    print(f"Motor Running: {'Yes' if motor_running_pin.value() == 0 else 'No'}")


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
    speed_signal_voltage = 0
    for i in range(10):
        speed_signal_voltage += speed_signal_voltage_adc.read_u16()
    
    speed_signal_voltage /= 10  # Average over 10 samples
    
    voltage_mV = (
        speed_signal_voltage / 65535
    ) * 3300  - 15 # Convert 0-65535 ADC value to 0-3300 mV
    voltage_percentage = (
        voltage_mV / 2500
    ) * 100  # Convert mV to percentage of 0-2.5V range

    print("------------------------------------------------")
    print("Summary:")
    print(f"Motor Running: {'Yes' if motor_running else 'No'}")
    print(f"Direction: {'CW' if cw_ccw_pin.value() else 'CCW'}")
    print(f"Open Head Sensor: {'Activated' if open_head_sensor else 'Deactivated'}")
    print(f"General Alarm: {'On' if general_alarm else 'Off'}")
    print(f"Local/Remote Output: {'Remote' if local_remote_output else 'Local'}")
    print(f"Local/Remote Input: {'Remote' if local_remote_input else 'Local'}")
    print(f"Tach Output (RPM): {rpm}")
    print(f"Speed Signal Voltage: {voltage_mV:.2f} mV ({voltage_percentage:.2f}%)")
    print("------------------------------------------------")

# Main loop
def main():
    
    toggle_start_stop()
    ad5761.reset()
    ad5761.write_control_register()
    ad5761.write_update_dac_register(10)
    while True:
        time.sleep(1)
        ad5761.read_dac_register()
        print_summary()
    
    while True:
        sleep_time = 5
        # toggle_start_stop()
        toggle_start_stop()
        print_summary()
        time.sleep(sleep_time)
        toggle_cw_ccw()
        print_summary()
        time.sleep(sleep_time)
        toggle_cw_ccw()
        print_summary()
        time.sleep(sleep_time)
        toggle_start_stop()
        print_summary()
        time.sleep(sleep_time)
        
        # toggle_prime()
        toggle_prime()
        print_summary()
        time.sleep(1)
        toggle_prime()
        print_summary()
        time.sleep(1)
        
        # print summary
        toggle_start_stop()
        time.sleep(5)
        print_summary()
        
        toggle_start_stop()
        
        for i in range(101):
            ad5761.write_update_dac_register(i)
            print(f"Setting DAC to {i}%")
            time.sleep(1)
            print_summary()


# Run the main loop
if __name__ == "__main__":
    main()
