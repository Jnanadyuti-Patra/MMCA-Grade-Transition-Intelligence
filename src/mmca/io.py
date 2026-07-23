from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

from .constants import PRODUCT_COLUMNS


PRODUCT_SHEET_CANDIDATES = ("Master", "Master_Simplified")
PROCESS_SHEET_CANDIDATES = ("Process_Values",)
MAX_HEADER_SCAN_ROWS = 8

# Normalise common column-name variants to the canonical names used by the
# analysis and grading modules. This lets the app accept both the full Master
# sheet and the lighter Master_Simplified sheet supplied by Metrod.
PRODUCT_COLUMN_VARIANTS = {
    "15 X 15 Twist Test (Index)": "15/15 Twist Test",
    "15 x 15 Twist Test (Index)": "15/15 Twist Test",
    "25 RTF Twist Test (Number)": "F/R 25 twist",
    "Oxide Content (Å)": "Total Oxide",
    "Oxide Content (A)": "Total Oxide",
    "Large Defect in Defectomat": "Large surface",
    "Medium Defect in Defectomat": "Medium Surface",
    "Small Defect in Defectomat": "Small Surface",
    "Large Defect in Ferromat": "Large Ferrous",
    "Medium Defect in Ferromat": "Medium Ferrous",
    "Small Defect in Ferromat": "Small Ferrous",
    "Net Weight": "Net",
    "Coil Weight": "Net",
}


def _source_for_reuse(source: bytes | BinaryIO | str | Path):
    """Return a seekable source that can be read repeatedly."""
    if isinstance(source, bytes):
        return BytesIO(source)
    return source


def _reset_source(source) -> None:
    if hasattr(source, "seek"):
        source.seek(0)


def _excel_file(source):
    """Open an ExcelFile with calamine first and openpyxl as fallback."""
    _reset_source(source)
    try:
        return pd.ExcelFile(source, engine="calamine")
    except Exception:
        _reset_source(source)
        return pd.ExcelFile(source, engine="openpyxl")


def _read_excel(
    source: bytes | BinaryIO | str | Path,
    *,
    sheet_name: str,
    header: int,
) -> pd.DataFrame:
    source = _source_for_reuse(source)
    _reset_source(source)
    try:
        return pd.read_excel(
            source,
            sheet_name=sheet_name,
            header=header,
            engine="calamine",
        )
    except Exception:
        _reset_source(source)
        return pd.read_excel(
            source,
            sheet_name=sheet_name,
            header=header,
            engine="openpyxl",
        )


def _normalise_name(value: object) -> str:
    return " ".join(str(value).replace("\n", " ").strip().split())


def _normalise_key(value: object) -> str:
    return _normalise_name(value).casefold()


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = [_normalise_name(column) for column in result.columns]
    return result


