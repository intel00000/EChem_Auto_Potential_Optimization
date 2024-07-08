
# Pump Controller Demo

This repository contains a Pump Controller Demo implemented in Python, utilizing a Raspberry Pi Pico for hardware control and a PC-side GUI for managing the pumps and their operations.

## Table of Contents
- [Requirements](#requirements)
- [Setup](#setup)
- [Running the Application](#running-the-application)
- [Compiling to an Executable](#compiling-to-an-executable)
- [Usage](#usage)
- [File Descriptions](#file-descriptions)

## Requirements

Ensure you have the following software and libraries installed:

### Software
- Python 3.11 or higher
- Pip package manager

### Python Libraries
Install the required Python libraries using the following command:
```sh
pip install pyserial tkinter pandas openpyxl
```

## Setup

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/pump-controller-demo.git
    cd pump-controller-demo
    ```

2. Ensure all required Python libraries are installed:
    ```sh
    pip install -r requirements.txt
    ```

## Running the Application

To run the Pump Controller Demo, use the following command:
```sh
python Pump\ Controller\ Demo_singlethread.py
```

## Compiling to an Executable

To compile the application to a standalone executable using PyInstaller, follow these steps:

1. Install PyInstaller if you haven't already:
    ```sh
    pip install pyinstaller
    ```

2. Run PyInstaller to compile the executable:
    ```sh
    pyinstaller --onefile --windowed Pump\ Controller\ Demo_singlethread.py
    ```

3. After the process completes, you will find the executable in the `dist` directory.

## Usage

1. Connect your Raspberry Pi Pico to your PC via a USB cable.
2. Open the executable or run the Python script as described above.
3. Select the appropriate COM port and click "Connect".
4. Load the recipe file by clicking the "Load Recipe" button and selecting your recipe file (CSV or Excel format).
5. Click "Start" to begin the procedure. The GUI will display the progress and status of each pump.

## File Descriptions

- `main.py`: The main entry point for the Raspberry Pi Pico script. It calls the `main` function from `pump_control_pico.py`.
- `pump_control_pico.py`: Contains the logic for controlling the pumps connected to the Raspberry Pi Pico.
- `Pump Controller Demo_singlethread.py`: The main Python script for the PC-side GUI, allowing users to interact with the pumps, load recipes, and monitor progress.

### Example Recipe File
An example of a recipe file structure (CSV or Excel):
```csv
Time point (min),Pump 1,Pump 2,Pump 3,Valve 1,Valve 2,Valve 3,Notes
0,On,Off,Off,CW,CW,CW,Start initial fill with reaction solution
0.5,Off,On,On,CCW,CCW,CCW,For testing
1,On,On,Off,,,For testing
5,Off,,,,,,
125,,On,,CW,CW,CW,Post reaction emptying
130,,Off,,,,
130,,On,CCW,CCW,CCW,3x rinse with solvent
135,,Off,,,,
135,,On,CW,CW,CW,
140,,Off,,,,
140,,On,CCW,CCW,CCW,
145,,Off,,,,
145,,On,CW,CW,CW,
150,,Off,,,,
150,,On,CCW,CCW,CCW,
155,,Off,,,,
155,,On,CW,CW,CW,
160,,Off,,,,
```

Ensure the `Time point (min)` column is sorted in ascending order.

## Contact

For any issues or contributions, please open an issue or pull request on GitHub.

---

This README provides all necessary steps and information to set up, run, and compile the Pump Controller Demo application. Ensure to follow each section carefully for a successful setup.
