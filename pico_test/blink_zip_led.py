# control zip led at GPIO 0

import machine
import time
import array
from rp2 import PIO, StateMachine, asm_pio

# Setup a PIO state machine to drive the ZIP LEDs       
@asm_pio(sideset_init=PIO.OUT_LOW, out_shiftdir=PIO.SHIFT_LEFT, autopull=True, pull_thresh=24)
def ZIPLEDOutput():
    wrap_target()
    label("bitloop")
    out(x, 1)               .side(0)    [2]
    jmp(not_x, "do_zero")   .side(1)    [1]
    jmp("bitloop")          .side(1)    [4]
    label("do_zero")
    nop()                   .side(0)    [4]
    wrap()

# define onboard led
onboard_led = machine.Pin("LED", machine.Pin.OUT)

numLEDs = 5 # Set the number of ZIP LEDs (5 on a ZIP Stick)
# Create a state machine with the PIO program, outputting on GPIO 0
sm = StateMachine(0, ZIPLEDOutput, freq=8000000, sideset_base=machine.Pin(15))
# Start the state machine, it will wait for data on its FIFO
sm.active(1)
# Create a bytearray to store the LED data
led_data = array.array("I", [0 for _ in range(numLEDs)])

# function to generate the gradient of the rainbow, cycle through the entire color wheel space
# all led color will be the same
def full_colorspace_gradient(interval=1, time_ms=10, led_data=None, led_selected=None, start_color=0x000000):
    # If led_data or led_selected are not provided, initialize them
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    
    if led_selected is None:
        led_selected = list(range(numLEDs))
    
    # Precompute the color value limits for easier comparison
    max_color_value = 0xFFFFFF
    min_color_value = 0x000000
    
    for i in led_selected:
        # Increment the color by interval
        led_data[i] += interval
        # Check if the color value exceeds the max color value
        if led_data[i] > max_color_value:
            led_data[i] = min_color_value  # Reset to 0 if the max value is exceeded
        print(hex(led_data[i]))
    
    # Put the updated LED data to the state machine
    sm.put(led_data, 8)
    # Delay for the specified time in milliseconds
    time.sleep_ms(time_ms)
    
    return led_data[0]

# again the color format is 0xGGRRBB
def single_colorspace_gradient(interval=1, color_channel='red', time_ms=10, led_data=None, led_selected=None, max_intensity=1, directions=None):
    # If led_data or led_selected are not provided, initialize them
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    if led_selected is None:
        led_selected = list(range(numLEDs))
    if directions is None:
        directions = {i: 1 for i in led_selected}

    min_value = 0x000000
    # Calculate the bit shift based on the color channel
    if color_channel == 'green':
        shift = 16
        full_value = 0xFF0000
        max_value = int(0xFF * max_intensity) << shift
    elif color_channel == 'red':
        shift = 8
        full_value = 0x00FF00
        max_value = int(0xFF * max_intensity) << shift
    elif color_channel == 'blue':
        shift = 0
        full_value = 0x0000FF
        max_value = int(0xFF * max_intensity) << shift
    else:
        raise ValueError("Invalid color channel. Choose from 'red', 'green', or 'blue'.")

    for i in led_selected:
        # Update the green value based on the direction
        led_data[i] += directions[i] * (0x01 << shift) * interval
        
        # Reverse direction if limits are exceeded
        if (led_data[i] & full_value) >= max_value:
            led_data[i] = (led_data[i] & ~full_value) | full_value
            directions[i] = -1
        elif (led_data[i] & full_value) <= min_value:
            led_data[i] = (led_data[i] & ~full_value) | min_value
            directions[i] = 1

    # Put the updated LED data to the state machine
    sm.put(led_data, 8)
    # Delay for the specified time in milliseconds
    time.sleep_ms(time_ms)



# Set the ZIP LEDs to a single color
def color(R, G, B, led_data, led_selected):
    # cap the value to between 0 and 255
    R = max(0, min(R, 255))
    G = max(0, min(G, 255))
    B = max(0, min(B, 255))
    # set the color
    for i in led_selected:
        led_data[i] = (G << 16) + (R << 8) + B
    sm.put(led_data, 8)

