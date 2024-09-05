# scan_i2c.py

from machine import I2C, Pin


# Function to scan I2C bus and return the list of addresses
def i2c_scan(i2c):
    print("Scanning I2C bus...")
    devices = i2c.scan()
    if len(devices) == 0:
        print("No I2C devices found.")
    else:
        print("I2C devices found:", [hex(device) for device in devices])
    return devices


if __name__ == "__main__":
    # Initialize I2C
    i2c = I2C(0, scl=Pin(1), sda=Pin(0))

    # Scan the I2C bus
    devices = i2c_scan(i2c)
    if len(devices) == 0:
        raise Exception("No I2C devices found. Please check your connections.")
