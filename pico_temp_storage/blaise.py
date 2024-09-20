print("blaise")

from machine import SPI, Pin
import struct
import time

spi = SPI(0, baudrate=250_000, polarity=1, phase=0, firstbit=1)
cs = Pin(22, mode=Pin.OUT, value=1)


def zfill(s, n, char):
    num = n - len(s)
    return char*num + s


def pprint_bin(b: bytes) -> str:
    out = ""
    for char in b:
        out += " 0b"
        char = bin(char)[2:]
        char = zfill(char, 8, "0")
        out += char[:4] + "_" + char[4:]
    return out.strip()

def print_binary(data: bytes) -> str:
    # Convert each byte to a binary string with 8 bits, then separate the middle 4 bits with a space
    return " ".join(f"{byte:08b}"[:4] + " " + f"{byte:08b}"[4:] for byte in data)

time.sleep(1)

def write_spi(tx: bytes):
    time.sleep(0.1)
    cs(0)
    time.sleep(0.1)
    spi.write(tx)
    time.sleep(0.1)
    cs(1)
    time.sleep(0.1)

address = 0b1111  # Software full reset
data = 0x0000
tx = struct.pack(">bh", address, data)
print("full reset", print_binary(tx))
write_spi(tx)

address = 0b0100  # Write to control register
data = 0b0000000101000  # haven't thought about these settings at all
tx = struct.pack(">bh", address, data)
print("control register", print_binary(tx))
write_spi(tx)

address = 0b0011  # Write to and update DAC register
data = 0xFFFF
tx = struct.pack(">bh", address, data)
print("data register", print_binary(tx))
write_spi(tx)

print("finished")
