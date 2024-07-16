# main.py

import pump_control_pico
import pwm_dma_led_fade

def main():
    pwm_dma_led_fade.main()
    pump_control_pico.main()

if __name__ == "__main__":
    main()