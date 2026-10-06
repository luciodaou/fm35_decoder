# FM35 Decoder

[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=flat&logo=ko-fi&logoColor=white)](https://ko-fi.com/luciodaou)
[![PyPI - Version](https://img.shields.io/pypi/v/fm35_decoder.svg)](https://pypi.org/project/fm35_decoder)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fm35_decoder.svg)](https://pypi.org/project/fm35_decoder)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A fast, robust Python tool to decode standard **WMO FM 35 TEMP** upper-air weather messages from radiosonde observations.

For an extensive plain-English guide referencing official WMO manuals, see [TEMP_DECODING.md](TEMP_DECODING.md).

---

## Installation

Install the package directly from PyPI:

```bash
pip install fm35_decoder
```

---

## Quickstart

Import the decoder and call `decode()` with the message parts (`TTAA`, `TTBB`, `TTCC`, `TTDD`):

```python
from fm35_decoder import decode

# Your FM35/TEMP message parts
ttaa = "TTAA 73121 83779 99938 21224 01008 00163 ///// ///// 92843 20019 07506 85570 18650 36008 ..."
ttbb = "TTBB 73128 83779 00938 21224 11882 16804 22870 19856 33735 11056 44712 08616 55615 01218 ..."
ttcc = "TTCC 73123 83779 70865 71568 15020 50064 67574 12519 30380 58383 08535 88906 77162 26018 ..."
ttdd = "TTDD 7312/ 83779 11906 77162 22585 70370 33542 70970 44445 63978 55283 57785 21212 11935 ..."

df_main, df_special = decode(ttaa, ttbb, ttcc, ttdd)

# df_main: Clean vertical sounding profile (Pressure, Height, Temp, DewPoint, WindDir, WindSpeed)
# df_special: Metadata, Tropopause, Maximum Wind, and Cloud groups
print(df_main)
print(df_special)
```

---

## Handling Non-Standard and Extreme Meteorological Data

Real-world atmospheric soundings and teletype GTS transmissions frequently contain non-standard encodings, extreme conditions, and transmission artifacts. `fm35_decoder` handles them deterministically per WMO regulations:

- **Variable Wind Direction ($dd = 99$)**:
  In WMO Code Table 0877, a wind direction reported as `99` indicates variable wind direction. The decoder sets `WindDir = np.nan` in `df_main` while preserving the numeric `WindSpeed`. Crucially, variable winds are excluded from trigonometric vector ($U/V$) decomposition so they do not distort the vertical wind field.
- **5-Degree Directional Resolution ($fff \ge 500$)**:
  In WMO FM 35, when the units digit of wind direction is $5^\circ$ (e.g., $275^\circ$), $500$ is added to the reported wind speed ($fff$) across both standard levels and maximum wind groups ($77P_mP_mP_m$). The decoder accurately separates the $5^\circ$ direction component from the true wind speed, avoiding the common $500\text{ kt}$ speed inflation bug.
- **Calm Wind ($0^\circ, 0\text{ kt}$)**:
  Calm wind is represented as `WindDir = 0.0, WindSpeed = 0.0`. True non-calm winds blowing from North are assigned `360.0°`.
- **GTS Transmission Sequence Breaks**:
  If network or teletype line noise drops an intermediate significant level in `TTBB` or `TTDD` (e.g., group sequence jumps directly from `22` to `44`), the decoder recovers automatically rather than terminating or discarding the remainder of the sounding.
- **Negative Geopotential Heights (surfaces below sea level)**:
  When a standard isobaric surface lies below sea level, WMO encodes its geopotential as $500 + |h|$. The decoder detects this offset and outputs true negative geopotential heights (e.g., `00520` $\implies -20\text{ gpm}$).
- **Wind Groups Omitted Above the $I_d$ Level**:
  Per Regulation 35.2.2.3 and Code Table 1734, the header indicator $I_d$ gives the last standard level carrying a wind group; above it the wind group is omitted (`/` means no standard-level winds at all). The decoder reads two groups per level above that point instead of misreading the next level as a wind.
- **Wind Speed Units**:
  `YY > 50` means knots; otherwise the message reports m/s. All speeds (including tropopause, maximum wind and wind shear) are output in **knots**, converting m/s reports (× 1.943844).
- **Parts C and D in Tenths of hPa**:
  Above 100 hPa, significant-level, tropopause ($P_tP_tP_t$) and maximum-wind ($P_mP_mP_m$) pressures are reported in tenths of a hectopascal (e.g., `88906` in `TTCC` $\implies 90.6\text{ hPa}$).
- **Headers With Solidi**:
  `YYGGId` / `YYGGa4` groups containing `/` (always the case in `TTDD`, `YYGG/`) are recognized, so the station number is never decoded as data. Each argument of `decode()` is decoded as the part it is passed as, even if the `TTAA`/`TTCC`/... identifier is missing.
- **Regional and National Sections**:
  Sections 9 (`51515` ... `59595`) and 10 (`61616` ... `69696`) are the last sections of each part; their contents are skipped rather than decoded as levels.
- **Missing Data Is Not Extrapolated**:
  Interpolation only fills gaps between reported values. Winds or dewpoints missing above (or below) the last report stay `NaN`.
- **Layers Reported as Missing**:
  Layers marked `nn/// /////` in `TTBB`/`TTDD` (Regulations 35.3.1.6 and 35.3.2.2) are never interpolated; they are listed in `df_special` as `Missing Layer`.
- **Stratospheric Standard Levels ($P < 10\text{ hPa}$)**:
  Soundings reaching the middle stratosphere in `TTCC` ($7, 5, 3, 2, 1\text{ hPa}$) are evaluated against extended standard atmosphere heights up to $47,800\text{ gpm}$.
- **Physical Super-Saturation Prevention**:
  Temperature inversions can cause vertical DewPoint interpolation to cross above Temperature. The decoder strictly enforces $T_d \le T$ ($\text{RH} \le 100\%$).

---

## Meteorological Methodology

### Vertical Interpolation
- **Temperature & Dewpoint**: Missing intermediate levels are filled via linear interpolation with respect to the **natural logarithm of pressure** ($\ln P$). This aligns with atmospheric thermodynamics on Skew-T / Log-P diagrams where temperature varies approximately linearly with $\ln P$.
- **Wind Vectors**: Wind speed and direction are decomposed into orthogonal **$U$ (zonal)** and **$V$ (meridional)** vector components. Each component is interpolated independently in $\ln P$ space before being recombined, preventing boundary artifacts across the $0^\circ/360^\circ$ North transition.

### Hypsometric Geopotential Calculation
Missing geopotential heights are computed using the Hypsometric Equation:
$$Z_2 - Z_1 = \frac{R_d \cdot \bar{T}_v}{g_0} \ln\left(\frac{P_1}{P_2}\right)$$
The decoder incorporates **virtual temperature ($T_v$)** when moisture data is available, accounting for air density variations in warm and humid tropical boundary layers.

---

## Performance & Architecture

- **In-Memory WMO Code Tables**: Core WMO tables (3931, 0777, 2700, 0513, 1600, 0515, 0509, 3849, and Common Code Tables C-2 and C-7 from WMO's official [wmo-im/CCT](https://github.com/wmo-im/CCT) release) are compiled directly into memory in `tables.py`, providing sub-microsecond table access with zero disk I/O overhead.
- **NumPy Vectorization**: Hypsometric height integration and vector wind calculations leverage NumPy array operations for speed when batch-processing large archives of historical radiosonde soundings.

---

## Output Data Structure

### `df_main` (Vertical Profile)
```
  Pressure  Height  Temp  DewPoint  WindDir  WindSpeed
      1000     163   NaN       NaN      NaN        NaN
       938     717  21.2      18.8     10.0        8.0
       925     843  20.0      18.1     75.0        6.0
       882    1253  16.8      16.4     23.0        8.5
       870    1371  19.8      13.8     15.0       10.0
       850    1570  18.6      13.6    360.0        8.0
       ...     ...   ...       ...      ...        ...
        30   23800 -58.3     -91.3     85.0       35.0
        29   24013 -58.0     -92.0     85.0       44.0
        28   24234 -57.7     -92.7     90.0       41.0
```

### `df_special` (Metadata & Special Levels)
```
    Symbol     Subject    Description                                                              Value
         h       Cloud    Base Height                                          600-1000 m (2000-3300 ft)
        Nh       Cloud         Amount                                                            8 oktas
        CL       Cloud       Low Type Stratus nebulosus and/or Stratus fractus other than of bad weather
        CM       Cloud       Mid Type                                                       No CM clouds
        CH       Cloud      High Type                                                       No CH clouds
        sr  Solar/Inst     Solar Corr    Solar and infrared corrected automatically by radiosonde system
      rara  Solar/Inst     Sonde Type                               Vaisala RS41/DigiCORA MW41 (Finland)
      sasa  Solar/Inst       Tracking                                     Automatic satellite navigation
     8GGgg  Solar/Inst           Time                                                              11:31
    PtPtPt  Tropopause       Pressure                                                            90.6hPa
    TtTtTt  Tropopause    Temperature                                                             -77.1C
      DtDt  Tropopause       Dewpoint                                                             -89.1C
  dtdtftft  Tropopause           Wind                                                           260/18kt
```

---

## License

This project is licensed under the terms of the **MIT License**.
You are free to use, modify, and distribute this software with attribution to the original author.
