from machine import ADC, Pin
import time

led = Pin('LED', Pin.OUT)
ADC0 = ADC(Pin(26))
ADC1 = ADC(Pin(27))
ADC2 = ADC(Pin(28))

def run(time_interval_ms=200):
    while True:
        data = {
            "ADC0": ADC0.read_u16(),
            "ADC1": ADC1.read_u16(),
            "ADC2": ADC2.read_u16(),
            "GPIO23": Pin(23).value(),
            "pi pico timestamp": time.time()
        }
        print(data)
        led.toggle()
        time.sleep_ms(time_interval_ms)

if __name__ == "__main__":
    run(time_interval_ms=200)