def _rename_known_variants(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {_normalise_key(column): column for column in df.columns}
    rename_map: dict[str, str] = {}
    for variant, canonical in PRODUCT_COLUMN_VARIANTS.items():
        actual = lookup.get(_normalise_key(variant))
        if actual is not None and canonical not in df.columns:
            rename_map[actual] = canonical
    return df.rename(columns=rename_map)


def _find_column(columns, aliases: list[str]) -> str | None:
    lookup = {_normalise_key(column): str(column) for column in columns}
    for alias in aliases:
        match = lookup.get(_normalise_key(alias))
        if match is not None:
            return match
    return None


def _canonicalise_product_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = _rename_known_variants(_normalise_columns(df))
    rename_map: dict[str, str] = {}
    canonical_names = {
        "coil_id": "Coil ID",
        "internal_id": "9 Digit Internal Coil ID",
        "date": "Date",
        "start_time": "Start Time",
        "finish_time": "Finish Time",
        "grade": "Grade",
        "net_weight": "Net",
        "downgrade_code": "Downgrade code",
        "manual_selected": "Check Box Manual selected",
        "manual_remarks": "Txt_Manual_Grading_Remarks",
        "remarks": "Remarks",
        "contaminated": "Contaminated",
    }
    for key, aliases in PRODUCT_COLUMNS.items():
        actual = _find_column(result.columns, aliases)
        canonical = canonical_names[key]
        if actual is not None and actual != canonical and canonical not in result.columns:
            rename_map[actual] = canonical
    return result.rename(columns=rename_map)


def _detect_product_table(source) -> tuple[pd.DataFrame, str, int, list[str]]:
    """Find the Metrod product table without assuming a fixed header row."""
    source = _source_for_reuse(source)
    workbook = _excel_file(source)
    sheet_names = workbook.sheet_names

    ordered_sheets = [
        sheet for candidate in PRODUCT_SHEET_CANDIDATES
        for sheet in sheet_names
        if _normalise_key(sheet) == _normalise_key(candidate)
    ]
    ordered_sheets.extend(sheet for sheet in sheet_names if sheet not in ordered_sheets)

    required = ["Coil ID", "Date", "Start Time", "Grade"]
    diagnostics: list[str] = []

    for sheet in ordered_sheets:
        for header_row in range(MAX_HEADER_SCAN_ROWS):
            try:
                candidate = _read_excel(
                    source,
                    sheet_name=sheet,
                    header=header_row,
                )
            except Exception as error:
                diagnostics.append(f"{sheet!r}, row {header_row + 1}: {error}")
                continue

            candidate = _canonicalise_product_columns(candidate)
            missing = [column for column in required if column not in candidate.columns]
            if not missing:
                return candidate, sheet, header_row, sheet_names

            if header_row <= 2:
                sample = ", ".join(map(str, list(candidate.columns)[:8]))
                diagnostics.append(
                    f"{sheet!r}, row {header_row + 1}: missing "
                    f"{', '.join(missing)}; detected {sample}"
                )

    detail = " | ".join(diagnostics[:8])
    raise ValueError(
        "The product workbook does not contain a recognisable Metrod product "
        "table. The application searched every sheet and the first "
        f"{MAX_HEADER_SCAN_ROWS} possible header rows. Available sheets: "
        f"{', '.join(sheet_names)}. Expected columns include Coil ID, Date, "
        f"Start Time and Grade. Detection details: {detail}"
    )


def _detect_process_table(source) -> tuple[pd.DataFrame, str, int, list[str]]:
    source = _source_for_reuse(source)
    workbook = _excel_file(source)
    sheet_names = workbook.sheet_names

    ordered_sheets = [
        sheet for candidate in PROCESS_SHEET_CANDIDATES
        for sheet in sheet_names
        if _normalise_key(sheet) == _normalise_key(candidate)
    ]
    ordered_sheets.extend(sheet for sheet in sheet_names if sheet not in ordered_sheets)

    diagnostics: list[str] = []
    for sheet in ordered_sheets:
        for header_row in range(MAX_HEADER_SCAN_ROWS):
            try:
                candidate = _read_excel(
                    source,
                    sheet_name=sheet,
                    header=header_row,
                )
            except Exception as error:
                diagnostics.append(f"{sheet!r}, row {header_row + 1}: {error}")
                continue
            candidate = _normalise_columns(candidate)
            time_column = _find_column(
                candidate.columns,
                ["Time", "Timestamp", "Date Time", "DateTime", "Datetime"],
            )
            if time_column is not None:
                if time_column != "Time" and "Time" not in candidate.columns:
                    candidate = candidate.rename(columns={time_column: "Time"})
                return candidate, sheet, header_row, sheet_names

            if header_row <= 2:
                sample = ", ".join(map(str, list(candidate.columns)[:8]))
                diagnostics.append(
                    f"{sheet!r}, row {header_row + 1}: no timestamp column; "
                    f"detected {sample}"
                )

    detail = " | ".join(diagnostics[:8])
    raise ValueError(
        "The process workbook does not contain a recognisable timestamped "
        f"process table. Available sheets: {', '.join(sheet_names)}. "
        f"Detection details: {detail}"
    )


def _excel_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")

    numeric = pd.to_numeric(series, errors="coerce")
    numeric_dates = pd.to_datetime(
        numeric,
        unit="D",
        origin="1899-12-30",
        errors="coerce",
    )
    direct_dates = pd.to_datetime(series, errors="coerce")
    return numeric_dates.where(numeric_dates.notna(), direct_dates)


def _time_delta(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_delta = pd.to_timedelta(numeric, unit="D", errors="coerce")

    # Excel time cells may arrive as datetime.time objects, strings, or a
    # fractional day. Converting the textual representation directly to a
    # timedelta handles both time objects and HH:MM:SS strings without
    # assigning an unrelated calendar date.
    text_delta = pd.to_timedelta(series.astype("string"), errors="coerce")
    return numeric_delta.where(numeric.notna(), text_delta)


def _truthy(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin({"1", "true", "yes", "y", "x", "checked"})
    )


def load_product_workbook(source: bytes | BinaryIO | str | Path) -> pd.DataFrame:
    df, source_sheet, header_row, sheet_names = _detect_product_table(source)
    df = df.dropna(how="all").copy()

    required = ["Coil ID", "Date", "Start Time", "Grade"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        # This is defensive; _detect_product_table already guarantees these.
        raise ValueError(
            "The detected product table is missing required columns: "
            + ", ".join(missing)
        )

    date = _excel_datetime(df["Date"]).dt.normalize()
    start = date + _time_delta(df["Start Time"])

    if "Finish Time" in df.columns:
        finish = date + _time_delta(df["Finish Time"])
    else:
        finish = pd.Series(pd.NaT, index=df.index)

    grade = pd.to_numeric(df["Grade"], errors="coerce")
    result = df.loc[
        df["Coil ID"].notna()
        & grade.between(0, 7)
        & start.notna()
    ].copy()

    result["CoilID"] = result["Coil ID"].astype("string").str.strip()
    result["Grade"] = pd.to_numeric(result["Grade"], errors="coerce").astype(int)
    result["StartDateTime"] = start.loc[result.index]
    result["FinishDateTime"] = finish.loc[result.index]

    result = result.sort_values(
        ["StartDateTime", "CoilID"],
        kind="stable",
    ).reset_index(drop=True)

    # Use the next coil start when the recorded finish is absent or implausible.
    next_start = result["StartDateTime"].shift(-1)
    crosses_midnight = (
        result["FinishDateTime"].notna()
        & (result["FinishDateTime"] < result["StartDateTime"])
    )
    result.loc[crosses_midnight, "FinishDateTime"] += pd.Timedelta(days=1)

    duration = (
        result["FinishDateTime"] - result["StartDateTime"]
    ).dt.total_seconds() / 60.0
    invalid_finish = (
        result["FinishDateTime"].isna()
        | duration.le(0)
        | duration.gt(180)
    )
    result.loc[invalid_finish, "FinishDateTime"] = next_start.loc[invalid_finish]
    result["FinishDateTime"] = result["FinishDateTime"].fillna(
        result["StartDateTime"] + pd.Timedelta(minutes=10)
    )

    result["DurationMinutes"] = (
        result["FinishDateTime"] - result["StartDateTime"]
    ).dt.total_seconds() / 60.0

    if "Net" in result.columns:
        weight = pd.to_numeric(result["Net"], errors="coerce")
    else:
        weight = pd.Series(np.nan, index=result.index, dtype=float)
    if weight.notna().any() and weight.median() > 100:
        weight = weight / 1000.0
    result["WeightMT"] = weight

    result["CoilKey"] = np.arange(1, len(result) + 1, dtype=int)
    result["ProductionDate"] = result["StartDateTime"].dt.date

    manual_text = pd.Series("", index=result.index, dtype="string")
    for column in ["Txt_Manual_Grading_Remarks", "Remarks"]:
        if column in result.columns:
            manual_text = manual_text.str.cat(
                result[column].astype("string").fillna(""),
                sep=" ",
            )

    manual_selected = (
        _truthy(result["Check Box Manual selected"])
        if "Check Box Manual selected" in result.columns
        else pd.Series(False, index=result.index)
    )
    contaminated = (
        _truthy(result["Contaminated"])
        if "Contaminated" in result.columns
        else pd.Series(False, index=result.index)
    )

    result["EventContext"] = np.select(
        [
            contaminated,
            manual_selected | manual_text.str.contains(
                r"manual|manul|manaul", case=False, regex=True, na=False
            ),
            manual_text.str.contains(
                r"start.?up|startup|plant start", case=False, regex=True, na=False
            ),
            manual_text.str.contains(
                r"plant stop|shutdown|stoppage", case=False, regex=True, na=False
            ),
        ],
        [
            "Contaminated coil",
            "Manual grade",
            "Startup",
            "Shutdown / stoppage",
        ],
        default="Normal production",
    )
    result["CombinedRemarks"] = manual_text.str.strip()

    # Metadata is useful to the UI and survives Streamlit's data cache.
    result.attrs["source_sheet"] = source_sheet
    result.attrs["header_row"] = header_row + 1
    result.attrs["available_sheets"] = sheet_names
    return result


def load_process_workbook(source: bytes | BinaryIO | str | Path) -> pd.DataFrame:
    df, source_sheet, header_row, sheet_names = _detect_process_table(source)
    df = df.dropna(how="all").copy()

    process_time = _excel_datetime(df["Time"])
    result = df.loc[process_time.notna()].copy()
    result["ProcessTime"] = process_time.loc[result.index]
    result = result.sort_values("ProcessTime", kind="stable")
    result = result.drop_duplicates("ProcessTime", keep="last").reset_index(drop=True)
    result.attrs["source_sheet"] = source_sheet
    result.attrs["header_row"] = header_row + 1
    result.attrs["available_sheets"] = sheet_names
    return result
