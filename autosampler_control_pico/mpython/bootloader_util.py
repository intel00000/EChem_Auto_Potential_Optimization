# bootloader_util.py
import json
import machine

CONFIG_FILE = "bootloader_config.json"


def enter_bootloader_settings():
    # Read current config (or use defaults)
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except OSError:
        config = {"enter_bootloader_setting": False, "mode": "pump"}

    # Update the flag to enter bootloader settings mode
    config["enter_bootloader_setting"] = True
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

    # Reset the board to start bootloader.py and enter settings mode
    machine.reset()


def set_bootloader_mode(mode: str):
    # Read current config (or use defaults)
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except OSError:
        config = {"enter_bootloader_setting": False, "mode": "pump"}

    # Update the mode
    # mode has to be either "pump" or "autosampler" or "update_firmware"
    if mode not in ["pump", "autosampler", "update_firmware"]:
        raise ValueError(
            "Invalid mode. Must be 'pump', 'autosampler', or 'update_firmware'."
        )
    config["mode"] = mode
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
