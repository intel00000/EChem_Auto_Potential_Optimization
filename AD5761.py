# Convert from https://github.com/analogdevicesinc/no-OS/tree/main/drivers/dac/ad5761r

from machine import Pin, SPI
import time


class AD5761:
    # Input Shift Register Commands
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

    # Control Register Format
    AD5761R_CTRL_SC = 1 << 12  # RO
    AD5761R_CTRL_BO = 1 << 11  # RO
    AD5761R_CTRL_CV = lambda x: ((x & 0x3) << 9)  # RW
    AD5761R_CTRL_OVR = 1 << 8  # RW
    AD5761R_CTRL_B2C = 1 << 7  # RW
    AD5761R_CTRL_ETS = 1 << 6  # RW
    AD5761R_CTRL_IRO = 1 << 5  # RW
    AD5761R_CTRL_PV = lambda x: ((x & 0x3) << 3)  # RW
    AD5761R_CTRL_RA = lambda x: ((x & 0x7) << 0)  # RW

    # Disable Daisy-Chain Register Format
    AD5761R_DIS_DAISY_CHAIN_DDC = lambda x: ((x & 0x1) << 0)

    def __init__(self, spi, cs_pin, reset_pin=None, clr_pin=None, ldac_pin=None):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT)
        self.reset = Pin(reset_pin, Pin.OUT) if reset_pin else None
        self.clr = Pin(clr_pin, Pin.OUT) if clr_pin else None
        self.ldac = Pin(ldac_pin, Pin.OUT) if ldac_pin else None
        self.daisy_chain_en = False

    def _spi_write_and_read(self, data):
        self.cs.value(0)
        self.spi.write_readinto(data, data)
        self.cs.value(1)
        return data

    def write(self, reg_addr_cmd, reg_data):
        data = bytearray(3)
        data[0] = reg_addr_cmd << 4
        data[1] = (reg_data >> 8) & 0xFF
        data[2] = reg_data & 0xFF
        self._spi_write_and_read(data)

    def read(self, reg_addr_cmd):
        data = bytearray(3)
        data[0] = reg_addr_cmd << 4
        data[1] = 0
        data[2] = 0
        self._spi_write_and_read(data)
        reg_data = (data[1] << 8) | data[2]
        return reg_data

    def register_readback(self, reg):
        if not self.daisy_chain_en:
            raise RuntimeError("Readback operation is disabled.")
        reg_addr = {
            "input": self.CMD_RD_INPUT_REG,
            "dac": self.CMD_RD_DAC_REG,
            "ctrl": self.CMD_RD_CTRL_REG,
        }.get(reg, None)
        if reg_addr is None:
            raise ValueError("Invalid register specified for readback.")
        self.read(reg_addr)  # Dummy read
        return self.read(reg_addr)

    def config(self, dev):
        reg_data = (
            self.AD5761R_CTRL_CV(dev["cv"])
            | (self.AD5761R_CTRL_OVR if dev["ovr_en"] else 0)
            | (self.AD5761R_CTRL_B2C if dev["b2c_range_en"] else 0)
            | (self.AD5761R_CTRL_ETS if dev["exc_temp_sd_en"] else 0)
            | (self.AD5761R_CTRL_IRO if dev["int_ref_en"] else 0)
            | self.AD5761R_CTRL_PV(dev["pv"])
            | self.AD5761R_CTRL_RA(dev["ra"])
        )
        self.write(self.CMD_WR_CTRL_REG, reg_data)

    def set_daisy_chain_en_dis(self, en_dis):
        self.daisy_chain_en = en_dis
        self.write(
            self.CMD_DIS_DAISY_CHAIN, self.AD5761R_DIS_DAISY_CHAIN_DDC(not en_dis)
        )

    def get_daisy_chain_en_dis(self):
        return self.daisy_chain_en

    def set_output_range(self, dev, out_range):
        dev["ra"] = out_range
        self.config(dev)

    def get_output_range(self, dev):
        return dev["ra"]

    def set_power_up_voltage(self, dev, pv):
        dev["pv"] = pv
        self.config(dev)

    def get_power_up_voltage(self, dev):
        return dev["pv"]

    def set_clear_voltage(self, dev, cv):
        dev["cv"] = cv
        self.config(dev)

    def get_clear_voltage(self, dev):
        return dev["cv"]

    def set_internal_reference_en_dis(self, dev, en_dis):
        dev["int_ref_en"] = en_dis
        self.config(dev)

    def get_internal_reference_en_dis(self, dev):
        return dev["int_ref_en"]

    def set_exceed_temp_shutdown_en_dis(self, dev, en_dis):
        dev["exc_temp_sd_en"] = en_dis
        self.config(dev)

    def get_exceed_temp_shutdown_en_dis(self, dev):
        return dev["exc_temp_sd_en"]

    def set_2c_bipolar_range_en_dis(self, dev, en_dis):
        dev["b2c_range_en"] = en_dis
        self.config(dev)

    def get_2c_bipolar_range_en_dis(self, dev):
        return dev["b2c_range_en"]

    def set_overrange_en_dis(self, dev, en_dis):
        dev["ovr_en"] = en_dis
        self.config(dev)

    def get_overrange_en_dis(self, dev):
        return dev["ovr_en"]

    def get_short_circuit_condition(self):
        reg_data = self.register_readback("ctrl")
        return (reg_data >> 12) & 0x1

    def get_brownout_condition(self):
        reg_data = self.register_readback("ctrl")
        return (reg_data >> 11) & 0x1

    def write_input_register(self, dac_data):
        self.write(self.CMD_WR_TO_INPUT_REG, dac_data)

    def update_dac_register(self):
        self.write(self.CMD_UPDATE_DAC_REG_FROM_INPUT_REG, 0)

    def write_update_dac_register(self, dac_data):
        self.write(self.CMD_WR_UPDATE_DAC_REG, dac_data)

    def software_data_reset(self):
        self.write(self.CMD_SW_DATA_RESET, 0)

    def software_full_reset(self):
        self.write(self.CMD_SW_FULL_RESET, 0)

    def set_reset_pin(self, value):
        if self.reset:
            self.reset.value(value)
        else:
            raise RuntimeError("Reset pin not initialized.")

    def get_reset_pin(self):
        if self.reset:
            return self.reset.value()
        else:
            raise RuntimeError("Reset pin not initialized.")

    def set_clr_pin(self, value):
        if self.clr:
            self.clr.value(value)
        else:
            raise RuntimeError("CLR pin not initialized.")

    def get_clr_pin(self):
        if self.clr:
            return self.clr.value()
        else:
            raise RuntimeError("CLR pin not initialized.")

    def set_ldac_pin(self, value):
        if self.ldac:
            self.ldac.value(value)
        else:
            raise RuntimeError("LDAC pin not initialized.")

    def get_ldac_pin(self):
        if self.ldac:
            return self.ldac.value()
        else:
            raise RuntimeError("LDAC pin not initialized.")


# Enums and struct-like class for device settings using dictionaries
class ad5761r_dev:
    def __init__(self, ra, pv, cv, int_ref_en, exc_temp_sd_en, b2c_range_en, ovr_en):
        self.settings = {
            "ra": ra,
            "pv": pv,
            "cv": cv,
            "int_ref_en": int_ref_en,
            "exc_temp_sd_en": exc_temp_sd_en,
            "b2c_range_en": b2c_range_en,
            "ovr_en": ovr_en,
        }


AD5761R_REGS = {"input": 0, "dac": 1, "ctrl": 2}

AD5761R_SCALES = {"zero": 0, "half": 1, "full": 2}

AD5761R_RANGES = {
    "m_10v_to_p_10v": 0,
    "0_v_to_p_10v": 1,
    "m_5v_to_p_5v": 2,
    "0v_to_p_5v": 3,
    "m_2v5_to_p_7v5": 4,
    "m_3v_to_p_3v": 5,
    "0v_to_p_16v": 6,
    "0v_to_p_20v": 7,
}
