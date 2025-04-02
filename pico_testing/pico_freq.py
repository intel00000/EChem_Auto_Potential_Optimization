# Pico MicroPython: gated frequency measurement
# See https://iosoft.blog/picofreq_python for description
#
# Copyright (c) 2021 Jeremy P Bentham
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# v0.03 JPB 19/8/23 Renamed rp_pwm_counter.py to pico_freq.py
#                   Added counter gating for frequency measurment
# v0.04 JPB 20/8/23 Switched input from pin 7 to pin 3
# v0.05 JPB 20/8/23 Corrected DMA initialisation

import machine, rp2, array, utime
import time, pico_devices as devs

PWM_OUT_PIN, PWM_IN_PIN = 4, 3
GATE_TIMER_PIN          = 0

# Frequency gate settings
GATE_PRESCALE = 250         # 125e6 / 250 = 500 kHz
GATE_WRAP = 125000          # 500 kHz / 125000 = 4 Hz (250 ms)
GATE_FREQ = 125e6 / (GATE_PRESCALE * GATE_WRAP)
GATE_TIME_MSEC = 1000 / GATE_FREQ

gate_data = devs.array32(1) # Gate DMA data

# Initialise PWM as a pulse counter (gpio must be odd number)
def pulse_counter_init(pin, rising=True):
    if pin & 1 == 0:
        print("Error: pulse counter must be on add GPIO pin")
    devs.gpio_set_function(pin, devs.GPIO_FUNC_PWM)
    ctr = devs.PWM(pin)
    ctr.set_clkdiv_mode(devs.PWM_DIV_B_RISING if rising else devs.PWM_DIV_B_FALLING)
    ctr.set_clkdiv(1)
    return ctr

# Get value of pulse counter
def pulse_counter_value(ctr):
    return ctr.get_counter()

# Initialise PWM as a gate timer
def gate_timer_init(pin):
    pwm = devs.PWM(pin)
    pwm.set_clkdiv_int_frac(GATE_PRESCALE, 0)
    pwm.set_wrap(int(GATE_WRAP/2 - 1))
    pwm.set_chan_level(pwm.gpio_to_channel(pin), int(GATE_WRAP/4))
    pwm.set_phase_correct(True)
    return pwm

# Initialise gate timer DMA
def gate_dma_init(ctr, gate):
    dma = devs.DMA()
    dma.set_transfer_data_size(devs.DMA_SIZE_32)
    dma.set_read_increment(False)
    dma.set_write_increment(False)
    dma.set_dreq(gate.get_dreq())
    gate_data[0] = ctr.slice.CSR_REG
    dma.set_read_addr(devs.addressof(gate_data))
    dma.set_write_addr(ctr.get_csr_address())
    return dma

# Start frequency measurment using gate
def freq_gate_start(ctr, gate, dma):
    ctr.set_ctr(0)
    gate.set_ctr(0)
    dma.set_trans_count(1, True)
    ctr.set_enables((1<<ctr.slice_num) | (1<<gate.slice_num), True)

# Stop frequency measurment using gate
def freq_gate_stop(ctr, gate, dma):
    gate_pwm.set_enabled(False)
    dma.abort()
    
if __name__ == "__main__":
    # Generate test PWM signal on PWM_OUTPUT_PIN
    pwm_test = machine.PWM(PWM_OUT_PIN)
    pwm_test.freq(625000)  # Set the desired frequency in Hz
    pwm_test.duty_u16(32768)  # Set duty cycle to 50%
    print(f"Generated PWM Frequency: {pwm_test.freq()} Hz")
    
    counter_pwm = pulse_counter_init(PWM_IN_PIN)
    gate_pwm = gate_timer_init(0)
    gate_dma = gate_dma_init(counter_pwm, gate_pwm)
    
    while True:
        freq_gate_start(counter_pwm, gate_pwm, gate_dma)
        time.sleep(0.3)
        count = pulse_counter_value(counter_pwm)
        freq_gate_stop(counter_pwm, gate_pwm, gate_dma)
        freq = count / GATE_TIME_MSEC
        print("Gate %f ms, count %u, freq %f kHz" % (GATE_TIME_MSEC, count, freq))