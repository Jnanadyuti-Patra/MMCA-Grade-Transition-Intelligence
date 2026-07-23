from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import PRODUCT_PARAMETER_COLUMNS


def load_grading_revisions(path: str | Path) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    revisions = payload["revisions"]
    revisions.sort(key=lambda item: item["effective_from"])
    return revisions


def select_revision(revisions: list[dict], production_date) -> dict:
    timestamp = pd.Timestamp(production_date)
    selected = revisions[0]
    for revision in revisions:
        if timestamp >= pd.Timestamp(revision["effective_from"]):
            selected = revision
    return selected


def _satisfies(value: float, criterion: dict | None) -> bool:
    if criterion is None or pd.isna(value):
        return False

    operation = criterion["op"]
    if operation == "between":
        return criterion["min"] <= value <= criterion["max"]
    if operation == "eq":
        return np.isclose(value, criterion["value"], equal_nan=False)
    if operation == "gt":
        return value > criterion["value"]
    if operation == "gte":
        return value >= criterion["value"]
    if operation == "lt":
        return value < criterion["value"]
    if operation == "lte":
        return value <= criterion["value"]
    return False


def parameter_grade(
    parameter: str,
    value,
    revision: dict,
) -> int | None:
    criteria = revision["parameters"].get(parameter)
    if not criteria:
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    for grade in range(7, -1, -1):
        if _satisfies(numeric_value, criteria.get(str(grade))):
            return grade
    return None


def diameter_grade(
    minimum,
    maximum,
    revision: dict,
) -> int | None:
    criteria = revision["parameters"].get("Diameter")
    if not criteria:
        return None

    try:
        minimum = float(minimum)
        maximum = float(maximum)
    except (TypeError, ValueError):
        return None

    for grade in range(7, -1, -1):
        criterion = criteria.get(str(grade))
        if not criterion:
            continue
        if (
            criterion["op"] == "between"
            and minimum >= criterion["min"]
            and maximum <= criterion["max"]
        ):
            return grade
    return None


def evaluate_product_parameters(
    coils: pd.DataFrame,
    revisions: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows = []
    summary_rows = []

    for row_data in coils.to_dict(orient="records"):
        revision = select_revision(revisions, row_data["StartDateTime"])
        evaluated = []

        for parameter, specification in PRODUCT_PARAMETER_COLUMNS.items():
            columns = specification["columns"]
            if not all(column in coils.columns for column in columns):
                continue

            if specification["kind"] == "pair":
                values = [row_data.get(column) for column in columns]
                grade = diameter_grade(values[0], values[1], revision)
                measured = " to ".join(
                    "" if pd.isna(value) else f"{float(value):.4g}"
                    for value in values
                )
            else:
                measured_value = row_data.get(columns[0])
                grade = parameter_grade(parameter, measured_value, revision)
                measured = measured_value

            if grade is None:
                continue

            evaluated.append((parameter, grade))
            detail_rows.append(
                {
                    "CoilKey": row_data["CoilKey"],
                    "CoilID": row_data["CoilID"],
                    "Parameter": parameter,
                    "ParameterGroup": specification["group"],
                    "MeasuredValue": measured,
                    "ParameterGrade": grade,
                    "RuleRevision": revision["revision"],
                }
            )

        if evaluated:
            computed_grade = min(grade for _, grade in evaluated)
            limiting = [
                parameter
                for parameter, grade in evaluated
                if grade == computed_grade
            ]
        else:
            computed_grade = np.nan
            limiting = []

        summary_rows.append(
            {
                "CoilKey": row_data["CoilKey"],
                "ComputedProductGrade": computed_grade,
                "LimitingProductParameters": " | ".join(limiting),
                "ParametersEvaluated": len(evaluated),
                "RuleRevision": revision["revision"],
            }
        )

    return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows)


def identify_product_triggers(
    transitions: pd.DataFrame,
    parameter_detail: pd.DataFrame,
) -> pd.DataFrame:
    if transitions.empty or parameter_detail.empty:
        return pd.DataFrame(
            columns=[
                "TransitionID", "TransitionKey", "Parameter",
                "ParameterGroup", "PreviousValue", "CurrentValue",
                "PreviousParameterGrade", "CurrentParameterGrade",
                "ParameterGradeDelta", "TriggerScore", "TriggerRank",
            ]
        )

    current = parameter_detail.rename(
        columns={
            "CoilKey": "CurrentCoilKey",
            "MeasuredValue": "CurrentValue",
            "ParameterGrade": "CurrentParameterGrade",
        }
    )
    previous = parameter_detail.rename(
        columns={
            "CoilKey": "PreviousCoilKey",
            "MeasuredValue": "PreviousValue",
            "ParameterGrade": "PreviousParameterGrade",
        }
    )

    events = transitions[
        [
            "TransitionID",
            "TransitionKey",
            "CoilKey",
            "PreviousCoilKey",
            "PreviousGrade",
            "Grade",
            "TransitionType",
        ]
    ].rename(columns={"CoilKey": "CurrentCoilKey"})

    merged = events.merge(
        current[
            [
                "CurrentCoilKey",
                "Parameter",
                "ParameterGroup",
                "CurrentValue",
                "CurrentParameterGrade",
            ]
        ],
        on="CurrentCoilKey",
        how="left",
    ).merge(
        previous[
            [
                "PreviousCoilKey",
                "Parameter",
                "PreviousValue",
                "PreviousParameterGrade",
            ]
        ],
        on=["PreviousCoilKey", "Parameter"],
        how="left",
    )

    merged["ParameterGradeDelta"] = (
        merged["CurrentParameterGrade"]
        - merged["PreviousParameterGrade"]
    )

    downgrade = (
        merged["TransitionType"].eq("Downgrade")
        & merged["ParameterGradeDelta"].lt(0)
    )
    upgrade = (
        merged["TransitionType"].eq("Upgrade")
        & merged["ParameterGradeDelta"].gt(0)
    )
    relevant = merged.loc[downgrade | upgrade].copy()

    relevant["TriggerStrength"] = relevant["ParameterGradeDelta"].abs()
    relevant["MatchesRecordedDirection"] = np.where(
        relevant["TransitionType"].eq("Downgrade"),
        relevant["CurrentParameterGrade"].le(relevant["Grade"]),
        relevant["CurrentParameterGrade"].ge(relevant["Grade"]),
    )
    relevant["TriggerScore"] = (
        70 * relevant["MatchesRecordedDirection"].astype(float)
        + 15 * relevant["TriggerStrength"].clip(upper=2)
        + 15 * (
            1
            - (
                relevant["CurrentParameterGrade"] - relevant["Grade"]
            ).abs().clip(upper=3) / 3
        )
    )
    relevant = relevant.sort_values(
        ["TransitionKey", "TriggerScore", "Parameter"],
        ascending=[True, False, True],
    )
    relevant["TriggerRank"] = relevant.groupby("TransitionKey").cumcount() + 1

    return relevant[
        [
            "TransitionID",
            "TransitionKey",
            "Parameter",
            "ParameterGroup",
            "PreviousValue",
            "CurrentValue",
            "PreviousParameterGrade",
            "CurrentParameterGrade",
            "ParameterGradeDelta",
            "TriggerScore",
            "TriggerRank",
        ]
    ].reset_index(drop=True)
