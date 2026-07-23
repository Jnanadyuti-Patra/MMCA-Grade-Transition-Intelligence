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


def test_product_loader_auto_detects_master_header(tmp_path):
    from mmca.io import load_product_workbook

    workbook = tmp_path / "product.xlsx"
    frame = pd.DataFrame(
        {
            "Coil ID": ["A001", "A002"],
            "Date": [pd.Timestamp("2024-01-03")] * 2,
            "Start Time": ["09:00:00", "09:10:00"],
            "Finish Time": ["09:09:30", "09:19:30"],
            "Grade": [4, 5],
            "Net": [4000, 4100],
        }
    )
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Master", index=False)

    loaded = load_product_workbook(workbook)

    assert len(loaded) == 2
    assert loaded.attrs["source_sheet"] == "Master"
    assert loaded.attrs["header_row"] == 1
    assert loaded.loc[0, "CoilID"] == "A001"
    assert loaded.loc[1, "Grade"] == 5
    assert round(loaded.loc[0, "WeightMT"], 3) == 4.0


def test_product_loader_accepts_master_simplified_variants(tmp_path):
    from mmca.io import load_product_workbook

    workbook = tmp_path / "product_simplified.xlsx"
    frame = pd.DataFrame(
        {
            "Coil ID": ["A001"],
            "Date": [pd.Timestamp("2024-01-03")],
            "Start Time": ["09:00:00"],
            "Finish Time": ["09:09:30"],
            "Grade": [4],
            "15 X 15 Twist Test (Index)": [2],
            "25 RTF Twist Test (Number)": [29],
            "Oxide Content (Å)": [350],
        }
    )
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Master_Simplified", index=False)

    loaded = load_product_workbook(workbook)

    assert loaded.attrs["source_sheet"] == "Master_Simplified"
    assert "15/15 Twist Test" in loaded.columns
    assert "F/R 25 twist" in loaded.columns
    assert "Total Oxide" in loaded.columns
