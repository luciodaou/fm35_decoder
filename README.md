# FM35 Decoder

[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=flat&logo=ko-fi&logoColor=white)](https://ko-fi.com/luciodaou)
[![PyPI - Version](https://img.shields.io/pypi/v/fm35_decoder.svg)](https://pypi.org/project/fm35_decoder)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fm35_decoder.svg)](https://pypi.org/project/fm35_decoder)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)


A Python tool to decode standard FM35 TEMP weather messages from upper-air observations (radiosoundings).

## Installation

Install the package directly from the repository:

```bash
pip install fm35_decoder
```

## Usage

Import the decoder into your project and call the `decode` function:

```python
from fm35_decoder import decode

# Your FM35/TEMP message parts
ttaa = "..."
# ...
df_main, df_special = decode(ttaa, ttbb, ttcc, ttdd)

# df_main: Standard levels, interpolated data and geopotential heights
# df_special: Tropopause, Max Wind, and Cloud groups
print(df_main)
print(df_special)
```
## Important Information
### Interpolation


### AI usage
Google's Gemini 3 Pro and Flash were used to assist in the development of this package, based on the FM35/TEMP documentation.

## Example
### df_main
```
=== Main Level DataFrame (df_main) ===
 Pressure  Height  Temp  DewPoint  WindDir  WindSpeed
     1000     163   NaN       NaN      NaN        NaN
      938     714  21.2      18.8     10.0        8.0
      925     843  20.0      18.1     75.0        6.0
      882    1249  16.8      16.4     23.0        8.5
      870    1366  19.8      13.8     15.0       10.0
      850    1570  18.6      13.6    360.0        8.0
      ...     ...   ...       ...      ...         ...
       31   23586 -58.8     -91.4     85.0       27.0
       30   23800 -58.3     -91.3     85.0       35.0
       29   24013 -58.0     -92.0     85.0       44.0
       28   24234 -57.7     -92.7     90.0       41.0
```

## df_special
```
=== Special Data DataFrame (df_special) ===
  Symbol    Subject     Description     Value
       h      Cloud     Base Height                      600-1000m (2000-3300ft)
      Nh      Cloud          Amount                                      8 oktas
      CL      Cloud        Low Type     Stratus nebulosus and/or Stratus fractus
      CM      Cloud        Mid Type                                 No CM clouds
      CH      Cloud       High Type                                 No CH clouds
      sr Solar/Inst      Solar Corr                         NOAA solar corrected
    rara Solar/Inst      Sonde Type         Vaisala RS41/DigiCORA MW41 (Finland)
    sasa Solar/Inst        Tracking                                 Radar (5 cm)
   8GGgg Solar/Inst            Time                                        11:31
  PtPtPt Tropopause        Pressure                                       906hPa
  TtTtTt Tropopause     Temperature                                       -77.1C
    DtDt Tropopause        Dewpoint                                       -89.1C
dtdtftft Tropopause            Wind                                     260/18kt
```

```

## Interpolation Methodology

**Temperature and Dewpoint**: Missing values are filled using linear interpolation with respect to the natural logarithm of pressure. This method aligns with standard atmospheric thermodynamics (Skew-T/Log-P diagrams), where temperature typically varies linearly with log-pressure, ensuring physically realistic profiles.

**Wind**: Wind speed and direction are decomposed into U (zonal) and V (meridional) vector components. Each component is interpolated independently with respect to the natural logarithm of pressure before being recombined. This vector-based approach prevents artifacts that can occur when interpolating speed and direction scalar values directly (e.g., across the 0°/360° north boundary).

## License

This project is licensed under the terms of the **MIT License**.

You are free to create derivative works and use this software for commercial purposes. The only requirement is that you **must give credit** to the original author.
