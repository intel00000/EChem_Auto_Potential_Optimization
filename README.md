<!-- @format -->

# MasterFlex Pump Controller

This repository contains a MasterFlex Pump Controller implemented in Python, utilizing a Raspberry Pi Pico for hardware control and a PC-side GUI for pumps automation and operations.

<p align="center">
  <img src=images/pump_control_gui.png alt="Pump Controller GUI"/>
</p>

## Table of Contents

- [Requirements](#requirements)
- [Setup](#setup)
  - [Native Installation](#native-installation)
  - [Using a Python Virtual Environment (Recommended)](#using-a-python-virtual-environment-recommended)
- [Running the Application](#running-the-application)
- [Compiling to an Executable](#compiling-to-an-executable)
- [Usage](#usage)
- [File Descriptions](#file-descriptions)

## Requirements

- Python 3.11 or higher
- Pip package manager

## Setup (two methods)

### 1. Native Installation

1. Clone the repository:
   ```sh
   git clone https://github.com/intel00000/EChem_Auto_Potential_Optimization.git
   cd EChem_Auto_Potential_Optimization
   ```
2. Install required Python libraries:
   ```sh
   pip install -r requirements.txt
   ```
3. Run the Pump Controller Demo with the following command:
   ```sh
   python pump_control.py
   ```

### 2. Using a Python Virtual Environment (Recommended)

It is recommended to use a Python virtual environment for better dependency management, especially when compiling the executable. See https://docs.python.org/3/library/venv.html for more details.

#### Windows

1. Open a Windows Powershell and navigate to the project directory.
2. Create a virtual environment:
   ```sh
   python -m venv .venv
   ```
3. Activate the virtual environment:
   ```sh
   .\.venv\Scripts\Activate.ps1
   ```
   If this fail, you might need to run this command first, see https://stackoverflow.com/questions/54776324/powershell-bug-execution-of-scripts-is-disabled-on-this-system
   ```sh
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine
   ```
4. Install the required packages:
   ```sh
   pip install -r requirements.txt
   ```
5. To run the Pump Controller Demo, ensure the virtual environment is activated and use the following command:
   ```sh
   python pump_control.py
   ```

#### Linux & MacOS (Untested)

1. Open a terminal and navigate to the project directory.
2. Create a virtual environment:

   In bash, run the following commands (assuming using apt)

   ```sh
   sudo apt-get install python3-venv
   python3 -m venv .venv
   ```

3. Activate the virtual environment:
   ```sh
   source ./.venv/bin/activate
   ```
4. Install the required packages:
   ```sh
   pip install -r requirements.txt
   ```
5. To run the Pump Controller Demo, activated the virtual environment first and use the following command:
   ```sh
   python3 pump_control.py
   ```

## Compiling to an Executable

To compile the application to a standalone executable using PyInstaller, it is recommended to use a Python virtual environment.

### Windows

1. Create and activate a virtual environment as described above.
2. Install PyInstaller if you haven't already:
   ```sh
   pip install pyinstaller
   ```
3. Run PyInstaller to compile the executable:
   ```sh
   pyinstaller --onefile --windowed --console --add-data "icons-black.ico;." --add-data "icons-white.ico;." --add-data "icons-red.ico;." --icon=icons-red.ico --paths . pump_control.py
   ```
4. After the process completes, you will find the executable in the `dist` directory.

## Usage

1. Connect your Raspberry Pi Pico to your PC via a USB cable.
2. Open the executable or run the Python script as described above.
3. Select the appropriate COM port and click "Connect".
4. Load the recipe file by clicking the "Load Recipe" button and selecting your recipe file (CSV or Excel format).
5. Click "Start" to begin the procedure. The GUI will display the progress and status of each pump.

## File Descriptions

- `main.py`: The main entry point for the Raspberry Pi Pico script. It calls the `main` function from `pump_control_pico.py`.
- `pump_control_pico.py`: Contains the logic for controlling the pumps connected to the Raspberry Pi Pico.
- `pwm_dma_fade_onetime.py`: Fade the onboard led of the pi pico using DMA & PWM without using logic core. (Currently don't work for Pi Pico W where the onboard led is controlled by the wifi chip.)

- `pump_control.py`: The Python script for the PC-side GUI, allowing users to interact with the pumps, load recipes, and monitor progress.

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
```

```excel
Time point (min)	Pump 1	Pump 2	Pump 3	Valve 1	Valve 2	Valve 3	Notes
0	                OFF	    OFF	    OFF	    CW	    CW	    CW	    1
0.2	                ON	    ON	    ON	    CCW	    CCW	    CCW	    2
0.4	                OFF	    OFF	    OFF	    CW	    CW	    CW	    3
0.6	                ON	    ON	    ON	    CCW	    CCW	    CCW	    4
0.8	                OFF	    OFF	    OFF	    CW	    CW	    CW	    5
1	                ON	    ON	    ON	    CCW	    CCW	    CCW	    6
1.2	                OFF	    OFF	    OFF	    CW	    CW	    CW	    7
1.4	                ON	    ON	    ON	    CCW	    CCW	    CCW	    8
1.6	                OFF	    OFF	    OFF	    CW	    CW	    CW	    9
1.8	                ON	    ON	    ON	    CCW	    CCW	    CCW	    10
```

Ensure the `Time point (min)` column is sorted in ascending order.

## Contact

For any issues or contributions, please open an issue or pull request on GitHub.
