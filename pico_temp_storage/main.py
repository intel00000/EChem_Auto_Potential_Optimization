# main.py

import pump_control_pico
import pwm_dma_led_fade
import array
from uctypes import addressof


def main():
    fade_buffer = array.array(
        "I",
        [(i * i) << 16 for i in range(0, 256, 1)]
        + [(i * i) << 16 for i in range(255, -1, -1)],
    )
    fade_buffer_addr = addressof(fade_buffer)
    pwm_dma_led_fade.main(fade_buffer=fade_buffer, fade_buffer_addr=fade_buffer_addr)

    pump_control_pico.main()


if __name__ == "__main__":
    main()
