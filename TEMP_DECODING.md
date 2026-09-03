# Decoding Standard FM 35 TEMP Messages

This document explains the meteorological decoding process for upper-air observations (radiosoundings) encoded in the **WMO FM 35 TEMP** format, written in clear language and cross-referenced with official World Meteorological Organization (WMO) standards.

---

## 1. Official Standards & References

The decoding methodology implemented in this library adheres strictly to:

- **WMO-No. 306, Volume I.1, Part A (Alphanumeric Codes)**:
  - **Code Form FM 35-XII TEMP**: *Upper-air report from land station*.
  - **Code Form FM 36-XII TEMP SHIP**: *Upper-air report from sea station*.
  - **Code Form FM 38-XII TEMP MOBIL**: *Upper-air report from mobile land station*.
- **WMO Code Tables**:
  - **Code Table 3931** ($T_a$): *Approximate tenths of degrees Celsius and its sign*.
  - **Code Table 0777** ($D_a D_a$ / $2D_a$): *Dew-point depression ($\Delta T = T - T_d$)*.
  - **Code Table 0877** ($dd$): *True wind direction in tens of degrees*.
  - **Code Table 2700** ($N_h$): *Amount of cloud whose base is at height $h$*.
  - **Code Table 0513** ($C_L$): *Clouds of the genera Stratocumulus, Stratus, Cumulus, and Cumulonimbus*.
  - **Code Table 1600** ($h$): *Height of base of lowest cloud layer*.
  - **Code Table 0515** ($C_M$): *Clouds of the genera Altocumulus, Altostratus, and Nimbostratus*.
  - **Code Table 0509** ($C_H$): *Clouds of the genera Cirrus, Cirrocumulus, and Cirrostratus*.
  - **Code Table 3849** ($s_r$): *Solar and infrared radiation correction*.
  - **Code Table 3872** ($s_a s_a$): *Tracking technique and system status*.
  - **Common Code Table C-2 / Code Table 3685** ($r_a r_a$): *Radiosonde model type*.

---

## 2. Why Are TEMP Messages Coded This Way?

Before high-speed internet, upper-air soundings gathered by weather balloons were transmitted globally across the Global Telecommunication System (GTS) via telex and radioteletype. Every character mattered. 

To achieve maximum compression, WMO designed FM 35 as fixed-length **5-digit groups** separated by spaces, ending with an equals sign (`=`). Within each 5-digit block:
- Standard pressure levels are indicated by 2-digit prefixes (`85` = $850\text{ hPa}$, `50` = $500\text{ hPa}$).
- Temperatures and dew-point depressions pack sign, value, and tenths into 5 digits (`TTTDD`).
- Wind direction and speed share a single 5-digit group (`ddfff`).

---

## 3. Message Architecture (The Four Parts)

A complete radiosonde sounding is divided into four distinct parts:

| Part | Identifier | Atmosphere Region | Contents |
| :--- | :--- | :--- | :--- |
| **Part A** | `TTAA` | Up to $100\text{ hPa}$ | Surface level, mandatory standard isobaric surfaces ($1000, 925, 850, 700, 500, 400, 300, 250, 200, 150, 100\text{ hPa}$), tropopause, and maximum wind level. |
| **Part B** | `TTBB` | Up to $100\text{ hPa}$ | Significant levels with respect to temperature and relative humidity (inversions, rapid lapse rate changes), significant wind levels, cloud groups, and instrument metadata. |
| **Part C** | `TTCC` | Above $100\text{ hPa}$ | Mandatory standard isobaric surfaces in the stratosphere ($70, 50, 30, 20, 10, 7, 5, 3, 2, 1\text{ hPa}$), stratospheric tropopause, and stratospheric maximum wind. |
| **Part D** | `TTDD` | Above $100\text{ hPa}$ | Significant temperature, humidity, and wind levels in the stratosphere. |

---

## 4. Group-by-Group Decoding Rules

### 4.1 Header Group: `TTAA YYGGId IIiii`
- `TTAA`: Part identifier (`TTAA`, `TTBB`, `TTCC`, or `TTDD`).
- `YYGGId`:
  - `YY`: Day of the month (with 50 added if wind speed is reported in knots; e.g., day 23 reported in knots becomes `73`).
  - `GG`: Observation hour UTC (e.g., `12` = 12:00 UTC, `00` = 00:00 UTC).
  - `Id`: Indicator for the highest standard level observed and wind units.
- `IIiii`: WMO Station Identifier (e.g., `83779` for São Paulo, Brazil).

### 4.2 Surface Level Group: `99PPP TTTDD dddff`
- `99`: Indicator for station surface level.
- `PPP`: Surface atmospheric pressure in whole hectopascals (hPa).
  - If $PPP < 100$ (e.g., `99021`), the pressure is $\ge 1000\text{ hPa}$ ($1021.0\text{ hPa}$).
  - If $PPP \ge 100$ (e.g., `99938`), the pressure is $< 1000\text{ hPa}$ ($938.0\text{ hPa}$).
- `TTT`: Surface air temperature (see Section 4.4).
- `DD`: Surface dew-point depression (see Section 4.5).
- `dddff`: Surface wind direction and speed (see Section 4.6).

