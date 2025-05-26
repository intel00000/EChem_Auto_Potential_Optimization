import json

CONFIG_FILE = "bootloader_config.json"


def create_default_config() -> dict:
    default_config = {"mode": "pump", "mode_before": "pump"}
    with open(CONFIG_FILE, "w") as f:
        f.write(json.dumps(default_config))
    return default_config


def bootloader():
    try:
        with open(CONFIG_FILE, "r") as f:
            config_data = f.read()
    except OSError:
        # config file does not exist, create it with default values
        config_data = json.dumps(create_default_config())

    # Parse the config
    try:
        config = json.loads(config_data)
    except ValueError:
        # recreate the config file with default values
        config = create_default_config()

    # Check if the bootloader is active
    mode = config.get("mode", "pump")
    if mode == "pump":
        import pump_control_pico

        pump_control_pico.main()
    elif mode == "autosampler":
        import autosampler_control_pico

        autosampler_control_pico.main()
    elif mode == "update_firmware":
        import bootloader_util

        bootloader_util.update_firmware()
    elif mode == "potentiostat":
        import potentiostat_control_pico

        potentiostat_control_pico.main()
    else:
        import pump_control_pico

        pump_control_pico.main()


if __name__ == "__main__":
    bootloader()
