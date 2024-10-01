from machine import Pin, I2C, ADC
import time
import gc

# for optimization, follow https://docs.micropython.org/en/v1.9.3/pyboard/reference/speed_python.html
# Use the micropython decorator to emit native code for the function

# define the number of test samples for max poll rate test
TEST_SAMPLES = const(100_000)
# Number of samples to average, for boxcar filtering
NUM_SAMPLES = const(1_000)

# Accumulators for boxcar filtering
adc0_sum = 0
adc1_sum = 0
adc2_sum = 0
temp_sum = 0
# Averages for boxcar filtering
adc0_avg = 0
adc1_avg = 0
adc2_avg = 0
temp_avg = 0
# a count for slower console output
count = 0

# I2C address of the Sparkfun Serial 7 Segment
s7sAddress = 0x71
i2c = I2C(0, scl=Pin(21), sda=Pin(20))

# ADC definitions
ADC0 = ADC(0)
ADC1 = ADC(1)
ADC2 = ADC(2)

# internal temperature sensor definition
temp_sensor = ADC(4)
conversion_factor = 3.3 / (65535)

# Record the start time
start_time = time.ticks_cpu()

@micropython.viper
def s7s_send_string_i2c(toSend):
    data = bytearray(4)
    for i in range(4):
        data[i] = ord(toSend[i])
    i2c.writeto(s7sAddress, data)

def clear_display_i2c():
    i2c.writeto(s7sAddress, b'\x76')

def set_brightness_i2c(value: int):
    # the value should be between 0 and 100, capped in the function
    if value > 100:
        value = 100
    if value < 0:
        value = 0
    i2c.writeto(s7sAddress, b'\x7A' + bytes([value]))

def set_decimals_i2c(decimals):
    i2c.writeto(s7sAddress, b'\x77' + bytes([decimals]))

available_baud_rates = [2400, 4800, 9600, 14400, 19200, 38400, 57600, 76800, 115200, 250000, 500000, 1000000]
def set_baud_rate_i2c(baud_rate: int):
    # select the closest baud rate
    if baud_rate not in available_baud_rates:
        baud_rate = min(available_baud_rates, key=lambda x:abs(x-baud_rate))
        
    # we are sending the index of the baud rate in the list
    baud_rate_index = available_baud_rates.index(baud_rate)
    i2c.writeto(s7sAddress, b'\x7F' + bytes([baud_rate_index]))

def serial_display_setup():
    # set baud rate to 57600
    set_baud_rate_i2c(57600)
    # clear the display
    clear_display_i2c()
    s7s_send_string_i2c("-HI-")
    set_decimals_i2c(0b00111111)  # Turn on all decimals, colon, apos

    set_brightness_i2c(0)  # Lowest brightness
    time.sleep(1)
    set_brightness_i2c(100)  # High brightness
    time.sleep(1)
    set_brightness_i2c(10)  # low brightness
    time.sleep(1)

    clear_display_i2c()

def serial_display_loop():
    global adc0_sum, adc1_sum, adc2_sum, temp_sum, adc0_avg, adc1_avg, adc2_avg, temp_avg, count, start_time
    
    while True:
        adc0_sum += ADC0.read_u16()
        adc1_sum += ADC1.read_u16()
        adc2_sum += ADC2.read_u16()
        temp_sum += temp_sensor.read_u16()
        count += 1
        
        if count >= NUM_SAMPLES:
            adc0_avg = adc0_sum / NUM_SAMPLES
            adc1_avg = adc1_sum / NUM_SAMPLES
            adc2_avg = adc2_sum / NUM_SAMPLES
            temp_avg = temp_sum / NUM_SAMPLES
            
            adc0_sum = 0
            adc1_sum = 0
            adc2_sum = 0
            temp_sum = 0
            count = 0
            
            # scale between 0 and 9999
            ADC1_value_scaled = adc1_avg * 9999 / 65535
            # convert to integer, format the string to 4 digits, send the string to the display
            s7s_send_string_i2c("{:4d}".format(int(ADC1_value_scaled)))
            
            # convert the internal temperature sensor value to Celsius and Fahrenheit
            temp_celsius = 27 - (temp_avg * conversion_factor - 0.706) / 0.001721
            temp_fahrenheit = (temp_celsius * 9 / 5) + 32
            
            # Calculate elapsed time
            elapsed_time = time.ticks_diff(time.ticks_cpu(), start_time) / 1000000
            
            # Print the values to the console
            print(f"adc1_avg raw: {adc1_avg:.3f}, adc1_avg scaled: {ADC1_value_scaled:.3f}, adc2_avg raw: {adc2_avg:.3f}, adc0_avg raw: {adc0_avg:.3f}", end=", ")
            print(f"temp_avg raw: {temp_avg:.3f}, RP2040 internal temperature in Celsius: {temp_celsius:.3f} C, in Fahrenheit: {temp_fahrenheit:.3f} F", end=", ")
            print(f"elapsed time: {elapsed_time} s, cpu ticks: {time.ticks_cpu()}", end=", ")
            # print the number of bytes of heap memory available for debugging
            print(f"Free heap: {gc.mem_free()} bytes, Allocated heap: {gc.mem_alloc()} bytes")
            
