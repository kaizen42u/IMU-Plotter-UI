## Description
This project reads COM port data and parses the output for graphing the IMU acceleration and angular velocity.

## Getting Started

### Prerequisites
- Python
- Git for Windows
- Jupyter Notebook

### Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/kaizen42u/IMU-Plotter-UI
   ```

2. Create a virtual environment:
    ```bash
    python -m venv .venv
    ```

3. Activate the virtual environment: 
- On Windows:
    ```bash
    .venv\Scripts\activate
    ```
- On macOS/Linux:
    ```bash
    source .venv/bin/activate
    ```

4. Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage
Run the `espGraphing.py` script:
```bash
python espGraphing.py
```

### Taking sample
Choose the Serial Port to connect to the MCU. Collect data and then save to .csv files via GUI

## Training Model
Use the `train.ipynb` script

## Features
- Graphs IMU acceleration and angular velocity
- Save as .csv

## Todo List
- Improve performance

## Contributing
PM me if you want to contribute.