from machine import SoftSPI, SPI, Pin
import time

# datasheet: https://www.analog.com/media/en/technical-documentation/data-sheets/ad5761_5721.pdf
# Everytime a 24-bit command is sent/received
# the first 4 bits XXX0, where X is don't care, we set it to 0
CMD_FIRST_4_BITS = 0x0
# Input Shift Register Commands, these are at DB19-DB16
CMD_NOP = 0x0
CMD_WR_TO_INPUT_REG = 0x1
CMD_UPDATE_DAC_REG_FROM_INPUT_REG = 0x2
CMD_WR_UPDATE_DAC_REG = 0x3
CMD_WR_CTRL_REG = 0x4
CMD_NOP_ALT_1 = 0x5
CMD_NOP_ALT_2 = 0x6
CMD_SW_DATA_RESET = 0x7
CMD_RESERVED = 0x8
CMD_DIS_DAISY_CHAIN = 0x9
CMD_RD_INPUT_REG = 0xA
CMD_RD_DAC_REG = 0xB
CMD_RD_CTRL_REG = 0xC
CMD_NOP_ALT_3 = 0xD
CMD_NOP_ALT_4 = 0xE
CMD_SW_FULL_RESET = 0xF

# Define the pins for SPI connection
ad5761_sdo = Pin(4)
ad5761_sclk = Pin(6)
ad5761_sdi = Pin(7)

# define alert pin
# Active Low Alert. This pin is asserted low when the die temperature exceeds approximately 150°C, or
# when an output short circuit or a brownout occurs. This pin is also asserted low during power-up, a
# full software reset, or a hardware reset, for which a write to the control register asserts the pin
# high.
ad5761_alert = Pin(12, Pin.IN, Pin.PULL_UP)

# Set up the SPI interface
spi = SPI(
    id=0,
    baudrate=250_000,
    polarity=1,
    phase=0,
    firstbit=1,
    sck=ad5761_sclk,
    mosi=ad5761_sdi,
    miso=ad5761_sdo,
)

ad5761_sync = Pin(5, Pin.OUT, value=1)

# this method adapter to the actual timing of the AD5761
def write_spi(tx: bytes):
    ad5761_sync(0)
    spi.write(tx)
    ad5761_sync(1)
    
def read_into_spi(rx: bytearray):
    ad5761_sync(0)
    spi.readinto(rx)
    ad5761_sync(1)

def print_binary(data):
    # Convert each byte to a binary string with 8 bits, then separate the middle 4 bits with a space
    return " ".join(f"{byte:08b}"[:4] + " " + f"{byte:08b}"[4:] for byte in data)

print(f"SPI: {spi}, Alert: {ad5761_alert.value()}")

time.sleep(1)

# Step 1: Perform a Software Full Reset
# reset command: 0xEF 00 00
# Assembling the reset command
reset_cmd = bytearray(3)
reset_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_SW_FULL_RESET
write_spi(reset_cmd)  # Write 24 bits

# Print the reset buffer to see the content in full binary
print("------------------------------------")
print(f"Software Full Reset Issued, Reset Command: {print_binary(reset_cmd)}, Alert pin: {ad5761_alert.value()}")

time.sleep(1)

# Step 2: Write to the control register
# Format: DB[23:21] DB20 DB[19:16] DB[15:11] DB[10:9] DB8 DB7 DB6 DB5 DB[4:3]   DB[2:0]
#         XXX       0    0100      XXXXX     CV[1:0]  OVR B2C ETS 0   PV[1:0]   RA[2:0]
# X mean don't care
# CV[1:0] CLEAR voltage selection, 00: zero scale, 01: midscale, 10 or 11: full scale.
# OVR 5% overrange, 0: 5% overrange disabled, 1: 5% overrange enabled.
# B2C Bipolar range. 0: DAC input for bipolar output range is straight binary coded., 1: DAC input for bipolar output range is twos complement coded
# ETS Thermal shutdown alert. The alert may not work correctly if the device powers on with temperature conditions >150°C (greater than the maximum rating of the device). 0: internal digital supply does not power down if die temperature exceeds 150°C. 1: internal digital supply powers down if die temperature exceeds 150°C.
# PV[1:0] Power-up voltage. 00: zero scale, 01: midscale, 10, 11: full scale.
# RA[2:0] Output range. Before an output range configuration, the device must be reset.
# 000: −10 V to +10 V. 001: 0 V to +10 V. 010: −5 V to +5 V. 011: 0 V to 5 V. 100: −2.5 V to +7.5 V. 101: −3 V to +3 V. 110: 0 V to 16 V. 111: 0 V to 20 V.

