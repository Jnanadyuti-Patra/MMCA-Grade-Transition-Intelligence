from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

from .constants import PRODUCT_COLUMNS


def _read_excel(
    source: bytes | BinaryIO | str | Path,
    *,
    sheet_name: str,
    header: int,
) -> pd.DataFrame:
    if isinstance(source, bytes):
        source = BytesIO(source)

    try:
        return pd.read_excel(
            source,
            sheet_name=sheet_name,
            header=header,
            engine="calamine",
        )
    except Exception:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_excel(
            source,
            sheet_name=sheet_name,
            header=header,
            engine="openpyxl",
        )


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result.columns = [
        " ".join(str(column).replace("\n", " ").strip().split())
        for column in result.columns
    ]
    return result


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

    direct = pd.to_datetime(series.astype("string"), errors="coerce")
    direct_delta = (
        pd.to_timedelta(direct.dt.hour.fillna(0), unit="h")
        + pd.to_timedelta(direct.dt.minute.fillna(0), unit="m")
        + pd.to_timedelta(direct.dt.second.fillna(0), unit="s")
    )
    return numeric_delta.where(numeric.notna(), direct_delta)


def _truthy(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .isin({"1", "true", "yes", "y", "x", "checked"})
    )


def load_product_workbook(source: bytes | BinaryIO | str | Path) -> pd.DataFrame:
    df = _read_excel(source, sheet_name="Master", header=1)
    df = _normalise_columns(df)
    df = df.dropna(how="all").copy()

    required = ["Coil ID", "Date", "Start Time", "Grade"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            "The product workbook does not match the expected Metrod Master "
            f"sheet. Missing columns: {', '.join(missing)}"
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

    weight = pd.to_numeric(
        result["Net"] if "Net" in result.columns else np.nan,
        errors="coerce",
    )
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
    return result


def load_process_workbook(source: bytes | BinaryIO | str | Path) -> pd.DataFrame:
    df = _read_excel(source, sheet_name="Process_Values", header=0)
    df = _normalise_columns(df)
    df = df.dropna(how="all").copy()

    if "Time" not in df.columns:
        raise ValueError(
            "The process workbook does not contain the expected 'Time' column."
        )

    process_time = _excel_datetime(df["Time"])
    result = df.loc[process_time.notna()].copy()
    result["ProcessTime"] = process_time.loc[result.index]
    result = result.sort_values("ProcessTime", kind="stable")
    result = result.drop_duplicates("ProcessTime", keep="last").reset_index(drop=True)
    return result
