import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mmca.analysis import detect_transitions
from mmca.finance import FinancialAssumptions, calculate_financial_impact


def test_detects_adjacent_grade_changes_and_run_weight():
    coils = pd.DataFrame(
        {
            "CoilKey": [1, 2, 3, 4, 5],
            "CoilID": ["A", "B", "C", "D", "E"],
            "Grade": [6, 6, 5, 5, 6],
            "StartDateTime": pd.date_range("2024-01-01", periods=5, freq="10min"),
            "FinishDateTime": pd.date_range(
                "2024-01-01 00:09", periods=5, freq="10min"
            ),
            "WeightMT": [4.0, 4.0, 4.2, 4.1, 4.0],
            "EventContext": ["Normal production"] * 5,
            "CombinedRemarks": [""] * 5,
        }
    )

    enriched, transitions = detect_transitions(coils)

    assert len(transitions) == 2
    assert transitions.iloc[0]["GradePair"] == "6 → 5"
    assert transitions.iloc[0]["PersistenceCoils"] == 2
    assert round(transitions.iloc[0]["AffectedWeightMT"], 1) == 8.3
    assert transitions.iloc[1]["TransitionType"] == "Upgrade"


def test_financial_model_only_charges_downgrades():
    transitions = pd.DataFrame(
        {
            "TransitionID": ["T1", "T2"],
            "StartDateTime": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "TransitionType": ["Downgrade", "Upgrade"],
            "PreviousGrade": [6, 5],
            "Grade": [5, 6],
            "AffectedWeightMT": [10.0, 10.0],
        }
    )
    assumptions = FinancialAssumptions(
        price_mode="manual",
        manual_copper_price_usd_mt=10000,
        manual_usd_myr=4,
        grade_step_discount_pct=1,
        grade_zero_remelt_loss_pct=3,
        preventable_share_pct=50,
        intervention_effectiveness_pct=50,
        implementation_cost_myr=0,
    )

    events, summary = calculate_financial_impact(
        transitions,
        assumptions,
    )

    assert events.loc[0, "EstimatedLossMYR"] == 4000
    assert events.loc[1, "EstimatedLossMYR"] == 0
    assert summary["PotentialSavingsMYR"] == 1000