### 4.3 Mandatory Standard Isobaric Levels: `PPhhh TTTDD dddff`
- `PP`: Standard pressure level indicator:
  - `00` = $1000\text{ hPa}$, `92` = $925\text{ hPa}$, `85` = $850\text{ hPa}$, `70` = $700\text{ hPa}$, `50` = $500\text{ hPa}$, `40` = $400\text{ hPa}$, `30` = $300\text{ hPa}$, `25` = $250\text{ hPa}$, `20` = $200\text{ hPa}$, `15` = $150\text{ hPa}$, `10` = $100\text{ hPa}$.
  - In Part C (`TTCC`): `70` = $70\text{ hPa}$, `50` = $50\text{ hPa}$, `30` = $30\text{ hPa}$, `20` = $20\text{ hPa}$, `10` = $10\text{ hPa}$, `07` = $7\text{ hPa}$, `05` = $5\text{ hPa}$, `03` = $3\text{ hPa}$, `02` = $2\text{ hPa}$, `01` = $1\text{ hPa}$.
- `hhh`: Geopotential height of the pressure surface.
  - **For $P > 500\text{ hPa}$** (e.g., $1000, 925, 850, 700\text{ hPa}$): Reported in **whole standard geopotential meters**. Thousands digits are omitted. For example, $850\text{ hPa}$ coded as `85570` represents $1570\text{ gpm}$.
  - **For $P \le 500\text{ hPa}$** (e.g., $500, 400, 300, 200, 100\text{ hPa}$): Reported in **tens of geopotential meters (decameters, dam)**. For example, $500\text{ hPa}$ coded as `50591` represents $591\text{ dam} = 5910\text{ gpm}$.
  - **Sub-zero / Below-sea-level heights**: At $1000\text{ hPa}$, if the surface is below sea level or the pressure surface lies below ground, 500 is added to the absolute value ($500 + |h|$). A reported `00520` indicates $-20\text{ gpm}$.

### 4.4 Temperature Group: `TTT` (WMO Code Table 3931)
The 3-digit group `TTT` represents dry-bulb temperature in degrees Celsius:
- The first two digits (`TT`) report the absolute value in whole degrees.
- The third digit ($T_a$) encodes both the **sign** and the **approximate tenths of a degree**:
  - **Even digits ($0, 2, 4, 6, 8$)**: Temperature is **positive** ($+0.0, +0.2, +0.4, +0.6, +0.8^\circ\text{C}$).
  - **Odd digits ($1, 3, 5, 7, 9$)**: Temperature is **negative** ($-0.1, -0.3, -0.5, -0.7, -0.9^\circ\text{C}$).
- *Example 1*: `212` $\implies +21.2^\circ\text{C}$.
- *Example 2*: `583` $\implies -58.3^\circ\text{C}$.

### 4.5 Dew-Point Depression Group: `DD` (WMO Code Table 0777)
The 2-digit group `DD` represents the dew-point depression $\Delta T = T - T_d$:
- **Codes `00` through `50`**: Depression from $0.0^\circ\text{C}$ to $5.0^\circ\text{C}$ in tenths of a degree ($DD / 10.0$).
  - *Example*: `24` $\implies \Delta T = 2.4^\circ\text{C}$. Dewpoint $T_d = 21.2 - 2.4 = 18.8^\circ\text{C}$.
- **Codes `56` through `99`**: Depression from $6^\circ\text{C}$ to $49^\circ\text{C}$ in whole degrees ($DD - 50$).
  - *Example*: `65` $\implies \Delta T = 65 - 50 = 15^\circ\text{C}$.
  - `99` indicates a depression of $49^\circ\text{C}$ or more (extremely dry air).
- **Code `//`**: Moisture sensor frozen or missing.

### 4.6 Wind Group: `ddfff` (WMO Regulations 35.2.4.4 & 12.3.4.1)
- `dd`: Wind direction in tens of degrees ($01 = 10^\circ, 36 = 360^\circ$).
  - `00`: Calm wind ($fff = 000$).
  - `99`: **Variable wind**. Direction is marked as `NaN` in `df_main` while speed is preserved.
- `fff`: Wind speed in knots.
  - **The 5-Degree Rule**: WMO encodes the $5^\circ$ unit digit of wind direction by adding $500$ to the wind speed $fff$.
  - *Case A ($fff < 500$)*: Units digit of direction is $0$. Direction is $dd \times 10$, speed is $fff$.
  - *Case B ($fff \ge 500$)*: Units digit of direction is $5$. Direction is $dd \times 10 + 5$, speed is $fff - 500$.
  - *Example*: `27620` $\implies fff = 620 \ge 500 \implies$ Direction $= 27 \times 10 + 5 = 275^\circ$, Speed $= 620 - 500 = 120\text{ kt}$.

### 4.7 Significant Levels: `nnPPP TTTDD` (Part B & Part D)
- `nn`: Repeating sequence counter ($00, 11, 22, 33, \dots, 99, 11, 22\dots$).
  - `00` represents the surface level.
