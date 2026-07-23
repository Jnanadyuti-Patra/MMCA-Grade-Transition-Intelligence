from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .constants import POUNDS_PER_METRIC_TONNE


@dataclass(frozen=True)
class FinancialAssumptions:
    price_mode: str = "automatic"
    manual_copper_price_usd_mt: float = 10000.0
    manual_usd_myr: float = 4.50
    grade_step_discount_pct: float = 0.50
    grade_zero_remelt_loss_pct: float = 3.00
    preventable_share_pct: float = 50.0
    intervention_effectiveness_pct: float = 60.0
    implementation_cost_myr: float = 0.0


def _single_close(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)

    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def fetch_market_history(
    start_date,
    end_date,
) -> tuple[pd.Series, pd.Series]:
    import yfinance as yf

    start = pd.Timestamp(start_date) - pd.Timedelta(days=10)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=3)

    copper = yf.download(
        "HG=F",
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    fx = yf.download(
        "MYR=X",
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        threads=False,
    )

    copper_usd_lb = _single_close(copper)
    usd_myr = _single_close(fx)

    copper_usd_mt = copper_usd_lb * POUNDS_PER_METRIC_TONNE
    copper_usd_mt.name = "CopperPriceUSDMT"
    usd_myr.name = "USDMYR"
    return copper_usd_mt, usd_myr


def _daily_lookup(
    dates: pd.Series,
    price: pd.Series,
    fallback: float,
) -> pd.Series:
    if price.empty:
        return pd.Series(fallback, index=dates.index, dtype=float)

    calendar = pd.date_range(
        min(price.index.min(), pd.Timestamp(dates.min())),
        max(price.index.max(), pd.Timestamp(dates.max())),
        freq="D",
    )
    daily = price.reindex(calendar).ffill().bfill()
    normalised = pd.to_datetime(dates).dt.normalize()
    return normalised.map(daily).fillna(fallback).astype(float)


def calculate_financial_impact(
    transitions: pd.DataFrame,
    assumptions: FinancialAssumptions,
    copper_history_usd_mt: pd.Series | None = None,
    usd_myr_history: pd.Series | None = None,
) -> tuple[pd.DataFrame, dict]:
    events = transitions.copy()
    events["EventDate"] = pd.to_datetime(
        events["StartDateTime"]
    ).dt.normalize()

    manual_price = assumptions.manual_copper_price_usd_mt
    manual_fx = assumptions.manual_usd_myr

    if (
        assumptions.price_mode == "automatic"
        and copper_history_usd_mt is not None
    ):
        events["CopperPriceUSDMT"] = _daily_lookup(
            events["EventDate"],
            copper_history_usd_mt,
            manual_price,
        )
    else:
        events["CopperPriceUSDMT"] = manual_price

    if (
        assumptions.price_mode == "automatic"
        and usd_myr_history is not None
    ):
        events["USDMYR"] = _daily_lookup(
            events["EventDate"],
            usd_myr_history,
            manual_fx,
        )
    else:
        events["USDMYR"] = manual_fx

    events["CopperPriceMYRMT"] = (
        events["CopperPriceUSDMT"] * events["USDMYR"]
    )
    events["GradeStepsLost"] = np.where(
        events["TransitionType"].eq("Downgrade"),
        (events["PreviousGrade"] - events["Grade"]).clip(lower=0),
        0,
    )
    events["GrossCopperValueMYR"] = (
        events["AffectedWeightMT"].fillna(0)
        * events["CopperPriceMYRMT"]
    )
    events["CommercialLossPct"] = (
        events["GradeStepsLost"]
        * assumptions.grade_step_discount_pct
    )
    events["RemeltLossPct"] = np.where(
        events["Grade"].eq(0)
        & events["TransitionType"].eq("Downgrade"),
        assumptions.grade_zero_remelt_loss_pct,
        0,
    )
    events["EstimatedLossMYR"] = (
        events["GrossCopperValueMYR"]
        * (
            events["CommercialLossPct"]
            + events["RemeltLossPct"]
        )
        / 100.0
    )
    events["EstimatedLossMYR"] = np.where(
        events["TransitionType"].eq("Downgrade"),
        events["EstimatedLossMYR"],
        0.0,
    )
    events["PotentialSavingsMYR"] = (
        events["EstimatedLossMYR"]
        * assumptions.preventable_share_pct
        / 100.0
        * assumptions.intervention_effectiveness_pct
        / 100.0
    )

    total_loss = float(events["EstimatedLossMYR"].sum())
    total_savings = float(events["PotentialSavingsMYR"].sum())
    net_revenue = total_savings - assumptions.implementation_cost_myr
    downgrade_count = int(events["TransitionType"].eq("Downgrade").sum())
    affected_weight = float(
        events.loc[
            events["TransitionType"].eq("Downgrade"),
            "AffectedWeightMT",
        ].sum()
    )

    summary = {
        "TotalEstimatedLossMYR": total_loss,
        "AverageLossPerDowngradeMYR": (
            total_loss / downgrade_count if downgrade_count else 0.0
        ),
        "DowngradeAffectedWeightMT": affected_weight,
        "GrossCopperValueExposedMYR": float(
            events.loc[
                events["TransitionType"].eq("Downgrade"),
                "GrossCopperValueMYR",
            ].sum()
        ),
        "PotentialSavingsMYR": total_savings,
        "ImplementationCostMYR": assumptions.implementation_cost_myr,
        "PotentialNetRevenueProtectedMYR": net_revenue,
        "PreventableSharePct": assumptions.preventable_share_pct,
        "InterventionEffectivenessPct": (
            assumptions.intervention_effectiveness_pct
        ),
        "GradeStepDiscountPct": assumptions.grade_step_discount_pct,
        "GradeZeroRemeltLossPct": (
            assumptions.grade_zero_remelt_loss_pct
        ),
        "AverageCopperPriceUSDMT": float(
            events["CopperPriceUSDMT"].mean()
        ) if not events.empty else assumptions.manual_copper_price_usd_mt,
        "AverageCopperPriceMYRMT": float(
            events["CopperPriceMYRMT"].mean()
        ) if not events.empty else (
            assumptions.manual_copper_price_usd_mt
            * assumptions.manual_usd_myr
        ),
    }
    return events, summary
