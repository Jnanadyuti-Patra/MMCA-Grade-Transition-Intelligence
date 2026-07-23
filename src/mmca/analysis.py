from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .constants import (
    ACTION_LIBRARY,
    IMPORTANT_PROCESS_PARAMETERS,
    PROCESS_GROUP_RELEVANCE,
    PROCESS_PLAUSIBLE_RANGES,
)


@dataclass(frozen=True)
class AnalysisSettings:
    baseline_coils: int = 5
    process_lag_minutes: float = 0.0
    minimum_candidate_score: float = 25.0


def detect_transitions(coils: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched = coils.copy()
    enriched["PreviousGrade"] = enriched["Grade"].shift(1)
    enriched["PreviousCoilKey"] = enriched["CoilKey"].shift(1)
    enriched["PreviousCoilID"] = enriched["CoilID"].shift(1)
    enriched["GradeChanged"] = enriched["Grade"].ne(enriched["PreviousGrade"])
    if not enriched.empty:
        enriched.loc[enriched.index[0], "GradeChanged"] = False

    enriched["RunID"] = enriched["Grade"].ne(
        enriched["Grade"].shift(1)
    ).cumsum()
    enriched["RunLength"] = (
        enriched.groupby("RunID")["CoilKey"].transform("size")
    )
    enriched["RunWeightMT"] = (
        enriched.groupby("RunID")["WeightMT"].transform("sum")
    )
    enriched["SingleCoilRun"] = enriched["RunLength"].eq(1)

    events = enriched.loc[enriched["GradeChanged"]].copy()
    events["TransitionKey"] = np.arange(1, len(events) + 1)
    events["TransitionID"] = events["TransitionKey"].map(
        lambda value: f"TR-{value:05d}"
    )
    events["TransitionType"] = np.where(
        events["Grade"] > events["PreviousGrade"],
        "Upgrade",
        "Downgrade",
    )
    events["GradePair"] = (
        events["PreviousGrade"].astype("Int64").astype("string")
        + " → "
        + events["Grade"].astype("Int64").astype("string")
    )
    events["GradeDelta"] = events["Grade"] - events["PreviousGrade"]
    events["PersistenceCoils"] = events["RunLength"]
    events["AffectedWeightMT"] = events["RunWeightMT"]
    events["TransientOneCoil"] = events["SingleCoilRun"]

    event_columns = [
        "TransitionKey",
        "TransitionID",
        "CoilKey",
        "CoilID",
        "PreviousCoilKey",
        "PreviousCoilID",
        "PreviousGrade",
        "Grade",
        "GradePair",
        "GradeDelta",
        "TransitionType",
        "StartDateTime",
        "FinishDateTime",
        "PersistenceCoils",
        "AffectedWeightMT",
        "TransientOneCoil",
        "EventContext",
        "CombinedRemarks",
    ]
    return enriched, events[event_columns].reset_index(drop=True)


def select_important_process_columns(process: pd.DataFrame) -> list[str]:
    return [
        column
        for column in IMPORTANT_PROCESS_PARAMETERS
        if column in process.columns
    ]


def clean_process_values(
    process: pd.DataFrame,
    parameters: Iterable[str],
) -> pd.DataFrame:
    cleaned = process.copy()
    for parameter in parameters:
        numeric = pd.to_numeric(cleaned[parameter], errors="coerce")
        minimum, maximum = PROCESS_PLAUSIBLE_RANGES.get(
            parameter,
            (-np.inf, np.inf),
        )
        cleaned[parameter] = numeric.where(
            numeric.between(minimum, maximum)
        )
    return cleaned


def process_data_quality(
    process: pd.DataFrame,
    parameters: Iterable[str],
) -> pd.DataFrame:
    rows = []
    for parameter in parameters:
        numeric = pd.to_numeric(process[parameter], errors="coerce")
        unique = numeric.nunique(dropna=True)
        rows.append(
            {
                "Parameter": parameter,
                "ParameterGroup": IMPORTANT_PROCESS_PARAMETERS[parameter],
                "ValidValues": int(numeric.notna().sum()),
                "MissingValues": int(numeric.isna().sum()),
                "MissingFraction": float(numeric.isna().mean()),
                "UniqueValues": int(unique),
                "FrozenChannel": bool(unique <= 1),
                "Minimum": numeric.min(),
                "Maximum": numeric.max(),
                "P01": numeric.quantile(0.01),
                "P99": numeric.quantile(0.99),
            }
        )
    return pd.DataFrame(rows)


def map_process_to_coils(
    process: pd.DataFrame,
    coils: pd.DataFrame,
    parameters: list[str],
    *,
    lag_minutes: float,
) -> pd.DataFrame:
    work = process[["ProcessTime", *parameters]].copy()
    for parameter in parameters:
        work[parameter] = pd.to_numeric(work[parameter], errors="coerce")

    delay = pd.to_timedelta(lag_minutes, unit="m")
    windows = coils[
        ["CoilKey", "StartDateTime", "FinishDateTime"]
    ].copy()
    windows["InfluenceStart"] = windows["StartDateTime"] - delay
    windows["InfluenceFinish"] = windows["FinishDateTime"] - delay
    windows = windows.sort_values("InfluenceStart")

    mapped = pd.merge_asof(
        work.sort_values("ProcessTime"),
        windows,
        left_on="ProcessTime",
        right_on="InfluenceStart",
        direction="backward",
        allow_exact_matches=True,
    )
    mapped = mapped.loc[
        mapped["CoilKey"].notna()
        & mapped["ProcessTime"].le(mapped["InfluenceFinish"])
    ].copy()
    mapped["CoilKey"] = mapped["CoilKey"].astype(int)
    return mapped


def aggregate_process_features(
    mapped: pd.DataFrame,
    parameters: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if mapped.empty or not parameters:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    means = mapped.groupby("CoilKey")[parameters].mean()
    counts = mapped.groupby("CoilKey")[parameters].count()
    first = mapped.groupby("CoilKey")[parameters].first()
    last = mapped.groupby("CoilKey")[parameters].last()

    long = (
        means.stack()
        .rename("Mean")
        .to_frame()
        .join(counts.stack().rename("SampleCount"))
        .join(first.stack().rename("First"))
        .join(last.stack().rename("Last"))
        .reset_index()
        .rename(columns={"level_1": "Parameter"})
    )
    long["WithinCoilDelta"] = long["Last"] - long["First"]
    long["ParameterGroup"] = long["Parameter"].map(
        IMPORTANT_PROCESS_PARAMETERS
    )
    return means, counts, long


def _robust_scale(values: pd.Series, fallback: float) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if len(values) < 2:
        return fallback if fallback > 0 else 1.0
    median = values.median()
    mad = (values - median).abs().median()
    if mad > 0:
        return 1.4826 * mad
    std = values.std(ddof=0)
    return std if std > 0 else (fallback if fallback > 0 else 1.0)


def _trigger_group_map(product_triggers: pd.DataFrame) -> dict[str, str]:
    if product_triggers.empty:
        return {}
    first = (
        product_triggers.sort_values(["TransitionKey", "TriggerRank"])
        .drop_duplicates("TransitionID")
    )
    return first.set_index("TransitionID")["ParameterGroup"].to_dict()


def rank_process_candidates(
    coils: pd.DataFrame,
    transitions: pd.DataFrame,
    means: pd.DataFrame,
    counts: pd.DataFrame,
    data_quality: pd.DataFrame,
    product_triggers: pd.DataFrame,
    settings: AnalysisSettings,
) -> pd.DataFrame:
    if transitions.empty or means.empty:
        return pd.DataFrame(
            columns=[
                "TransitionKey", "TransitionID", "Parameter",
                "ParameterGroup", "CurrentMean", "PreviousMean",
                "BaselineMedian", "RobustZ", "StepZ", "SampleCount",
                "PhysicalRelevance", "CandidateScore", "CandidateRank",
                "ConfidenceBand",
            ]
        )

    quality = data_quality.set_index("Parameter")
    trigger_groups = _trigger_group_map(product_triggers)
    coil_position = {
        key: position
        for position, key in enumerate(coils["CoilKey"].tolist())
    }
    global_scale = {
        parameter: _robust_scale(means[parameter], 1.0)
        for parameter in means.columns
    }

    rows = []
    for event in transitions.itertuples(index=False):
        current_key = int(event.CoilKey)
        previous_key = int(event.PreviousCoilKey)
        position = coil_position.get(current_key)

        if (
            position is None
            or current_key not in means.index
            or previous_key not in means.index
        ):
            continue

        baseline_frame = coils.iloc[
            max(0, position - settings.baseline_coils):position
        ]
        baseline_keys = baseline_frame.loc[
            baseline_frame["Grade"].eq(int(event.PreviousGrade)),
            "CoilKey",
        ].tolist()
        if len(baseline_keys) < 2:
            baseline_keys = baseline_frame["CoilKey"].tolist()

        product_group = trigger_groups.get(event.TransitionID)

        candidates = []
        for parameter in means.columns:
            q = quality.loc[parameter]
            if (
                bool(q["FrozenChannel"])
                or float(q["MissingFraction"]) > 0.50
            ):
                continue

            current = means.at[current_key, parameter]
            previous = means.at[previous_key, parameter]
            baseline_values = means.loc[
                means.index.intersection(baseline_keys), parameter
            ].dropna()

            if pd.isna(current) or len(baseline_values) < 2:
                continue

            baseline_median = baseline_values.median()
            local_scale = _robust_scale(
                baseline_values,
                global_scale[parameter],
            )
            robust_z = abs(current - baseline_median) / local_scale
            step_z = (
                abs(current - previous) / global_scale[parameter]
                if pd.notna(previous)
                else 0.0
            )
            completeness = min(
                float(counts.at[current_key, parameter]) / 5.0,
                1.0,
            )

            process_group = IMPORTANT_PROCESS_PARAMETERS[parameter]
            relevance = 0.55
            if product_group:
                relevance = PROCESS_GROUP_RELEVANCE.get(
                    product_group, {}
                ).get(process_group, 0.40)

            score = 100 * (
                0.45 * min(robust_z / 4.0, 1.0)
                + 0.25 * min(step_z / 4.0, 1.0)
                + 0.15 * completeness
                + 0.15 * relevance
            )

            if score < settings.minimum_candidate_score:
                continue

            candidates.append(
                {
                    "TransitionKey": event.TransitionKey,
                    "TransitionID": event.TransitionID,
                    "Parameter": parameter,
                    "ParameterGroup": process_group,
                    "CurrentMean": current,
                    "PreviousMean": previous,
                    "BaselineMedian": baseline_median,
                    "RobustZ": robust_z,
                    "StepZ": step_z,
                    "SampleCount": counts.at[current_key, parameter],
                    "PhysicalRelevance": relevance,
                    "CandidateScore": score,
                }
            )

        candidates.sort(
            key=lambda item: item["CandidateScore"],
            reverse=True,
        )
        for rank, candidate in enumerate(candidates[:8], start=1):
            candidate["CandidateRank"] = rank
            candidate["ConfidenceBand"] = (
                "High"
                if candidate["CandidateScore"] >= 75
                else "Moderate"
                if candidate["CandidateScore"] >= 50
                else "Low"
            )
            rows.append(candidate)

    return pd.DataFrame(rows)


def root_cause_contributions(
    transitions: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if transitions.empty or candidates.empty:
        return (
            pd.DataFrame(
                columns=[
                    "ParameterGroup", "ContributionWeight",
                    "ContributionPct",
                ]
            ),
            pd.DataFrame(
                columns=[
                    "ParameterGroup", "Parameter",
                    "ContributionWeight", "ContributionPct",
                ]
            ),
        )

    event_weight = transitions.set_index("TransitionID")[
        "AffectedWeightMT"
    ].fillna(1.0)

    selected = candidates.loc[
        candidates["CandidateRank"].le(5)
    ].copy()
    selected["EventScoreTotal"] = selected.groupby("TransitionID")[
        "CandidateScore"
    ].transform("sum")
    selected["EventContribution"] = (
        selected["CandidateScore"] / selected["EventScoreTotal"]
    )
    selected["EventWeight"] = selected["TransitionID"].map(
        event_weight
    ).fillna(1.0)
    selected["WeightedContribution"] = (
        selected["EventContribution"] * selected["EventWeight"]
    )

    group_summary = (
        selected.groupby("ParameterGroup", as_index=False)[
            "WeightedContribution"
        ]
        .sum()
        .rename(columns={"WeightedContribution": "ContributionWeight"})
    )
    group_summary["ContributionPct"] = (
        group_summary["ContributionWeight"]
        / group_summary["ContributionWeight"].sum()
        * 100
    )
    group_summary = group_summary.sort_values(
        "ContributionPct", ascending=False
    )

    parameter_summary = (
        selected.groupby(
            ["ParameterGroup", "Parameter"],
            as_index=False,
        )["WeightedContribution"]
        .sum()
        .rename(columns={"WeightedContribution": "ContributionWeight"})
    )
    parameter_summary["ContributionPct"] = (
        parameter_summary["ContributionWeight"]
        / parameter_summary["ContributionWeight"].sum()
        * 100
    )
    parameter_summary = parameter_summary.sort_values(
        "ContributionPct", ascending=False
    )
    return group_summary, parameter_summary


def build_recommendations(
    group_contributions: pd.DataFrame,
    product_triggers: pd.DataFrame,
    data_quality: pd.DataFrame,
    transitions: pd.DataFrame,
) -> list[dict]:
    recommendations = []

    for row in group_contributions.head(4).itertuples(index=False):
        item = ACTION_LIBRARY.get(row.ParameterGroup)
        if not item:
            continue
        recommendations.append(
            {
                "Priority": len(recommendations) + 1,
                "RootCauseGroup": row.ParameterGroup,
                "ContributionPct": row.ContributionPct,
                "Recommendation": item["title"],
                "Actions": item["actions"],
                "Verification": item["verification"],
            }
        )

    if not product_triggers.empty:
        chemistry_share = (
            product_triggers.loc[
                product_triggers["ParameterGroup"].eq("Chemistry")
                & product_triggers["TriggerRank"].eq(1)
            ].shape[0]
            / max(
                product_triggers.loc[
                    product_triggers["TriggerRank"].eq(1),
                    "TransitionID",
                ].nunique(),
                1,
            )
            * 100
        )
        if chemistry_share >= 10:
            item = ACTION_LIBRARY["Chemistry / raw material"]
            recommendations.append(
                {
                    "Priority": len(recommendations) + 1,
                    "RootCauseGroup": "Chemistry / raw material",
                    "ContributionPct": chemistry_share,
                    "Recommendation": item["title"],
                    "Actions": item["actions"],
                    "Verification": item["verification"],
                }
            )

    if not transitions.empty:
        context_share = transitions["EventContext"].value_counts(normalize=True)
        startup_share = float(
            context_share.get("Startup", 0)
            + context_share.get("Shutdown / stoppage", 0)
        ) * 100
        manual_share = float(
            context_share.get("Manual grade", 0)
            + context_share.get("Contaminated coil", 0)
        ) * 100

        if startup_share >= 5:
            item = ACTION_LIBRARY["Startup / shutdown"]
            recommendations.append(
                {
                    "Priority": len(recommendations) + 1,
                    "RootCauseGroup": "Startup / shutdown",
                    "ContributionPct": startup_share,
                    "Recommendation": item["title"],
                    "Actions": item["actions"],
                    "Verification": item["verification"],
                }
            )
        if manual_share >= 5:
            item = ACTION_LIBRARY["Manual / contamination"]
            recommendations.append(
                {
                    "Priority": len(recommendations) + 1,
                    "RootCauseGroup": "Manual / contamination",
                    "ContributionPct": manual_share,
                    "Recommendation": item["title"],
                    "Actions": item["actions"],
                    "Verification": item["verification"],
                }
            )

    if not data_quality.empty:
        poor = data_quality.loc[
            data_quality["FrozenChannel"]
            | data_quality["MissingFraction"].gt(0.25)
        ]
        if not poor.empty:
            item = ACTION_LIBRARY["Data quality"]
            recommendations.append(
                {
                    "Priority": len(recommendations) + 1,
                    "RootCauseGroup": "Data quality",
                    "ContributionPct": np.nan,
                    "Recommendation": item["title"],
                    "Actions": item["actions"],
                    "Verification": item["verification"],
                }
            )
    return recommendations


def run_analysis(
    coils: pd.DataFrame,
    process: pd.DataFrame,
    product_summary: pd.DataFrame,
    parameter_detail: pd.DataFrame,
    product_trigger_builder,
    settings: AnalysisSettings,
) -> dict:
    coils = coils.merge(product_summary, on="CoilKey", how="left")
    coils, transitions = detect_transitions(coils)
    product_triggers = product_trigger_builder(
        transitions,
        parameter_detail,
    )

    parameters = select_important_process_columns(process)
    process = clean_process_values(process, parameters)
    quality = process_data_quality(process, parameters)
    mapped = map_process_to_coils(
        process,
        coils,
        parameters,
        lag_minutes=settings.process_lag_minutes,
    )
    means, counts, process_features = aggregate_process_features(
        mapped, parameters
    )
    candidates = rank_process_candidates(
        coils,
        transitions,
        means,
        counts,
        quality,
        product_triggers,
        settings,
    )
    group_contributions, parameter_contributions = (
        root_cause_contributions(transitions, candidates)
    )
    recommendations = build_recommendations(
        group_contributions,
        product_triggers,
        quality,
        transitions,
    )

    return {
        "coils": coils,
        "transitions": transitions,
        "product_parameters": parameter_detail,
        "product_triggers": product_triggers,
        "process_mapped": mapped,
        "process_features": process_features,
        "process_means": means,
        "root_cause_candidates": candidates,
        "root_cause_groups": group_contributions,
        "root_cause_parameters": parameter_contributions,
        "data_quality": quality,
        "recommendations": recommendations,
        "event_context_summary": (
            transitions["EventContext"]
            .value_counts()
            .rename_axis("EventContext")
            .reset_index(name="Events")
        ),
        "important_process_parameters": parameters,
    }