def run_serial_display():
    global i2c, s7sAddress
    # give time for i2c initialization
    time.sleep_ms(100)
    s7sAddress  = i2c.scan()[0]
    
    serial_display_setup()
    # Sets digit 4 decimal on, see https://github.com/sparkfun/Serial7SegmentDisplay/wiki/Special-Commands#decimal
    set_decimals_i2c(0b00001000)
    
    serial_display_loop()

def test_max_poll_rate():
    print('test_max_poll_rate unoptimized')
    start = time.ticks_us()  # Start time in microseconds
    count: int = 0 # current count
    
    adc1 = ADC1.read_u16
    while count < TEST_SAMPLES:
        adc1()
        count += 1
        
    end = time.ticks_us()  # End time in microseconds
    elapsed_time_us = time.ticks_diff(end, start)
    elapsed_time_s = elapsed_time_us / 1_000_000  # Convert to seconds
    poll_rate = TEST_SAMPLES / elapsed_time_s  # Poll rate in samples per second

    print(f"Max poll rate: {poll_rate:.2f} samples per second")
    print(f"Elapsed time for {TEST_SAMPLES} samples: {elapsed_time_s:.2f} seconds")
    
@micropython.native
def test_max_poll_rate_native():
    print('test_max_poll_rate_native native optimized')
    start = time.ticks_us()  # Start time in microseconds
    count: int = 0 # current count
    
    adc1 = ADC1.read_u16
    while count < TEST_SAMPLES:
        adc1()
        count += 1
        
    end = time.ticks_us()  # End time in microseconds
    elapsed_time_us = time.ticks_diff(end, start)
    elapsed_time_s = elapsed_time_us / 1e6  # Convert to seconds
    poll_rate = TEST_SAMPLES / elapsed_time_s  # Poll rate in samples per second

    print(f"Max poll rate: {poll_rate:.2f} samples per second")
    print(f"Elapsed time for {TEST_SAMPLES} samples: {elapsed_time_s:.2f} seconds")

@micropython.viper
def test_max_poll_rate_viper() -> int:
    print('test_max_poll_rate_viper viper optimized')
    start: int = time.ticks_us()  # Start time in microseconds
    count: int = 0 # current count
    _TEST_SAMPLES: int = int(TEST_SAMPLES)
    
    adc1 = ADC1.read_u16
    while count < _TEST_SAMPLES:
        adc1()
        count += 1
        
    end: int = time.ticks_us()  # End time in microseconds
    elapsed_time_us: int = time.ticks_diff(end, start)
    
    return int(elapsed_time_us)
    
if __name__ == "__main__":
    test_max_poll_rate()
    time.sleep_ms(20)
    test_max_poll_rate_native()
    time.sleep_ms(20)
    
    elapsed_time_us = test_max_poll_rate_viper()
    elapsed_time_s = elapsed_time_us / 1e6  # Convert to seconds
    poll_rate = TEST_SAMPLES / elapsed_time_s  # Poll rate in samples per second
    print(f"Max poll rate: {poll_rate:.2f} samples per second")
    print(f"Elapsed time for {TEST_SAMPLES} samples: {elapsed_time_s:.2f} seconds")
    time.sleep_ms(20)
    
    run_serial_display()