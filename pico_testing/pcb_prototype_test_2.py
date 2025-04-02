from machine import Pin, SPI, ADC
import time
from AD5761 import AD5761, ad5761r_dev, AD5761R_RANGES, AD5761R_SCALES

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

# Initialize AD5761 DAC
ad5761 = AD5761(spi, cs_pin=5)

# Device settings
dev_settings = ad5761r_dev(
    ra=AD5761R_RANGES["0v_to_p_5v"],  # Output range is 0V to +10V
    pv=AD5761R_SCALES["zero"],
    cv=AD5761R_SCALES["zero"],
    int_ref_en=True,
    exc_temp_sd_en=True,
    b2c_range_en=False,
    ovr_en=False,
)


# Function to write to the control register
def write_control_register():
    ad5761.config(dev_settings.settings)


# Function to write and update the DAC register with a 16-bit value
def write_and_update_dac(value):
    ad5761.write_update_dac_register(value)


# Function to read back from the DAC register
def read_dac():
    return ad5761.register_readback("dac")


# Function to set DAC voltage
def set_dac_voltage(voltage):
    if 0 <= voltage <= 10:
        dac_value = int((voltage / 10.0) * 65535)
        # convert to 16-bit value
        write_and_update_dac(dac_value)
        print(f"Set DAC to {voltage}V -> DAC value: {dac_value}")


# Toggle output functions
def toggle_start_stop():
    start_stop_pin.value(not start_stop_pin.value())
    print(f"Start/Stop Pin toggled to {start_stop_pin.value()}")
    print(f"Motor Running: {'Yes' if motor_running_pin.value() == 0 else 'No'}")


def toggle_cw_ccw():
    cw_ccw_pin.value(not cw_ccw_pin.value())
    print(f"CW/CCW Pin toggled to {cw_ccw_pin.value()}")
    print(f"Motor Running: {'Yes' if motor_running_pin.value() == 0 else 'No'}")


def toggle_prime():
    prime_pin.value(not prime_pin.value())
    print(f"Prime Pin toggled to {prime_pin.value()}")
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
    write_and_update_dac(0x0000)
    voltage = 0.0
    step = 1.0
    
    while True:
        # toggle_start_stop()
        toggle_start_stop()
        time.sleep(5)
        toggle_start_stop()
        
        # toggle_cw_ccw()
        toggle_cw_ccw()
        time.sleep(5)
        toggle_cw_ccw()
        
        # toggle_prime()
        toggle_prime()
        time.sleep(5)
        toggle_prime()
        
        # print summary
        toggle_start_stop()
        print_summary()
        
        # setting a DAC value, incrementing by 0.1V every 5 seconds
        if voltage <= 10.0:
            set_dac_voltage(voltage)  # Set DAC to the specified voltage
            time.sleep(1)  # Wait for 1 second before incrementing
            voltage += step
        time.sleep(10)


# Run the main loop
if __name__ == "__main__":
    main()
