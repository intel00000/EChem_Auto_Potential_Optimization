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

# ADC definitions
ADC0 = ADC(0)
ADC1 = ADC(1)
ADC2 = ADC(2)

# internal temperature sensor definition
temp_sensor = ADC(4)
conversion_factor = 3.3 / (65535)

# Record the start time
start_time = time.ticks_cpu()


def adc_read_loop():
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

            # scale between 0 and 3300 mV
            ADC0_value_scaled = adc0_avg * conversion_factor * 1000
            ADC1_value_scaled = adc1_avg * conversion_factor * 1000
            ADC2_value_scaled = adc2_avg * conversion_factor * 1000

            # convert the internal temperature sensor value to Celsius and Fahrenheit
            temp_celsius = 27 - (temp_avg * conversion_factor - 0.706) / 0.001721
            temp_fahrenheit = (temp_celsius * 9 / 5) + 32

            # Calculate elapsed time
            elapsed_time = time.ticks_diff(time.ticks_cpu(), start_time) / 1000000

            # Print the values to the console
            print(
                f"adc0_avg: {ADC0_value_scaled:.3f} mV, adc1_avg: {ADC1_value_scaled:.3f} mV, adc2_avg: {ADC2_value_scaled:.3f} mV",
                end=", ",
            )
            print(
                f"RP2040 internal temperature in Celsius: {temp_celsius:.3f} C, in Fahrenheit: {temp_fahrenheit:.3f} F",
                end=", ",
            )
            print(
                f"elapsed time: {elapsed_time} s, cpu ticks: {time.ticks_cpu()}",
                end=", ",
            )
            # print the number of bytes of heap memory available for debugging
            total_mem = gc.mem_alloc() + gc.mem_free()
            print(
                f"Memory status (free/total): {gc.mem_free()}/{total_mem}",
            )


def test_max_poll_rate():
    print("test_max_poll_rate unoptimized")
    start = time.ticks_us()  # Start time in microseconds
    count: int = 0  # current count

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
    print("test_max_poll_rate_native native optimized")
    start = time.ticks_us()  # Start time in microseconds
    count: int = 0  # current count

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
    print("test_max_poll_rate_viper viper optimized")
    start: int = time.ticks_us()  # Start time in microseconds
    count: int = 0  # current count
    _TEST_SAMPLES: int = int(TEST_SAMPLES)

    adc1 = ADC1.read_u16
    while count < _TEST_SAMPLES:
        adc1()
        count += 1

    end: int = time.ticks_us()  # End time in microseconds
    elapsed_time_us: int = time.ticks_diff(end, start)

    return int(elapsed_time_us)


def main():
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

    adc_read_loop()


if __name__ == "__main__":
    main()