# Turn off all the ZIP LEDs
def off():
    for i in range(numLEDs):
        led_data[i] = 0x000000
    sm.put(led_data, 8)

# Helper function to convert HSV to RGB
def hsv_to_rgb(h, s, v):
    if s == 0.0: return (v, v, v)
    i = int(h*6.0)  # assume int() truncates!
    f = (h*6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6
    if i == 0: return (v, t, p)
    if i == 1: return (q, v, p)
    if i == 2: return (p, v, t)
    if i == 3: return (p, q, v)
    if i == 4: return (t, p, v)
    if i == 5: return (v, p, q)

# Function to create a rainbow effect
def rainbow_effect(time_ms=10, led_data=None, led_selected=None, max_intensity=1, hue=0):
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    
    if led_selected is None:
        led_selected = list(range(numLEDs))

    hue = 0
    for i in led_selected:
        # Calculate the color for each LED based on its position
        led_hue = (hue + i * (1 / numLEDs)) % 1.0
        r, g, b = hsv_to_rgb(led_hue, 1.0, max_intensity)
        led_data[i] = (int(g * 255) << 16) + (int(r * 255) << 8) + int(b * 255)
        
    # Put the updated LED data to the state machine
    sm.put(led_data, 8)
    # Increment the hue for the next frame to create a moving rainbow effect
    hue = (hue + 0.01) % 1.0
    # Delay for the specified time in milliseconds
    time.sleep_ms(time_ms)
    
    return hue

def breathing_effect(time_ms=10, led_data=None, led_selected=None, max_intensity=1, color=(255, 255, 255), intensity=0, direction=1):
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    if led_selected is None:
        led_selected = list(range(numLEDs))

    scaled_intensity = (intensity / 255.0) * max_intensity
    r = int(color[0] * scaled_intensity)
    g = int(color[1] * scaled_intensity)
    b = int(color[2] * scaled_intensity)
    for i in led_selected:
        led_data[i] = (g << 16) + (r << 8) + b
    sm.put(led_data, 8)
    time.sleep_ms(time_ms)
    
    intensity += direction
    if intensity >= 255 or intensity <= 0:
        direction *= -1

    return intensity, direction

def blinking_effect(time_ms=500, led_data=None, led_selected=None, color=(255, 255, 255), state=True):
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    if led_selected is None:
        led_selected = list(range(numLEDs))

    for i in led_selected:
        if state:
            led_data[i] = (color[1] << 16) + (color[0] << 8) + color[2]
        else:
            led_data[i] = 0x000000
    sm.put(led_data, 8)
    time.sleep_ms(time_ms)
    
    return not state

def chase_effect(time_ms=100, led_data=None, led_selected=None, color=(255, 255, 255), index=0):
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    if led_selected is None:
        led_selected = list(range(numLEDs))

    for j in range(numLEDs):
        if j == index:
            led_data[j] = (color[1] << 16) + (color[0] << 8) + color[2]
        else:
            led_data[j] = 0x000000
    sm.put(led_data, 8)
    time.sleep_ms(time_ms)

    index = (index + 1) % numLEDs

    return index

import random

def sparkle_effect(time_ms=100, led_data=None, led_selected=None, probability=0.1, max_intensity=1):
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    if led_selected is None:
        led_selected = list(range(numLEDs))

    for i in led_selected:
        if random.random() < probability:
            r = int(random.random() * 255 * max_intensity)
            g = int(random.random() * 255 * max_intensity)
            b = int(random.random() * 255 * max_intensity)
            led_data[i] = (g << 16) + (r << 8) + b
        else:
            led_data[i] = 0x000000  # Turn off the LED
    sm.put(led_data, 8)
    time.sleep_ms(time_ms)

# Combined Chase and Rainbow Effect
def chase_rainbow_effect(time_ms=100, led_data=None, led_selected=None, max_intensity=1, hue=0, index=0):
    if led_data is None:
        led_data = array.array("I", [0 for _ in range(numLEDs)])
    if led_selected is None:
        led_selected = list(range(numLEDs))
    
    for j in range(numLEDs):
        # Calculate the color for the current position in the chase
        led_hue = (hue + j * (1 / numLEDs)) % 1.0
        r, g, b = hsv_to_rgb(led_hue, 1.0, max_intensity)
        if j == index:
            led_data[j] = (int(g * 255) << 16) + (int(r * 255) << 8) + int(b * 255)
        else:
            led_data[j] = 0x000000  # Turn off other LEDs
    sm.put(led_data, 8)
    time.sleep_ms(time_ms)

    index = (index + 1) % numLEDs
    hue = (hue + 0.01) % 1.0

    return hue, index

# Run the function
def run(interval_sec=10):
    off()
    led_data = array.array("I", [0 for _ in range(numLEDs)])
    led_selected = list(range(numLEDs))
    
    effects = [
        full_colorspace_gradient,
        single_colorspace_gradient,
        rainbow_effect,
        breathing_effect,
        breathing_effect,
        breathing_effect,
        blinking_effect,
        blinking_effect,
        blinking_effect,
        chase_effect,
        sparkle_effect,
        chase_rainbow_effect
    ]
    
    effect_index = 0
    effect_state = None
    hue = 0
    intensity = 0
    direction = 1
    blink_state = True
    chase_index = 0
    start_color = 0x000000
    
    start_time = time.ticks_ms()
    
    while True:
        current_time = time.ticks_ms()
        elapsed_time = time.ticks_diff(current_time, start_time)

        if elapsed_time >= interval_sec * 1000:
            effect_index = (effect_index + 1) % len(effects)
            start_time = current_time

        if effect_index == 0:
            print("running full_colorspace_gradient")
            start_color = full_colorspace_gradient(led_data=led_data, led_selected=led_selected, interval=1, time_ms=10, start_color=start_color)
        elif effect_index == 1:
            directions = effect_state if effect_state else {i: 1 for i in led_selected}
            print(f"running single_colorspace_gradient with directions: {directions}")
            effect_state = single_colorspace_gradient(max_intensity=1, color_channel='red', led_data=led_data, led_selected=led_selected, time_ms=10, directions=directions)
        elif effect_index == 2:
            print("running rainbow_effect")
            hue = rainbow_effect(led_data=led_data, led_selected=led_selected, max_intensity=0.1, time_ms=10, hue=hue)
        elif effect_index == 3 or effect_index == 4 or effect_index == 5:
            color = (255, 0, 0) if effect_index == 3 else (0, 255, 0) if effect_index == 4 else (0, 0, 255)
            print(f"running breathing_effect with intensity: {intensity}, direction: {direction}, color: {color}" )
            _, direction = breathing_effect(led_data=led_data, led_selected=led_selected, time_ms=10, color=color, intensity=intensity, direction=direction)
        elif effect_index == 6 or effect_index == 7 or effect_index == 8:
            color = (255, 0, 0) if effect_index == 6 else (0, 255, 0) if effect_index == 7 else (0, 0, 255)
            print(f"running blinking_effect with state: {blink_state}, color: {color}")
            blink_state = blinking_effect(led_data=led_data, led_selected=led_selected, time_ms=500, color=color, state=blink_state)
        elif effect_index == 9:
            chase_index = chase_effect(led_data=led_data, led_selected=led_selected, color=(255, 0, 0), index=chase_index)
        elif effect_index == 10:
            sparkle_effect(led_data=led_data, led_selected=led_selected, probability=0.1, max_intensity=0.1)
        elif effect_index == 11:
            print(f"running chase_rainbow_effect with index: {chase_index}, hue: {hue}")
            hue, chase_index = chase_rainbow_effect(led_data=led_data, led_selected=led_selected, max_intensity=0.05, hue=hue, index=chase_index)
        
        time.sleep_ms(10)
        onboard_led.toggle()
        
def run_chase_rainbow_effect(time_ms=1000):
    led_data = array.array("I", [0 for _ in range(numLEDs)])
    led_selected = list(range(numLEDs))
    hue = 0
    chase_index = 0
    off()
    while True:
        hue, chase_index = chase_rainbow_effect(time_ms=time_ms, led_data=led_data, led_selected=led_selected, max_intensity=0.05, hue=hue, index=chase_index)
        print(f"running chase_rainbow_effect with index: {chase_index}, hue: {hue}")
        onboard_led.toggle()
        
if __name__ == "__main__":
    run(interval_sec=10)