# we want full scale, no overrange, straight binary, thermal shutdown, full scale power-up, and 0 to 10V output range
# 0b 0000 0100 0000 0110 0101 1001
# which is 0x040659
# Assembling the write command
write_cmd = bytearray(3)
write_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_WR_CTRL_REG
write_cmd[1] = 0x06
write_cmd[2] = 0x59

# Write to the control register
write_spi(write_cmd)  # Write 24 bits

# Print the write buffer to see the content in full binary
print("------------------------------------")
print(f"Write to Control Register, Command: {print_binary(write_cmd)}, Alert pin: {ad5761_alert.value()}")

time.sleep(1)

# Step 3: Readback the control register
# Assembling the read command, which is 0000 1100 0000 0000 0000 0000
write_cmd = bytearray(3)
write_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_RD_CTRL_REG
read_buf = bytearray(3)  # Buffer for reading back

# first method, we write the read command and then read the response
write_spi(write_cmd)  # Write 24 bits
# Read 24 bits while writing 0x00 which is NOP
read_into_spi(read_buf)  # Read 24 bits

# Print the read buffer to see the content in full binary
print("------------------------------------")
print(f"Read Control Register, Sent: {print_binary(write_cmd)}, Received: {print_binary(read_buf)}, Alert pin: {ad5761_alert.value()}")

time.sleep(1)

# step 4, write and update the DAC register, the value is 16bit
# Assembling the write command
write_cmd = bytearray(3)
write_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_WR_UPDATE_DAC_REG
# the percentage define the percentage of the voltage output
percentage = 25
# convert the percentage to 16bit
value = int(0xFFFF * percentage / 100)
write_cmd[1] = value >> 8
write_cmd[2] = value & 0xFF

# Write to the control register
write_spi(write_cmd)  # Write 24 bits

# Print the write buffer to see the content in full binary
print("------------------------------------")
print(f"Write to DAC Register with {percentage}% of the voltage, command: {print_binary(write_cmd)}, Alert pin: {ad5761_alert.value()}")

time.sleep(1)

# step 5, read back the DAC register
# Assembling the read command, which is 0000 1011 0000 0000 0000 0000
write_cmd = bytearray(3)
write_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_RD_DAC_REG
read_buf = bytearray(3)  # Buffer for reading back

# first method, we write the read command and then read the response
write_spi(write_cmd)  # Write 24 bits
# Read 24 bits while writing 0x00 which is NOP
read_into_spi(read_buf)  # Read 24 bits
# converted the read buffer to 16bit
read_value = (read_buf[1] << 8) | read_buf[2]

# Print the read buffer to see the content in full binary
print("------------------------------------")
print(f"Read DAC Register, Sent: {print_binary(write_cmd)}, Received: {print_binary(read_buf)}, Alert: {ad5761_alert.value()}")
print(f"Read Value: {read_value}, percentage: {read_value / 0xFFFF * 100}%")

time.sleep(1)


# now we will loop from 0 to 100% in 10% increment every 3 seconds, read the DAC register and print the value
while True:
    for percentage in range(0, 101, 1):
        # Assembling the write command
        write_cmd = bytearray(3)
        write_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_WR_UPDATE_DAC_REG
        # the percentage define the percentage of the voltage output
        value = int(0xFFFF * percentage / 100)
        write_cmd[1] = value >> 8
        write_cmd[2] = value & 0xFF

        # Write to the control register
        write_spi(write_cmd)  # Write 24 bits

        # Print the write buffer to see the content in full binary
        print("------------------------------------")
        print(f"Assembled Write Command: {print_binary(write_cmd)}")
        print(f"Write to DAC Register with {percentage}% of the voltage")

        # Assembling the read command, which is 0000 1011 0000 0000 0000 0000
        write_cmd = bytearray(3)
        write_cmd[0] = CMD_FIRST_4_BITS << 4 | CMD_RD_DAC_REG
        read_buf = bytearray(3)  # Buffer for reading back

        # first method, we write the read command and then read the response
        write_spi(write_cmd)  # Write 24 bits
        # Read 24 bits while writing 0x00 which is NOP
        read_into_spi(read_buf)  # Read 24 bits
        # converted the read buffer to 16bit
        read_value = (read_buf[1] << 8) | read_buf[2]

        # Print the read buffer to see the content in full binary
        print("------------------------------------")
        print(f"Read DAC Register, Sent: {print_binary(write_cmd)}, Received: {print_binary(read_buf)}, Alert: {ad5761_alert.value()}")
        print(f"Read Value: {read_value}, percentage: {read_value / 0xFFFF * 100}%")