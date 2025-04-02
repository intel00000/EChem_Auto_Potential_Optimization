from machine import I2C, Pin
import time

DEFAULT_ADDRESS = 0x70
DEFAULT_NOTHING_ATTACHED = 0xFF

# Define constants for segment bits
SEG_A = 0x01
SEG_B = 0x02
SEG_C = 0x04
SEG_D = 0x08
SEG_E = 0x10
SEG_F = 0x20
SEG_G = 0x40
SEG_H = 0x80


class HT16K33:
    ALPHA_BLINK_RATE_NOBLINK = 0b00
    ALPHA_BLINK_RATE_2HZ = 0b01
    ALPHA_BLINK_RATE_1HZ = 0b10
    ALPHA_BLINK_RATE_0_5HZ = 0b11

    ALPHA_DISPLAY_ON = 0b1
    ALPHA_DISPLAY_OFF = 0b0

    ALPHA_DECIMAL_ON = 0b1
    ALPHA_DECIMAL_OFF = 0b0

    ALPHA_COLON_ON = 0b1
    ALPHA_COLON_OFF = 0b0

    ALPHA_CMD_SYSTEM_SETUP = 0b00100000
    ALPHA_CMD_DISPLAY_SETUP = 0b10000000
    ALPHA_CMD_DIMMING_SETUP = 0b11100000

    def __init__(self, i2c, address=DEFAULT_ADDRESS):
        self.i2c = i2c
        self.address = address
        self.displayRAM = bytearray(16)
        self.clear()

    def is_connected(self):
        try:
            self.i2c.readfrom(self.address, 1)
            return True
        except:
            return False

    def write_data(self, data):
        self.i2c.writeto(self.address, data)

    def enable_system_clock(self):
        self.write_data(bytearray([self.ALPHA_CMD_SYSTEM_SETUP | 0x01]))
        time.sleep(0.001)

    def disable_system_clock(self):
        self.write_data(bytearray([self.ALPHA_CMD_SYSTEM_SETUP | 0x00]))
        time.sleep(0.001)

    def set_brightness(self, brightness):
        if brightness > 15:
            brightness = 15
        self.write_data(bytearray([self.ALPHA_CMD_DIMMING_SETUP | brightness]))

    def set_blink_rate(self, rate):
        blink_rate = {
            0: self.ALPHA_BLINK_RATE_NOBLINK,
            2: self.ALPHA_BLINK_RATE_2HZ,
            1: self.ALPHA_BLINK_RATE_1HZ,
            0.5: self.ALPHA_BLINK_RATE_0_5HZ,
        }.get(rate, self.ALPHA_BLINK_RATE_NOBLINK)
        self.write_data(
            bytearray(
                [
                    self.ALPHA_CMD_DISPLAY_SETUP
                    | (blink_rate << 1)
                    | self.ALPHA_DISPLAY_ON
                ]
            )
        )

    def display_on(self):
        self.write_data(
            bytearray([self.ALPHA_CMD_DISPLAY_SETUP | self.ALPHA_DISPLAY_ON])
        )

    def display_off(self):
        self.write_data(
            bytearray([self.ALPHA_CMD_DISPLAY_SETUP | self.ALPHA_DISPLAY_OFF])
        )

    def clear(self):
        self.displayRAM = bytearray(16)
        self.update_display()

    def update_display(self):
        data = bytearray([0x00]) + self.displayRAM
        self.write_data(data)

    def print_char(self, displayChar, digit):
        char_segments = self.get_segments(displayChar)
        for i in range(8):  # There are 8 segments (including the decimal point)
            if char_segments & (1 << i):
                self.displayRAM[i * 2] |= 1 << digit
            else:
                self.displayRAM[i * 2] &= ~(1 << digit)
        self.update_display()

    def get_segments(self, displayChar):
        char_map = {
            " ": 0b00000000000000,
            "!": 0b00001000001000,
            '"': 0b00001000000010,
            "#": 0b01001101001110,
            "$": 0b01001101101101,
            "%": 0b10010000100100,
            "&": 0b00110011011001,
            "'": 0b00001000000000,
            "(": 0b00000000111001,
            ")": 0b00000000001111,
            "*": 0b11111010000000,
            "+": 0b01001101000000,
            ",": 0b10000000000000,
            "-": 0b00000101000000,
            ".": 0b00000000000000,
            "/": 0b10010000000000,
            "0": 0b00000000111111,
            "1": 0b00010000000110,
            "2": 0b00000101011011,
            "3": 0b00000101001111,
            "4": 0b00000101100110,
            "5": 0b00000101101101,
            "6": 0b00000101111101,
            "7": 0b01010000000001,
            "8": 0b00000101111111,
            "9": 0b00000101100111,
            ":": 0b01000000000000,
            ";": 0b01001000000000,
            "<": 0b01000000000000,
            "=": 0b00000001000000,
            ">": 0b01000000000000,
            "?": 0b01000100000011,
            "@": 0b00001100111011,
            "A": 0b00000101110111,
            "B": 0b01001100001111,
            "C": 0b00000000111001,
            "D": 0b01001000001111,
            "E": 0b00000101111001,
            "F": 0b00000101110001,
            "G": 0b00000100111101,
            "H": 0b00000101110110,
            "I": 0b01001000001001,
            "J": 0b00000000011110,
            "K": 0b00110001110000,
            "L": 0b00000000111000,
            "M": 0b00010010110110,
            "N": 0b00100010110110,
            "O": 0b00000000111111,
            "P": 0b00000101110011,
            "Q": 0b00100000111111,
            "R": 0b00100101110011,
            "S": 0b00000110001101,
            "T": 0b01001000000001,
            "U": 0b00000000111110,
            "V": 0b10010000110000,
            "W": 0b10100000110110,
            "X": 0b10110010000000,
            "Y": 0b01010010000000,
            "Z": 0b10010000001001,
        }
        return char_map.get(
            displayChar, 0b00000000000000
        )  # Default to space if character not found


# Example usage
i2c = I2C(0, scl=Pin(21), sda=Pin(20))
display = HT16K33(i2c)
display.enable_system_clock()
display.set_brightness(15)
display.set_blink_rate(0)
display.display_on()

# Display "HELLO"
display.print_char("A", 9)