- `PPP`: Pressure of the significant level.
  - In **Part B (`TTBB`)**: Reported in whole hectopascals (hPa).
  - In **Part D (`TTDD`)**: Reported in **tenths of a hectopascal (hPa)**. For example, `11906` represents significant level 1 at $90.6\text{ hPa}$.

### 4.8 Tropopause Group: `88PtPtPt TtTtTt dtdtftft`
- `88`: Tropopause indicator group (`88999` indicates no tropopause was observed).
- `PtPtPt`: Pressure of the tropopause level in hPa.
- `TtTtTt`: Temperature and dew-point depression at the tropopause.
- `dtdtftft`: Wind direction and speed at the tropopause.

### 4.9 Maximum Wind Level: `77PmPmPm dmdmfmfmfm 4vbvbvava`
- `77` (or `66`): Maximum wind indicator group (`77999` indicates maximum wind was not determined).
- `PmPmPm`: Pressure of the maximum wind level in hPa.
- `dmdmfmfmfm`: Direction and speed of the maximum wind (subject to the same $+500$ speed addition rule for $5^\circ$ directional resolution).
- `4vbvbvava`: Vertical wind shear group (optional):
  - `vbvb`: Wind shear in the $1\text{ km}$ layer below the maximum wind level (knots).
  - `vava`: Wind shear in the $1\text{ km}$ layer above the maximum wind level (knots).

### 4.10 Cloud Layer Group: `41414 Nh CL h CM CH`
- `41414`: Section identifier for cloud data.
- `Nh`: Cloud amount (Code Table 2700, oktas).
- `CL`: Low cloud genus (Code Table 0513: Stratus, Cumulus, Cumulonimbus, Stratocumulus).
- `h`: Base height of lowest cloud layer (Code Table 1600).
- `CM`: Mid-level cloud genus (Code Table 0515: Altocumulus, Altostratus, Nimbostratus).
- `CH`: High-level cloud genus (Code Table 0509: Cirrus, Cirrostratus, Cirrocumulus).

### 4.11 Radiosonde Metadata & Release Time: `31313 sr rara sasa 8GGgg`
- `31313`: Section identifier for instrumentation metadata.
- `sr`: Solar and infrared radiation correction applied (Code Table 3849).
- `rara`: Radiosonde model type (Common Code Table C-2 / Code Table 3685; e.g., Vaisala RS41, Graw DFM-17).
- `sasa`: Wind-tracking technique (Code Table 3872; e.g., GPS, Radar, Radiotheodolite).
- `8GGgg`: Actual radiosonde launch time in hours (`GG`) and minutes (`gg`) UTC.

---

## 5. Thermodynamics & Vertical Processing Methodology

### 5.1 Vertical Interpolation in $\ln(P)$ Space
Atmospheric pressure decreases exponentially with height in accordance with the barometric equation ($P(z) = P_0 e^{-z / H}$). On thermodynamic charts such as the **Skew-T / Log-P** diagram:
- Temperature and dewpoint vary approximately linearly with the **natural logarithm of pressure** ($\ln P$).
- Missing intermediate levels in `df_main` are interpolated with respect to $\ln P$, preventing artificial distortions caused by linear interpolation in Cartesian pressure space.

### 5.2 Vector Wind Interpolation
Interpolating wind direction and speed directly as scalar numbers creates severe mathematical artifacts (e.g., averaging $350^\circ$ and $10^\circ$ scalar numbers produces $180^\circ$ South wind instead of $360^\circ$ North wind).
This decoder converts wind vectors into zonal ($U$) and meridional ($V$) components:
$$u = -S \cdot \sin(\theta), \quad v = -S \cdot \cos(\theta)$$
Each vector component ($u, v$) is interpolated independently in $\ln P$ space and recombined:
$$S = \sqrt{u^2 + v^2}, \quad \theta = \left(270^\circ - \text{atan2}(v, u)\right) \pmod{360^\circ}$$
Non-calm North winds ($0.0^\circ$) are mapped to the meteorological standard of $360.0^\circ$.

### 5.3 Physical Moisture Constraint
Because temperature and dewpoint are interpolated independently, temperature inversions can occasionally produce non-physical mathematical artifacts where $T_d > T$ (super-saturation, $\text{RH} > 100\%$). The decoder enforces the physical boundary:
$$T_d = \min(T_d, T)$$

### 5.4 Hypsometric Equation & Virtual Temperature
When standard level geopotential heights are missing, heights are calculated using the Hypsometric Equation:
$$Z_2 - Z_1 = \frac{R_d \cdot \bar{T}_v}{g_0} \ln\left(\frac{P_1}{P_2}\right)$$
Where:
- $R_d = 287.05\text{ J/(kg K)}$ (Specific gas constant for dry air).
- $g_0 = 9.80665\text{ m/s}^2$ (Standard acceleration of gravity).
- $\bar{T}_v$ is the mean **virtual temperature** of the layer, calculated from dry temperature and water vapor mixing ratio ($w$):
  $$T_v = T \cdot (1 + 0.608 \cdot w)$$
  Accounting for moisture via virtual temperature corrects for air density, preventing 20–50 meter thickness errors in warm, humid lower atmospheres.
