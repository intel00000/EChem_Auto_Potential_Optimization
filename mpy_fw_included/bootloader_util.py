# bootloader_util.py
import json
import machine

CONFIG_FILE = "bootloader_config.json"


def set_bootloader_mode(mode: str):
    # Read current config (or use defaults)
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except OSError:
        config = {"mode": "pump"}

    # Update the mode
    # mode has to be either "pump" or "autosampler" or "update_firmware"
    if mode not in ["pump", "autosampler", "update_firmware", "potentiostat"]:
        raise ValueError(
            "Invalid mode. Must be 'pump', 'autosampler', 'potentiostat', or 'update_firmware'."
        )
    if mode == "update_firmware":
        config["mode_before"] = config.get("mode", "pump")
    config["mode"] = mode
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def exit_bootloader_settings():
    # Read current config (or use defaults)
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except OSError:
        config = {"mode": "pump"}

    # Update the flag to exit bootloader settings mode
    config["mode"] = config.get("mode_before", "pump")
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

    # Reset the board to start the main application
    machine.reset()
