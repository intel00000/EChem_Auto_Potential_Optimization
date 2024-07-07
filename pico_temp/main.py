# main.py

import pump_control_pico

@micropython.native
def main():
    pump_control_pico.main()

if __name__ == "__main__":
    main()