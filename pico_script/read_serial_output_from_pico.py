import serial
import json
import time
import matplotlib.pyplot as plt

from matplotlib.animation import FuncAnimation
from serial.tools import list_ports
from datetime import datetime

# Lists to store data for plotting
host_machine_timestamps = []
pico_timestamps = []
adc0_values = []
adc1_values = []
adc2_values = []

# format of the output in string
# read_u16(), ADC0: 10930, ADC1: 10818, ADC2: 11362
# Pico local time: 2024-6-17 19:55:11
# Function to read serial data
def read_serial(ser, log_file):
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line.startswith('read_u16()'):
            print(line)
            data = {}
            for item in line.split(','):
                if item.startswith('read_u16()'):
                    continue
                key, value = item.split(':')
                data[key.strip()] = int(value.strip())
            
            adc0_values.append(data.get("ADC0", 0))
            adc1_values.append(data.get("ADC1", 0))
            adc2_values.append(data.get("ADC2", 0))

            # read the second line
            line = ser.readline().decode('utf-8').strip()
            print(line)
            if line.startswith('Pico local time'):
                data["host_machine_timestamp"] = time.strftime('%Y-%m-%d %H:%M:%S')
                data["pico_timestamp"] = line.split('Pico local time: ')[1]
                
                host_machine_timestamps.append(data["host_machine_timestamp"])
                pico_timestamps.append(data["pico_timestamp"])

                with open(log_file, 'a') as f:
                    json.dump(data, f)
                    f.write('\n')

# Main function to start serial communication and plotting
def main():
    print("Listing all available serial ports...")
    # Print all available serial ports
    for port in list_ports.comports():
        print(f"{port.device} - {port.description}")
        print(f"  hwid: {port.hwid}")
        print(f"  vid:pid: {port.vid:04x}:{port.pid:04x}")
        print(f"  serial_number: {port.serial_number}")
        print(f"  location: {port.location}")
        print(f"  manufacturer: {port.manufacturer}")
        print(f"  product: {port.product}")
        print(f"  interface: {port.interface}")
    print("-" * 40)

    pico_ports = list(list_ports.grep("2E8A:0005"))
    print("Looking for Raspberry Pi Pico...")
    print(f"Found {len(pico_ports)} Raspberry Pi Pico(s) on port:" + str([p.device for p in pico_ports]))

    if not pico_ports:
        print("No Raspberry Pi Pico found")
        return

    pico_serial_port = pico_ports[0].device
    ser = serial.Serial(pico_serial_port, timeout=1)
    log_file = 'data_log.json'

    # Start reading serial data in a separate thread
    import threading
    serial_thread = threading.Thread(target=read_serial, args=(ser, log_file))
    serial_thread.daemon = True
    serial_thread.start()

    # Plotting setup
    fig, axs = plt.subplots(3, 1, figsize=(10, 8))
    # disable x ticks
    for ax in axs:
        ax.set_xticks([])

    def update_plot(frame):
        axs[0].clear()
        axs[1].clear()
        axs[2].clear()

        axs[0].plot(host_machine_timestamps, adc0_values, label='ADC0')
        axs[0].set_ylabel('ADC0 Value')
        axs[0].legend(loc='upper left')

        axs[1].plot(host_machine_timestamps, adc1_values, label='ADC1')
        axs[1].set_ylabel('ADC1 Value')
        axs[1].legend(loc='upper left')

        axs[2].plot(host_machine_timestamps, adc2_values, label='ADC2')
        axs[2].set_ylabel('ADC2 Value')
        axs[2].legend(loc='upper left')

        plt.tight_layout()

    ani = FuncAnimation(fig, update_plot, interval=200)
    plt.show()

if __name__ == "__main__":
    main()