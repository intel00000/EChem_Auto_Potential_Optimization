"""
AD5761 DAC Controller Class for MicroPython
-----------------------------------------------------------------
This class provides a full implementation for controlling the AD5761 Digital-to-Analog Converter (DAC)
via SPI on a Raspberry Pi Pico.
It supports all commands listed in the spec sheet, including writing to input registers, updating the DAC, resetting, and setting the control register.
Testing is done on a Raspberry Pi Pico with MicroPython v1.23.

Datasheet Reference: https://www.analog.com/media/en/technical-documentation/data-sheets/ad5761_5721.pdf

Key Features:
- Write to the DAC register with a percentage of the full scale (0-100%).
- Update the DAC register from the input register (software LDAC).
- Write to the input register without updating the DAC.
- Control and disable daisy-chain functionality.
- Perform a software data reset.
- Read back control and DAC registers with interpreted values.

Things to watch out for:
- After a full software reset, the control register MUST be set before writing again to the DAC.

Dependencies:
- MicroPython

Author: Tom Tan
Date: 2024-09-30
"""

from machine import SPI, Pin
import time


class AD5761:
    """
    AD5761: A class to control the AD5761 DAC through SPI on a Raspberry Pi Pico.
    """

    # Command First 4 Bits, X means don't care, always set to 0000.
    CMD_FIRST_4_BITS = 0x0
    # Input Shift Register Commands options at DB[19:16]
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

    # Control Register Options
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
    CV_ZERO_SCALE = 0x0  # Clear voltage selection: Zero Scale
    CV_MIDSCALE = 0x1  # Clear voltage selection: Mid Scale
    CV_FULL_SCALE = 0x2  # Clear voltage selection: Full Scale
    OVR_DISABLED = 0x0  # Overrange disabled
    OVR_ENABLED = 0x1  # Overrange enabled
    B2C_BINARY = 0x0  # Bipolar range: Straight Binary
    B2C_TWOS_COMPLEMENT = 0x1  # Bipolar range: Twos Complement
    ETS_NOT_POWER_DOWN = 0x0  # Thermal shutdown: Does not power down
    ETS_POWER_DOWN = 0x1  # Thermal shutdown: Powers down if temp > 150°C
    PV_ZERO_SCALE = 0x0  # Power-up voltage: Zero Scale
    PV_MIDSCALE = 0x1  # Power-up voltage: Mid Scale
    PV_FULL_SCALE = 0x2  # Power-up voltage: Full Scale
    RA_10V_BIPOLAR = 0x0  # Output range: -10V to +10V
    RA_10V_UNIPOLAR = 0x1  # Output range: 0V to +10V
    RA_5V_BIPOLAR = 0x2  # Output range: -5V to +5V
    RA_5V_UNIPOLAR = 0x3  # Output range: 0V to +5V
    RA_7_5V = 0x4  # Output range: -2.5V to +7.5V
    RA_3V = 0x5  # Output range: -3V to +3V
    RA_16V_UNIPOLAR = 0x6  # Output range: 0V to +16V
    RA_20V_UNIPOLAR = 0x7  # Output range: 0V to +20V

    def __init__(
        self,
        sclk_pin: int,
        sdi_pin: int,
        sdo_pin: int,
        sync_pin: int,
        alert_pin: int,
        spi_id: int = 0,
        baudrate: int = 1_000_000,
        debug: bool = False,
    ) -> None:
        """
        Initializes AD5761.

        Args:
        - sclk_pin: Pin for the SPI clock.
        - sdi_pin: Pin for SPI data input.
        - sdo_pin: Pin for SPI data output.
        - sync_pin: Pin for SPI chip select (SYNC).
        - alert_pin: Pin to monitor the alert (active low).
        - spi_id: SPI bus ID (default: 0).
        - baudrate: SPI clock speed (default: 1 MHz).
        - debug: Enable/disable debug printing (default: False).
        """
        self.spi = SPI(
            id=spi_id,
            baudrate=baudrate,
            polarity=1,
            phase=0,
            firstbit=1,
            sck=Pin(sclk_pin),
            mosi=Pin(sdi_pin),
            miso=Pin(sdo_pin),
        )
        self.sync = Pin(sync_pin, Pin.OUT, value=1)
        self.alert = Pin(alert_pin, Pin.IN, Pin.PULL_UP)
        self.debug = debug

    def write_spi(self, tx: bytes) -> None:
        """
        Writes the given data to the SPI interface.

        Args:
        - tx: Byte array to write over SPI.
        """
        self.sync(0)
        self.spi.write(tx)
        self.sync(1)

    def read_into_spi(self, rx: bytearray) -> None:
        """
        Reads data from the SPI interface into the given buffer.

        Args:
        - rx: Byte array buffer to store the read data.
        """
        self.sync(0)
        self.spi.readinto(rx)
        self.sync(1)

    def print_binary(self, data: bytearray) -> str:
        """Converts byte data to a binary string for display."""
        return " ".join(f"{byte:08b}"[:4] + " " + f"{byte:08b}"[4:] for byte in data)

    def reset(self) -> None:
        """
        Performs a software full reset on the AD5761 DAC.
        """
        reset_cmd = bytearray(3)
        reset_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_SW_FULL_RESET
        self.write_spi(reset_cmd)
        if self.debug:
            print(
                f"Software Full Reset Issued, Command: {self.print_binary(reset_cmd)}, Alert pin: {self.alert.value()}"
            )

    def write_control_register(
        self,
        cv=CV_ZERO_SCALE,
        ovr=OVR_DISABLED,
        b2c=B2C_BINARY,
        ets=ETS_POWER_DOWN,
        pv=PV_ZERO_SCALE,
        ra=RA_10V_UNIPOLAR,
    ) -> None:
        """
        Writes the control register with the provided configuration options.

        Args:
        - cv: Clear voltage selection. (default: Zero Scale on software data reset)
        - ovr: Overrange option. (default: Disabled)
        - b2c: Bipolar range configuration. (default: Binary input)
        - ets: Thermal shutdown configuration. (default: Power down on overheat)
        - pv: Power-up voltage configuration. (default: Zero Scale on power-up)
        - ra: Output range configuration. (default: 0V to 10V Unipolar)
        """
        write_cmd = bytearray(3)
        write_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_WR_CTRL_REG
        write_cmd[1] = (cv << 1) | ovr
        write_cmd[2] = (b2c << 7) | (ets << 6) | (pv << 3) | ra
        self.write_spi(write_cmd)
        if self.debug:
            print(
                f"Write to Control Register, Command: {self.print_binary(write_cmd)}, Alert pin: {self.alert.value()}"
            )

    def read_control_register(self) -> None:
        """
        Reads and interprets the control register, printing out the settings.
        """
        write_cmd = bytearray(3)
        write_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_RD_CTRL_REG
        read_buf = bytearray(3)
        self.write_spi(write_cmd)  # Send the read command
        self.read_into_spi(read_buf)  # Read the response into the buffer

        reg_address = read_buf[0] & 0xF  # Extract bits [19:16] - Register address

        sc = (read_buf[1] >> 4) & 0x1  # Extract bit [12] - Short-circuit condition
        bo = (read_buf[1] >> 3) & 0x1  # Extract bit [11] - Brownout condition
        cv = (read_buf[1] >> 1) & 0x3  # Extract bits [10:9] - Clear voltage selection
        ovr = read_buf[1] & 0x1  # Extract bit [8] - Overrange

        b2c = (read_buf[2] >> 7) & 0x1  # Extract bit [7] - Bipolar/Two's complement
        ets = (read_buf[2] >> 6) & 0x1  # Extract bit [6] - Thermal shutdown
        pv = (read_buf[2] >> 3) & 0x3  # Extract bits [4:3] - Power-up voltage selection
        ra = read_buf[2] & 0x7  # Extract bits [2:0] - Output range

        if self.debug:
            print(
                f"Read Control Register, Sent: {self.print_binary(write_cmd)}, Received: {self.print_binary(read_buf)}, Alert pin: {self.alert.value()}"
            )

        print("--------------------------------------------------------")
        print("Control Register Data:")
        print(f"  Register Address: 0x{reg_address:02X} (0x{reg_address:04b})")
        print(f"  Short-circuit condition (SC): {'Detected' if sc else 'No condition'}")
        print(f"  Brownout condition (BO): {'Detected' if bo else 'No condition'}")
        print(f"  Clear voltage selection (CV): {self.decode_cv(cv)}")
        print(f"  Overrange (OVR): {'Enabled' if ovr else 'Disabled'}")
        print(
            f"  Bipolar/Two's Complement (B2C): {'Two Complement' if b2c else 'Binary'}"
        )
        print(
            f"  Thermal Shutdown (ETS): {'Shutdown on overheat' if ets else 'No shutdown on overheat'}"
        )
        print(f"  Power-up Voltage (PV): {self.decode_pv(pv)}")
        print(f"  Output Range (RA): {self.decode_ra(ra)}")
        print("--------------------------------------------------------")

    def decode_cv(self, cv) -> str:
        """Decode the Clear Voltage Selection (CV) field."""
        return {
            self.CV_ZERO_SCALE: "Zero Scale",
            self.CV_MIDSCALE: "Mid Scale",
            self.CV_FULL_SCALE: "Full Scale",
        }.get(cv, "Unknown")

    def decode_pv(self, pv) -> str:
        """Decode the Power-up Voltage (PV) field."""
        return {
            self.PV_ZERO_SCALE: "Zero Scale",
            self.PV_MIDSCALE: "Mid Scale",
            self.PV_FULL_SCALE: "Full Scale",
        }.get(pv, "Unknown")

    def decode_ra(self, ra) -> str:
        """Decode the Output Range (RA) field."""
        return {
            self.RA_10V_BIPOLAR: "-10V to +10V Bipolar",
            self.RA_10V_UNIPOLAR: "0V to +10V Unipolar",
            self.RA_5V_BIPOLAR: "-5V to +5V Bipolar",
            self.RA_5V_UNIPOLAR: "0V to +5V Unipolar",
            self.RA_7_5V: "-2.5V to +7.5V Bipolar",
            self.RA_3V: "-3V to +3V Bipolar",
            self.RA_16V_UNIPOLAR: "0V to +16V Unipolar",
            self.RA_20V_UNIPOLAR: "0V to +20V Unipolar",
        }.get(ra, "Unknown")

    def write_update_dac_register(self, percentage: float) -> None:
        """
        Writes and updates the DAC register with a given percentage of the full scale voltage.

        Args:
        - percentage: Percentage of the full-scale voltage to write to the DAC.
        """
        value = int(0xFFFF * percentage / 100)  # convert percentage to 16-bit value
        write_cmd = bytearray(3)
        write_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_WR_UPDATE_DAC_REG
        write_cmd[1] = value >> 8
        write_cmd[2] = value & 0xFF
        self.write_spi(write_cmd)
        if self.debug:
            print(
                f"Write and update DAC Register with {percentage}% of the voltage, Command: {self.print_binary(write_cmd)}, Alert pin: {self.alert.value()}"
            )

    def write_input_register(self, percentage: float) -> None:
        """
        Writes the given percentage value to the input register without updating the DAC register.

        Args:
        - percentage: Percentage value to write to the input register.
        """
        value = int(0xFFFF * percentage / 100)  # convert percentage to 16-bit value
        write_cmd = bytearray(3)
        write_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_WR_TO_INPUT_REG
        write_cmd[1] = value >> 8
        write_cmd[2] = value & 0xFF
        self.write_spi(write_cmd)
        if self.debug:
            print(
                f"Write to Input Register (No DAC update) with {percentage}% value, Command: {self.print_binary(write_cmd)}, Alert pin: {self.alert.value()}"
            )

    def update_dac_from_input_register(self) -> None:
        """
        Updates the DAC register with the value stored in the input register.
        """
        update_cmd = bytearray(3)
        update_cmd[0] = (
            self.CMD_FIRST_4_BITS << 4 | self.CMD_UPDATE_DAC_REG_FROM_INPUT_REG
        )
        self.write_spi(update_cmd)
        if self.debug:
            print(
                f"Update DAC Register from Input Register, Command: {self.print_binary(update_cmd)}, Alert pin: {self.alert.value()}"
            )

    def set_daisy_chain(self, enabled: bool = True) -> None:
        """
        Enables or disables daisy-chain functionality. You need to enable this if you want to read back any register values.

        Args:
        - enabled: Pass `True` to enable and `False` to disable daisy-chaining.
        """
        daisy_chain_cmd = bytearray(3)
        daisy_chain_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_DIS_DAISY_CHAIN
        daisy_chain_cmd[2] = 0x0 if enabled else 0x1
        self.write_spi(daisy_chain_cmd)
        if self.debug:
            status = "enabled" if enabled else "disabled"
            print(
                f"Daisy-Chain {status}, Command: {self.print_binary(daisy_chain_cmd)}, Alert pin: {self.alert.value()}"
            )

    def software_data_reset(self) -> None:
        """
        Performs a software data reset to the power-up scale specified in the control register.
        """
        reset_cmd = bytearray(3)
        reset_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_SW_DATA_RESET
        self.write_spi(reset_cmd)
        if self.debug:
            print(
                f"Software Data Reset, Command: {self.print_binary(reset_cmd)}, Alert pin: {self.alert.value()}"
            )

    def read_dac_register(self) -> int:
        """
        Reads and returns the value in the DAC register.
        """
        write_cmd = bytearray(3)
        write_cmd[0] = self.CMD_FIRST_4_BITS << 4 | self.CMD_RD_DAC_REG
        read_buf = bytearray(3)
        self.write_spi(write_cmd)
        self.read_into_spi(read_buf)
        read_value = (read_buf[1] << 8) | read_buf[2]
        if self.debug:
            print(
                f"Read DAC Register, Sent: {self.print_binary(write_cmd)}, Received: {self.print_binary(read_buf)}, Alert: {self.alert.value()}"
            )
            print(f"Read Value: {read_value}, percentage: {read_value / 0xFFFF * 100}%")
        return read_value


