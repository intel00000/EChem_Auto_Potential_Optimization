from machine import Pin
import neopixel
import time
import math

# create a NeoPixel object on pin 25 with 1 pixel
pin = Pin(25, Pin.OUT)
np = neopixel.NeoPixel(pin=pin, n=1, bpp=3, timing=1)


def hsv_to_rgb(h, s, v):
    """Convert HSV color space to RGB color space"""
    h = float(h)
    s = float(s)
    v = float(v)
    h60 = h / 60.0
    h60f = math.floor(h60)
    hi = int(h60f) % 6
    f = h60 - h60f
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)

    r, g, b = 0, 0, 0
    if hi == 0:
        r, g, b = v, t, p
    elif hi == 1:
        r, g, b = q, v, p
    elif hi == 2:
        r, g, b = p, v, t
    elif hi == 3:
        r, g, b = p, q, v
    elif hi == 4:
        r, g, b = t, p, v
    elif hi == 5:
        r, g, b = v, p, q

    return int(r * 255), int(g * 255), int(b * 255)


def rainbow_cycle(wait):
    for j in range(256):
        for i in range(1):
            pixel_index = (i * 256 // 1) + j
            r, g, b = hsv_to_rgb(pixel_index % 256, 1.0, 1.0)
            np[i] = (r, g, b)
        np.write()
        time.sleep(wait)


while True:
    rainbow_cycle(0.01)
