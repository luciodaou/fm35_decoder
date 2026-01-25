# TTAA Decoder

A lightweight Python tool to decode standard TTAA weather messages (Upper-air observations).

## Installation

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management.

```bash
uv sync
```

Or install dependencies manually via pip:

```bash
pip install pandas
```

## Usage

### 1. From File
Pass a text file containing the TTAA message:
```bash
python decode_ttaa.py path/to/message.txt
```

### 2. Direct String Input
Pass the message directly as a command-line argument:
```bash
python decode_ttaa.py "TTAA 73121 82332 99008 26652 06005 00139 26257 05508 ..."
```

### 3. Interactive Mode
Run without arguments and paste the message when prompted:
```bash
python decode_ttaa.py
```

## Output
The script prints a clean DataFrame table containing:
- Pressure (hPa)
- Air Temperature (°C)
- Dew Temperature (°C)
- Wind Direction (°)
- Wind Speed (kt)
