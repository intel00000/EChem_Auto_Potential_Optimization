from machine import Pin, PWM
import time

servo = PWM(Pin(16))
servo.freq(50)

def angle_to_duty(angle):
    # Map 0-180 degrees to the duty cycle range for the servo
    # This range may need to be adjusted based on your servo specifications
    min_duty = 1638  # Duty cycle for 0 degrees
    max_duty = 8192  # Duty cycle for 180 degrees
    return int((angle / 180.0) * (max_duty - min_duty) + min_duty)

angles = [0, 90, 180, 90]  # Angles to move to

while True:
    for angle in angles:
        duty = angle_to_duty(angle)
        servo.duty_u16(duty)
        print(f"Angle: {angle}, Duty cycle: {duty}")
        time.sleep(1)