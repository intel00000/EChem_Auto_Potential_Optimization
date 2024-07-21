from machine import Pin, PWM, mem32, ADC
from uctypes import addressof, struct, UINT32
import rp2
import array
import time


# No cycle version of the PWM DMA fade example
def pwm_dma_led_fade(
    fade_buffer_addr=None,
    fade_buffer_len=512,
    secondary_config_data_addr=None,
    frequency=10240,
) -> (rp2.DMA, rp2.DMA):
    # Set up PWM on the onboard LED pin (GPIO 25)
    led_pin = Pin("LED")
    pwm = PWM(led_pin)
    pwm.deinit()  # Deinitialize the PWM channel to release the pin for PWM use
    pwm.init()  # Reinitialize the PWM channel to use the pin

    # setup the PWM channel and register addresses
    PWM_BASE = 0x40050000  # PWM base address
    PWM_CH_OFFSET = 0x14  # PWM channel block offset
    PWM_CSR = 0x00  # PWM control and status offset
    PWM_DIV = 0x04  # PWM frequency divisor offset
    PWM_CC = 0x0C  # PWM Counter compare values offset
    PWM_TOP = 0x10  # PWM Counter wrap value offset

    # the onboard LED on the RP2040 is connected to PWM slice 4, at 4B
    pwm_ch = PWM_BASE + (PWM_CH_OFFSET * 4)
    pwm_cc = pwm_ch + PWM_CC
    mem32[pwm_cc] = 0x0  # clear the pwm_cc value first

    # Set the PWM divisor to slow down the frequency for smooth fading
    # mem32[pwm_ch + PWM_DIV] = (0x1 << 4)  # Set clock divider to 8
    # or set it by frequency
    pwm.freq(frequency)

    mem32[pwm_ch + PWM_CSR] |= (
        1 << 1
    ) | 1  # Enable phase-correct modulation and enable PWM

    # Create the fade buffer with gamma correction
    if fade_buffer_addr is None:
        fade_buffer = array.array(
            "I",
            [(i * i) << 16 for i in range(0, 256, 1)]
            + [(i * i) << 16 for i in range(255, -1, -1)],
        )
        fade_buffer_addr = addressof(fade_buffer)
        fade_buffer_len = len(fade_buffer)

    # Set up DMA channels
    dma_main = rp2.DMA()
    dma_secondary = rp2.DMA()
    DMA_BASE = 0x50000000
    DMA_CH = 0x40
    DREQ_PWM_WRAP4 = 28
    print("Main DMA channel:", dma_main.channel)
    print("Secondary DMA channel:", dma_secondary.channel)

    # Configure main DMA to write to the PWM compare register
    main_ctrl = dma_main.pack_ctrl(
        size=2,  # Transfer size: 0=byte, 1=half word, 2=word
        inc_read=True,  # Increment the read address
        inc_write=False,  # Do not increment the write address
        treq_sel=DREQ_PWM_WRAP4,  # Select the PWM DREQ for PWM slice 4
        ring_size=0,  # Disable wrapping
        ring_sel=False,  # Apply wrap to read address
        chain_to=dma_main.channel,  # Disable chaining
        irq_quiet=True,  # Do not generate interrupts
        sniff_en=False,  # Do not enable read sniffing
        write_err=True,  # Clear a previously reported write error.
        read_err=True,  # Clear a previously reported read error.
    )

    # Configure the main DMA transfer
    dma_main.config(
        read=fade_buffer_addr,
        write=pwm_cc,
        count=fade_buffer_len,  # Number of words to transfer
        ctrl=main_ctrl,
        trigger=False,
    )

    # Define the DMA control register layout
    DMA_CTRL_LAYOUT = {
        "READ_ADDR": 0x00 | UINT32,
    }
    # Prepare the secondary configuration data struct
    if secondary_config_data_addr is None:
        secondary_config_data = bytearray(16)
        secondary_config_data_addr = addressof(secondary_config_data)
    secondary_config = struct(secondary_config_data_addr, DMA_CTRL_LAYOUT)
    secondary_config.READ_ADDR = fade_buffer_addr

    # Configure the secondary DMA to reconfigure the main DMA
    secondary_ctrl = dma_secondary.pack_ctrl(
        size=2,  # Transfer size: 0=byte, 1=half word, 2=word
        inc_read=False,  # Do not increment the read address
        inc_write=False,  # Do not increment the write address
        treq_sel=0x3F,  # Permanent request, for unpaced transfers
        ring_size=0,  # Disable wrapping
        ring_sel=False,  # Apply wrap to read address
        chain_to=dma_main.channel,  # Chain to main DMA
        irq_quiet=True,  # Do not generate interrupts
        sniff_en=False,  # Do not enable read sniffing
        write_err=True,  # Clear a previously reported write error.
        read_err=True,  # Clear a previously reported read error.
    )

    # Configure the secondary DMA transfer
    dma_secondary.config(
        read=secondary_config_data_addr,
        write=DMA_BASE
        + dma_main.channel * DMA_CH,  # Write to the main DMA channel's registers
        # Number of registers to write (READ_ADDR, WRITE_ADDR, TRANS_COUNT, CTRL_TRIG)
        count=4,
        ctrl=secondary_ctrl,
        trigger=False,
    )

    print("DMA configured with read address:", fade_buffer_addr)
    print("DMA configured with write address:", pwm_cc)
    print("DMA transfer count:", fade_buffer_len)

    # Start the DMA transfer
    dma_main.active(1)
    print("DMA transfer started")

    return dma_main, dma_secondary


def adjust_pwm_frequency_from_adc(adc_pin):
    adc = ADC(adc_pin)

    # define the onboard LED pin (GPIO 25)
    led_pin = Pin("LED")
    pwm = PWM(led_pin)

    max_frequency = 512  # Maximum frequency of the PWM signal
    min_frequency = 128  # Minimum frequency of the PWM signal

    while True:
        adc_value = adc.read_u16()  # Read the ADC value
        # print the adc value

        # Map the ADC value to the frequency range
        frequency = int(
            min_frequency + (adc_value / 65535) * (max_frequency - min_frequency)
        )
        # change the frequency
        pwm.freq(frequency)

        print(f"ADC value: {adc_value}, Adjusted frequency: {frequency} Hz")
        # Adjust the frequency every 1 second for demonstration purposes
        time.sleep(1)


def main(fade_buffer_addr, fade_buffer_len, secondary_config_data_addr, frequency):
    pwm_dma_led_fade(
        fade_buffer_addr, fade_buffer_len, secondary_config_data_addr, frequency
    )


if __name__ == "__main__":
    main(None, None, None, 512)