# Usage
def main() -> None:
    ad5761 = AD5761(
        spi_id=0, sclk_pin=6, sdi_pin=7, sdo_pin=4, sync_pin=5, alert_pin=12, debug=True
    )
    ad5761.reset()
    time.sleep(1)

    # Configure the DAC control register with the correct command
    # full scale, overrange disabled, straight binary, thermal shutdown enabled, zero scale power-up, 0V to 10V range
    ad5761.write_control_register(
        cv=ad5761.CV_FULL_SCALE,
        ovr=ad5761.OVR_DISABLED,
        b2c=ad5761.B2C_BINARY,
        ets=ad5761.ETS_POWER_DOWN,
        pv=ad5761.PV_ZERO_SCALE,
        ra=ad5761.RA_10V_UNIPOLAR,
    )
    time.sleep(1)
    ad5761.read_control_register()
    time.sleep(1)

    # enable daisy chain
    ad5761.set_daisy_chain(enabled=True)
    time.sleep(1)

    # Write a 50% value to the DAC using write_update_dac_register
    ad5761.write_update_dac_register(75)
    time.sleep(1)
    ad5761.read_dac_register()

    # then use the write_input_register to write a 25% value to the input register
    ad5761.write_input_register(25)
    time.sleep(5)
    # read the DAC register to see the value
    ad5761.read_dac_register()
    time.sleep(1)
    # update the DAC register from the input register
    ad5761.update_dac_from_input_register()
    time.sleep(1)
    # read the DAC register to see the value
    ad5761.read_dac_register()
    time.sleep(1)

    # Perform a software data reset
    ad5761.software_data_reset()
    time.sleep(1)
    # read the DAC register to see the value
    ad5761.read_dac_register()
    time.sleep(1)


if __name__ == "__main__":
    main()
