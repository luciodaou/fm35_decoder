"""
FM 35-XII TEMP Decoder.
Decodes standard WMO FM 35 / FM 36 / FM 38 upper-air radiosonde observations.
"""

from __future__ import annotations

import functools
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .tables import STANDARD_ATMOSPHERE_HEIGHTS, WMO_TABLES


# --- WMO Tables Loader ---


@functools.lru_cache(maxsize=1)
def load_wmo_tables(base_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns WMO code tables for FM 35 TEMP decoding.
    By default, returns fast in-memory compiled tables (0 ms overhead).
    If base_path is provided, loads CSV files from that directory.
    """
    if base_path is None:
        return WMO_TABLES

    codes: Dict[str, Any] = {}
    table_files = {
        "Nh": "Nh_2700.csv",
        "CL": "CL_0513.csv",
        "h": "h_1600.csv",
        "CM": "CM_0515.csv",
        "CH": "CH_0509.csv",
        "Sr": "Sr_3849.csv",
        "rara": "rara_3685.csv",
        "sasa": "sasa_3872.csv",
        "T_3931": "T_3931.csv",
        "D_0777": "D_0777.csv",
    }

    for key, filename in table_files.items():
        path = os.path.join(base_path, filename)
        if os.path.exists(path):
            try:
                df_code = pd.read_csv(path, dtype=str)
                if "Code" in df_code.columns:
                    if key in ["T_3931", "D_0777"]:
                        codes[key] = df_code.set_index("Code").to_dict(orient="index")
                    else:
                        codes[key] = df_code.set_index("Code")["Description"].to_dict()
            except Exception:
                codes[key] = WMO_TABLES.get(key, {})
        else:
            codes[key] = WMO_TABLES.get(key, {})
    return codes


# --- Decoding Helper Functions ---


def decode_temperature(ttt_str: str, tables: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """
    Decodes the TTT (TaTaTa) temperature group using WMO Code Table 3931.
    TaTa gives whole degrees Celsius.
    The 3rd digit (Ta) gives approximate tenths and sign:
      - Even digits (0, 2, 4, 6, 8) -> Positive temperature
      - Odd digits (1, 3, 5, 7, 9)  -> Negative temperature
    Returns temperature in Celsius.
    """
    if not ttt_str or len(ttt_str) != 3:
        return None
    try:
        tt = int(ttt_str[:2])
        ta_code = ttt_str[2]

        t_table = (tables or WMO_TABLES).get("T_3931", TABLE_T_3931 if "TABLE_T_3931" in globals() else {})
        entry = t_table.get(ta_code)

        if entry:
            sign = entry.get("Sign", "+")
            tenths = float(entry.get("TenthsValue", 0.0))
            val = float(tt) + abs(tenths)
            return -val if sign == "-" else val

        # Fallback if table entry not found
        ta = int(ta_code)
        val = float(tt) + (ta / 10.0)
        return -val if ta % 2 != 0 else val
    except (ValueError, TypeError):
        return None


def decode_dewpoint_depression(dd_str: str, tables: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """
    Decodes the DD dew-point depression group using WMO Code Table 0777.
    Codes 00-50: 0.0 to 5.0 C (tenths)
    Codes 56-99: 6 to 49 C (whole degrees, code - 50)
    Code 99: depression of 49 C or more
    //: missing or not observed
    Returns depression in Celsius.
    """
    if not dd_str or len(dd_str) != 2 or dd_str == "//":
        return None
    try:
        d_table = (tables or WMO_TABLES).get("D_0777", {})
        entry = d_table.get(dd_str)
        if entry is not None:
            val = entry.get("Value") if isinstance(entry, dict) else entry
            if val is not None and not pd.isna(val) and val != "":
                return float(val)

        # Mathematical fallback per WMO 0777 specification
        dd = int(dd_str)
        if dd <= 50:
            return dd / 10.0
        elif 56 <= dd <= 99:
            return float(dd - 50)
        return None
    except (ValueError, TypeError):
        return None


def decode_wind(dff_str: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Decodes a 5-digit WMO wind group (ddfff).
    - dd: Direction in tens of degrees (00=calm, 01-36=10°-360°, 99=variable wind).
    - fff: Wind speed in knots (standard).
      When wind direction ends in 5 degrees, 500 is added to fff.

    Returns (direction_degrees, speed_knots).
    For variable wind (dd=99), direction is returned as np.nan while speed is preserved.
    For calm wind (dd=00, fff=000), returns (0.0, 0.0).
    """
    if not dff_str or len(dff_str) != 5 or "/////" in dff_str or "/" in dff_str:
        return None, None
    try:
        dd = int(dff_str[:2])
        fff = int(dff_str[2:])

        # Direction Range Validation: 00-36 or 99 (Variable)
        if not (0 <= dd <= 36 or dd == 99):
            return None, None

        # Extract 5-degree offset from speed
        direction_unit = 0
        speed = fff
        if fff >= 500:
            direction_unit = 5
            speed = fff - 500

        # Variable wind direction
        if dd == 99:
            return np.nan, float(speed)

        # Calm wind
        if dd == 0 and speed == 0:
            return 0.0, 0.0

        direction = dd * 10 + direction_unit
        return float(direction), float(speed)
    except (ValueError, TypeError):
        return None, None


def calculate_dewpoint(temp: Optional[float], depression: Optional[float]) -> Optional[float]:
    """Calculates dewpoint temperature from dry-bulb temperature and dew-point depression."""
    if temp is not None and depression is not None:
        return round(temp - depression, 1)
    return None


def decode_height(pressure: float, h_str: str) -> Optional[int]:
    """
    Decodes geopotential height based on pressure level (hPa) and reported 3-digit string.
    Rules (WMO Manual on Codes):
    - P <= 500 hPa: h_str is in tens of standard geopotential meters (decameters).
    - P > 500 hPa: h_str is in whole standard geopotential meters.
    - Ambiguity/Truncation: Add thousands (for P>500) or ten-thousands (for P<=500)
      to match standard atmosphere approximation closest to target.
    - Negative heights (e.g. 1000 hPa below sea level): If reported >= 500, value is 500 + |h|.
    """
    if not h_str or len(h_str) != 3 or "/" in h_str:
        return None

    try:
        val_raw = int(h_str)
    except (ValueError, TypeError):
        return None

    p_int = int(round(pressure))
    target = STANDARD_ATMOSPHERE_HEIGHTS.get(p_int, 0)

    # 1. Determine Scale and Step
    if p_int <= 500:
        val = val_raw * 10
        step = 10000
    else:
        val = val_raw
        step = 1000

    candidates = [val + k * step for k in range(6)]

    # Negative heights for surface / 1000 hPa (reported as 500 + |h|)
    if p_int >= 900 and val_raw >= 500:
        abs_h = val_raw - 500
        candidates.append(-abs_h)

    # Pick candidate closest to standard atmosphere target
    best_h = min(candidates, key=lambda x: abs(x - target))
    return int(round(best_h))


# --- Atmospheric Thermodynamics & Physics ---


def interpolate_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Interpolates missing Temperature, DewPoint, and Wind data vertically.
    - Temperature/DewPoint: Linear interpolation in Log-Pressure space.
    - Physical bound: Enforces DewPoint <= Temp (no super-saturation).
    - Wind: Vector interpolation (U/V components) in Log-Pressure space.
      Variable wind (NaN direction) is safely excluded from trigonometric vector decomposition.
    """
    if df.empty or "Pressure" not in df.columns:
        return df

    df = df.copy()

    # Filter out invalid or non-positive pressures
    df = df[pd.to_numeric(df["Pressure"], errors="coerce") > 0].copy()
    if df.empty:
        return df

    # Sort descending by Pressure (Surface -> Top)
    df = df.sort_values("Pressure", ascending=False).reset_index(drop=True)

    # Natural log of pressure for vertical coordinate
    df["log_p"] = np.log(df["Pressure"].astype(float))
    df = df.set_index("log_p")

    # --- Temperature & Dewpoint Interpolation ---
    for col in ["Temp", "DewPoint"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            mask = df[col].isna()
            df[col] = df[col].interpolate(method="index")
            df.loc[mask, col] = df.loc[mask, col].round(1)

    # Physical constraint: Dewpoint cannot exceed dry temperature
    if "Temp" in df.columns and "DewPoint" in df.columns:
        valid_both = df["Temp"].notna() & df["DewPoint"].notna()
        df.loc[valid_both, "DewPoint"] = np.minimum(
            df.loc[valid_both, "DewPoint"], df.loc[valid_both, "Temp"]
        )

    # --- Wind Vector Interpolation ---
    if "WindSpeed" in df.columns and "WindDir" in df.columns:
        df["WindSpeed"] = pd.to_numeric(df["WindSpeed"], errors="coerce")
        df["WindDir"] = pd.to_numeric(df["WindDir"], errors="coerce")

        # Vector decomposition: only for non-NaN, valid directional wind
        valid_wind = df["WindSpeed"].notna() & df["WindDir"].notna()
        rads = np.radians(df.loc[valid_wind, "WindDir"])
        df["u"] = np.nan
        df["v"] = np.nan
        df.loc[valid_wind, "u"] = -df.loc[valid_wind, "WindSpeed"] * np.sin(rads)
        df.loc[valid_wind, "v"] = -df.loc[valid_wind, "WindSpeed"] * np.cos(rads)

        # Interpolate U and V components across vertical profile
        df["u"] = df["u"].interpolate(method="index")
        df["v"] = df["v"].interpolate(method="index")

        # Reconstruct speed and direction
        reconstructed_speed = np.sqrt(df["u"] ** 2 + df["v"] ** 2)
        degrees = np.degrees(np.arctan2(df["v"], df["u"]))
        reconstructed_dir = (270.0 - degrees) % 360.0

        # Map non-calm wind with angle 0.0 to 360.0 degrees
        reconstructed_dir = np.where(
            (reconstructed_speed > 0.05) & (reconstructed_dir < 0.1),
            360.0,
            reconstructed_dir,
        )

        # Fill missing values in original columns
        missing_speed = df["WindSpeed"].isna() & df["u"].notna()
        missing_dir = df["WindDir"].isna() & df["u"].notna()

        df.loc[missing_speed, "WindSpeed"] = reconstructed_speed[missing_speed].round(1)
        df.loc[missing_dir, "WindDir"] = pd.Series(reconstructed_dir, index=df.index)[missing_dir].round(0)

        df = df.drop(columns=["u", "v"])

    df = df.reset_index(drop=True)
    return df


def calculate_geopotential(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates missing Geopotential Height values using the Hypsometric Equation.
    Formula: Z2 = Z1 + (R * Tv_avg / g) * ln(P1 / P2)
    Uses virtual temperature Tv where humidity is available to ensure physical accuracy.
    Includes WMO Extrapolation Rule 35.2.2.4 upward to the next standard level.
    """
    if df.empty or "Pressure" not in df.columns or "Temp" not in df.columns:
        return df

    # Physical constants
    R = 287.05  # Specific gas constant for dry air (J/(kg·K))
    g = 9.80665  # Standard acceleration of gravity (m/s^2)

    df = df.sort_values("Pressure", ascending=False).reset_index(drop=True)

    pressures = pd.to_numeric(df["Pressure"], errors="coerce").to_numpy(dtype=float)
    temps = pd.to_numeric(df["Temp"], errors="coerce").to_numpy(dtype=float)
    dewpoints = pd.to_numeric(df.get("DewPoint", pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)
    heights = pd.to_numeric(df.get("Height", pd.Series(dtype=float)), errors="coerce").to_numpy(dtype=float)

    # Linear interpolation for temperature to ensure continuous profile for hypsometric calculation
    valid_t = ~np.isnan(temps)
    if not valid_t.any():
        return df
    if not valid_t.all():
        temps = np.interp(np.arange(len(temps)), np.where(valid_t)[0], temps[valid_t])

    # Virtual temperature: Tv = T_K * (1 + 0.608 * w)
    temp_k = temps + 273.15
    tv_k = temp_k.copy()
    valid_td = ~np.isnan(dewpoints)
    if valid_td.any():
        # Vapor pressure e (hPa) via Tetens formula
        e = 6.112 * np.exp((17.67 * dewpoints) / (dewpoints + 243.5))
        w = np.where(pressures > e, 0.622 * e / (pressures - e), 0.0)
        w = np.nan_to_num(w, nan=0.0, posinf=0.0, neginf=0.0)
        tv_k = temp_k * (1.0 + 0.608 * w)

    n = len(df)

    # 1. Forward Pass (Surface -> Top)
    for i in range(1, n):
        if np.isnan(heights[i]) and not np.isnan(heights[i - 1]):
            p1, p2 = pressures[i - 1], pressures[i]
            if p1 > 0 and p2 > 0 and p1 > p2:
                avg_tv = (tv_k[i - 1] + tv_k[i]) / 2.0
                dz = (R * avg_tv / g) * np.log(p1 / p2)
                heights[i] = round(heights[i - 1] + dz)

    # 2. Backward Pass (Top -> Surface)
    valid_idx = np.where(~np.isnan(heights))[0]
    if len(valid_idx) > 0 and valid_idx[0] > 0:
        first_valid = valid_idx[0]
        for i in range(first_valid - 1, -1, -1):
            if np.isnan(heights[i]):
                p_upper, p_target = pressures[i + 1], pressures[i]
                if p_upper > 0 and p_target > 0 and p_target > p_upper:
                    avg_tv = (tv_k[i + 1] + tv_k[i]) / 2.0
                    dz = (R * avg_tv / g) * np.log(p_target / p_upper)
                    heights[i] = round(heights[i + 1] - dz)

    df["Height"] = heights

    # 3. WMO Extrapolation Rule 35.2.2.4 (Upward to standard levels)
    valid_rows = df.dropna(subset=["Height", "Temp"])
    if not valid_rows.empty:
        top_row = valid_rows.iloc[-1]
        p_min = float(top_row["Pressure"])
        t_min_k = float(top_row["Temp"]) + 273.15
        z_min = float(top_row["Height"])

        standard_levels = [
            1000, 925, 850, 700, 500, 400, 300, 250, 200, 150,
            100, 70, 50, 30, 20, 10, 7, 5, 3, 2, 1,
        ]
        targets = [sl for sl in standard_levels if sl < p_min]

        new_rows = []
        for p_target in targets:
            delta_p = p_min - p_target
            if delta_p <= 25 and delta_p <= 0.25 * p_target:
                try:
                    p_base = p_min + delta_p
                    all_p = df["Pressure"].to_numpy(dtype=float)
                    all_t = (df["Temp"].to_numpy(dtype=float) + 273.15)
                    log_p = np.log(all_p)
                    log_p_base = np.log(p_base)

                    t_base = np.interp(log_p_base, log_p[::-1], all_t[::-1])
                    log_p_min = np.log(p_min)
                    log_p_target = np.log(p_target)

                    if abs(log_p_min - log_p_base) < 1e-6:
                        t_target = t_min_k
                    else:
                        slope = (t_min_k - t_base) / (log_p_min - log_p_base)
                        t_target = t_min_k + slope * (log_p_target - log_p_min)

                    avg_t = (t_min_k + t_target) / 2.0
                    dz = (R * avg_t / g) * np.log(p_min / p_target)
                    z_target = z_min + dz

                    new_rows.append(
                        {
                            "Pressure": int(p_target),
                            "Height": round(z_target),
                            "Temp": round(t_target - 273.15, 1),
                            "DewPoint": None,
                            "Source": "Extrapolated",
                        }
                    )
                except Exception:
                    pass

        if new_rows:
            df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
            df = df.sort_values("Pressure", ascending=False).reset_index(drop=True)

    return df


# --- Special Section Decoders ---


def decode_cloud_group(group: str, tables: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Decodes the 5-digit cloud group Nh CL h CM CH.
    Symbols: Nh (Amount), CL (Low cloud), h (Base height), CM (Mid cloud), CH (High cloud).
    """
    t = tables or WMO_TABLES
    if not group or len(group) != 5:
        return [{"Symbol": "41414", "Subject": "Cloud", "Description": "Cloud Group", "Value": group}]

    nh, cl, h, cm, ch = group[0], group[1], group[2], group[3], group[4]
    return [
        {"Symbol": "Nh", "Subject": "Cloud", "Description": "Amount", "Value": t.get("Nh", {}).get(nh, nh)},
        {"Symbol": "CL", "Subject": "Cloud", "Description": "Low Type", "Value": t.get("CL", {}).get(cl, cl)},
        {"Symbol": "h", "Subject": "Cloud", "Description": "Base Height", "Value": t.get("h", {}).get(h, h)},
        {"Symbol": "CM", "Subject": "Cloud", "Description": "Mid Type", "Value": t.get("CM", {}).get(cm, cm)},
        {"Symbol": "CH", "Subject": "Cloud", "Description": "High Type", "Value": t.get("CH", {}).get(ch, ch)},
    ]


def decode_31313_group(
    groups: List[str], start_index: int, tables: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Decodes the 31313 regional radiation/sonde metadata section:
    - sr rara sasa (solar correction, radiosonde model, tracking system).
    - 8GGgg (release time in hours and minutes).
    """
    t = tables or WMO_TABLES
    i = start_index
    results: List[Dict[str, Any]] = []

    # Check next group: sr rara sasa
    if i + 1 < len(groups) and len(groups[i + 1]) == 5:
        grp = groups[i + 1]
        sr, rara, sasa = grp[0], grp[1:3], grp[3:5]
        results.append(
            {"Symbol": "sr", "Subject": "Solar/Inst", "Description": "Solar Corr", "Value": t.get("Sr", {}).get(sr, sr)}
        )
        results.append(
            {"Symbol": "rara", "Subject": "Solar/Inst", "Description": "Sonde Type", "Value": t.get("rara", {}).get(rara, rara)}
        )
        results.append(
            {"Symbol": "sasa", "Subject": "Solar/Inst", "Description": "Tracking", "Value": t.get("sasa", {}).get(sasa, sasa)}
        )
        i += 1

    # Check next group: 8GGgg (Release time)
    if i + 1 < len(groups) and groups[i + 1].startswith("8") and len(groups[i + 1]) == 5:
        grp = groups[i + 1]
        gg_h, gg_m = grp[1:3], grp[3:5]
        results.append(
            {"Symbol": "8GGgg", "Subject": "Solar/Inst", "Description": "Time", "Value": f"{gg_h}:{gg_m}"}
        )
        i += 1

    # Skip optional 9xxxx group if present
    if i + 1 < len(groups) and groups[i + 1].startswith("9") and len(groups[i + 1]) == 5:
        i += 1

    return results, i + 1


# --- Message Parsing Logic ---


def clean_message(message: str) -> str:
    """Normalizes message string by removing equals signs and standardizing whitespace."""
    return message.replace("=", "").strip()


def parse_ttaa_ttcc(
    message: str, cloud_tables: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses TTAA and TTCC parts containing mandatory standard isobaric surfaces,
    tropopause levels, and maximum wind levels.
    """
    levels_data: List[Dict[str, Any]] = []
    special_data: List[Dict[str, Any]] = []

    clean_msg = clean_message(message)
    groups = clean_msg.split()

    standard_levels_ttaa = {
        "99": "Surface",
        "00": 1000,
        "92": 925,
        "85": 850,
        "70": 700,
        "50": 500,
        "40": 400,
        "30": 300,
        "25": 250,
        "20": 200,
        "15": 150,
        "10": 100,
    }
    standard_levels_ttcc = {
        "70": 70,
        "50": 50,
        "30": 30,
        "20": 20,
        "10": 10,
        "07": 7,
        "05": 5,
        "03": 3,
        "02": 2,
        "01": 1,
    }

    is_ttcc = "TTCC" in message
    standard_levels = standard_levels_ttcc if is_ttcc else standard_levels_ttaa

    i = 0
    while i < len(groups):
        g = groups[i]

        # Header skip (TTAA/TTCC + YYGGId + IIiii)
        if re.match(r"^(TTAA|TTCC)$", g):
            i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            continue

        # Tropopause (88PtPtPt)
        if g.startswith("88") and len(g) == 5:
            if g == "88999":
                i += 1
                continue
            try:
                pressure = int(g[2:])
                special_data.append(
                    {"Symbol": "PtPtPt", "Subject": "Tropopause", "Description": "Pressure", "Value": f"{pressure}hPa"}
                )

                t_grp = groups[i + 1] if i + 1 < len(groups) else None
                w_grp = groups[i + 2] if i + 2 < len(groups) else None

                if t_grp and len(t_grp) == 5:
                    t = decode_temperature(t_grp[:3], tables=cloud_tables)
                    d = decode_dewpoint_depression(t_grp[3:], tables=cloud_tables)
                    if t is not None:
                        special_data.append(
                            {"Symbol": "TtTtTt", "Subject": "Tropopause", "Description": "Temperature", "Value": f"{t}C"}
                        )
                    if t is not None and d is not None:
                        dw = calculate_dewpoint(t, d)
                        special_data.append(
                            {"Symbol": "DtDt", "Subject": "Tropopause", "Description": "Dewpoint", "Value": f"{dw}C"}
                        )

                if w_grp and len(w_grp) == 5:
                    wd, ws = decode_wind(w_grp)
                    if ws is not None:
                        val_str = f"VRB/{int(ws)}kt" if np.isnan(wd) else f"{int(wd)}/{int(ws)}kt"
                        special_data.append(
                            {"Symbol": "dtdtftft", "Subject": "Tropopause", "Description": "Wind", "Value": val_str}
                        )

                i += 3
                continue
            except (ValueError, IndexError):
                i += 1
                continue

        # Maximum Wind Level (77PmPmPm or 66PmPmPm)
        if (g.startswith("77") or g.startswith("66")) and len(g) == 5:
            if g in ["77999", "66999"]:
                i += 1
                continue
            try:
                pressure = int(g[2:])
                special_data.append(
                    {"Symbol": "PmPmPm", "Subject": "Max Wind", "Description": "Pressure", "Value": f"{pressure}hPa"}
                )

                wind_grp = groups[i + 1] if i + 1 < len(groups) else None
                if wind_grp and len(wind_grp) == 5:
                    wd, ws = decode_wind(wind_grp)
                    if ws is not None:
                        val_str = f"VRB/{int(ws)}kt" if np.isnan(wd) else f"{int(wd)}/{int(ws)}kt"
                        special_data.append(
                            {"Symbol": "dmdmfmfmfm", "Subject": "Max Wind", "Description": "Wind", "Value": val_str}
                        )

                i_next = i + 2
                # Check for vertical wind shear group: 4vbvbvava
                if i_next < len(groups) and groups[i_next].startswith("4") and len(groups[i_next]) == 5:
                    shear_grp = groups[i_next]
                    vb, va = shear_grp[1:3], shear_grp[3:5]
                    special_data.append(
                        {"Symbol": "vbvb", "Subject": "Max Wind", "Description": "Shear Below", "Value": f"{vb}kt"}
                    )
                    special_data.append(
                        {"Symbol": "vava", "Subject": "Max Wind", "Description": "Shear Above", "Value": f"{va}kt"}
                    )
                    i_next += 1

                i = i_next
                continue
            except (ValueError, IndexError):
                i += 1
                continue

        # Regional / Instrumentation group 31313
        if g == "31313":
            decoded_list, new_i = decode_31313_group(groups, i, cloud_tables)
            special_data.extend(decoded_list)
            i = new_i
            continue

        # Cloud group 41414
        if g == "41414":
            if i + 1 < len(groups):
                decoded_list = decode_cloud_group(groups[i + 1], cloud_tables)
                special_data.extend(decoded_list)
                i += 2
            else:
                i += 1
            continue

        # Regional groups to skip
        if g.startswith(("51515", "52525", "53535", "54545", "55555", "56565", "57575", "58585", "59595", "21212")):
            i += 1
            continue

        # Mandatory Standard Isobaric Levels (PPhhh)
        if len(g) == 5 and g[:2] in standard_levels:
            pp = g[:2]
            pressure, height = None, None
            if pp == "99":
                try:
                    p_val = int(g[2:])
                    pressure = 1000 + p_val if p_val < 100 else p_val
                except (ValueError, TypeError):
                    pass
            elif pp in standard_levels:
                try:
                    pressure = standard_levels[pp]
                    h_code = g[2:]
                    height = decode_height(pressure, h_code)
                except (ValueError, TypeError):
                    pass

            if pressure is not None:
                t_group = groups[i + 1] if i + 1 < len(groups) else None
                w_group = groups[i + 2] if i + 2 < len(groups) else None
                dp: Dict[str, Any] = {"Pressure": float(pressure), "Source": "Standard"}
                if height is not None:
                    dp["Height"] = height

                valid = False
                indicators = ("88", "77", "66", "51515", "31313", "41414")
                if t_group and len(t_group) == 5 and not t_group.startswith(indicators):
                    t = decode_temperature(t_group[:3], tables=cloud_tables)
                    d = decode_dewpoint_depression(t_group[3:], tables=cloud_tables)
                    dp["Temp"] = t
                    dp["DewPoint"] = calculate_dewpoint(t, d)
                    valid = True

                if w_group and len(w_group) == 5 and not w_group.startswith(indicators):
                    wd, ws = decode_wind(w_group)
                    dp["WindDir"] = wd
                    dp["WindSpeed"] = ws
                    valid = True

                if valid:
                    levels_data.append(dp)
                    i += 3
                    continue

        i += 1
    return levels_data, special_data


def parse_ttbb_ttdd(
    message: str, cloud_tables: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses TTBB and TTDD parts containing significant levels for temperature/humidity
    and significant wind levels (21212 section).
    Resilient to missing intermediate sequence groups caused by GTS transmission noise.
    """
    levels_data: List[Dict[str, Any]] = []
    special_data: List[Dict[str, Any]] = []
    clean_msg = clean_message(message)
    groups = clean_msg.split()
    mode = "TEMP"
    is_ttdd = "TTDD" in message
    last_p: Optional[float] = None

    i = 0
    while i < len(groups):
        g = groups[i]

        # Header skip (TTBB/TTDD + YYGGId + IIiii)
        if re.match(r"^(TTBB|TTDD)$", g):
            is_ttdd = (g == "TTDD")
            last_p = None
            i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            if i < len(groups) and re.match(r"^\d{5}$", groups[i]):
                i += 1
            continue

        # Wind section indicator
        if g == "21212":
            mode = "WIND"
            last_p = None
            i += 1
            continue

        # Special groups
        if g == "31313":
            decoded_list, new_i = decode_31313_group(groups, i, cloud_tables)
            special_data.extend(decoded_list)
            i = new_i
            continue

        if g == "41414":
            if i + 1 < len(groups):
                decoded_list = decode_cloud_group(groups[i + 1], cloud_tables)
                special_data.extend(decoded_list)
                i += 2
            else:
                i += 1
            continue

        if g == "51515":
            i += 1
            continue

        # Significant Level Group: nnPPP
        # nn is a repeating 2-digit sequence: 00, 11, 22, ..., 99, 11, 22...
        if len(g) == 5 and g[:2].isdigit():
            nn = g[:2]
            n_val = int(nn)

            # Valid significant level indicator: 00 or identical digits (11, 22, 33... 99)
            is_valid_level = (n_val == 0) or (n_val % 11 == 0)

            if not is_valid_level:
                i += 1
                continue

            try:
                ppp_part = int(g[2:])
                if nn == "00":
                    pressure = 1000.0 + ppp_part if ppp_part < 100 else float(ppp_part)
                else:
                    if not is_ttdd and ppp_part < 100 and (last_p is None or last_p >= 900.0):
                        pressure = 1000.0 + ppp_part
                    else:
                        pressure = float(ppp_part)

                # TTDD pressure is in tenths of hPa
                if is_ttdd:
                    pressure = pressure / 10.0

                last_p = pressure

                if mode == "TEMP":
                    t_group = groups[i + 1] if i + 1 < len(groups) else None
                    if t_group and len(t_group) == 5 and t_group != "21212":
                        t = decode_temperature(t_group[:3], tables=cloud_tables)
                        d = decode_dewpoint_depression(t_group[3:], tables=cloud_tables)
                        levels_data.append(
                            {
                                "Pressure": float(pressure),
                                "Temp": t,
                                "DewPoint": calculate_dewpoint(t, d),
                                "Source": "SigTemp",
                            }
                        )
                        i += 2
                        continue
                elif mode == "WIND":
                    w_group = groups[i + 1] if i + 1 < len(groups) else None
                    if w_group and len(w_group) == 5:
                        wd, ws = decode_wind(w_group)
                        levels_data.append(
                            {
                                "Pressure": float(pressure),
                                "WindDir": wd,
                                "WindSpeed": ws,
                                "Source": "SigWind",
                            }
                        )
                        i += 2
                        continue
            except (ValueError, IndexError):
                pass
        i += 1

    return levels_data, special_data


def merge_data(df_list: List[pd.DataFrame]) -> pd.DataFrame:
    """Merges all standard and significant levels, combining non-null values by pressure."""
    if not df_list:
        return pd.DataFrame()

    full_df = pd.concat(df_list, ignore_index=True)
    full_df = full_df[full_df["Pressure"].notna() & (full_df["Pressure"] > 0)].copy()

    # Round Pressure to integer
    full_df["Pressure"] = full_df["Pressure"].round(0).astype(int)

    # Combine records by pressure, giving precedence to non-null values
    grouped = (
        full_df.groupby("Pressure")
        .agg(
            {
                "Height": "first",
                "Temp": "first",
                "DewPoint": "first",
                "WindDir": "first",
                "WindSpeed": "first",
                "Source": "first",
            }
        )
        .reset_index()
    )

    if "Height" in grouped.columns:
        grouped["Height"] = grouped["Height"].astype(float).round(0).astype("Int64")

    return grouped.sort_values(by="Pressure", ascending=False).reset_index(drop=True)


# --- Public Interface ---


def decode_full(
    ttaa_msg: Optional[str] = None,
    ttbb_msg: Optional[str] = None,
    ttcc_msg: Optional[str] = None,
    ttdd_msg: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Decodes full FM 35 radiosonde sounding components (TTAA, TTBB, TTCC, TTDD).
    Returns (df_main, df_special).
    """
    cloud_tables = load_wmo_tables()

    data_frames: List[pd.DataFrame] = []
    special_frames: List[pd.DataFrame] = []

    for msg, parser in [
        (ttaa_msg, parse_ttaa_ttcc),
        (ttcc_msg, parse_ttaa_ttcc),
        (ttbb_msg, parse_ttbb_ttdd),
        (ttdd_msg, parse_ttbb_ttdd),
    ]:
        if msg and isinstance(msg, str):
            lvls, spcls = parser(msg, cloud_tables=cloud_tables)
            if lvls:
                data_frames.append(pd.DataFrame(lvls))
            if spcls:
                special_frames.append(pd.DataFrame(spcls))

    df_main = merge_data(data_frames)
    df_main = interpolate_data(df_main)
    df_main = calculate_geopotential(df_main)

    df_special = pd.concat(special_frames, ignore_index=True) if special_frames else pd.DataFrame()

    if not df_special.empty:
        if {"Symbol", "Subject", "Description", "Value"}.issubset(df_special.columns):
            df_special = df_special[["Symbol", "Subject", "Description", "Value"]]

        df_special = df_special.drop_duplicates()

        # Sort Cloud group by standard order: h, Nh, CL, CM, CH
        mask = df_special["Subject"] == "Cloud"
        if mask.any():
            order = {"h": 0, "Nh": 1, "CL": 2, "CM": 3, "CH": 4}
            clouds = df_special[mask].sort_values(by="Symbol", key=lambda col: col.map(order))
            others = df_special[~mask]
            df_special = pd.concat([clouds, others], ignore_index=True)

    return df_main, df_special


def decode(
    ttaa: Optional[str] = None,
    ttbb: Optional[str] = None,
    ttcc: Optional[str] = None,
    ttdd: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Main entry point for decoding standard FM 35 TEMP radiosonde messages.

    Parameters:
        ttaa: Part A message string (standard levels <= 100 hPa).
        ttbb: Part B message string (significant levels <= 100 hPa).
        ttcc: Part C message string (standard levels > 100 hPa).
        ttdd: Part D message string (significant levels > 100 hPa).

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]:
            - df_main: Vertical profile with Pressure, Height, Temp, DewPoint, WindDir, WindSpeed.
            - df_special: Tropopause, Maximum Wind, Cloud layers, and Radiosonde/Solar metadata.
    """
    # Defensive type validation
    for name, val in [("ttaa", ttaa), ("ttbb", ttbb), ("ttcc", ttcc), ("ttdd", ttdd)]:
        if val is not None and not isinstance(val, str):
            raise TypeError(f"Message argument '{name}' must be a string or None, got {type(val).__name__}")

    return decode_full(ttaa, ttbb, ttcc, ttdd)
