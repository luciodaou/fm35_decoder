# FM35 Decoder

A lightweight Python tool to decode standard FM35 TEMP weather messages from upper-air observations (radiosoundings).

## Installation

Install the package directly from the repository:

```bash
pip install .
```

Or for development (editable mode):

```bash
pip install -e .
```

## Usage

Import the decoder into your project and call the `decode` function:

```python
from fm35_decoder import decode

# Your FM35/TEMP message parts
ttaa = "..."
# ...
df_main, df_special = decode(ttaa, ttbb, ttcc, ttdd)
```
# df_main: Standard levels, interpolated data and geopotential heights
# df_special: Tropopause, Max Wind, and Cloud groups
print(df_main)
