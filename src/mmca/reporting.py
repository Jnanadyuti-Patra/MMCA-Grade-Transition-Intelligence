from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Iterable

import pandas as pd


def _money(value: float) -> str:
    return f"MYR {value:,.2f}"


def _table_html(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    max_rows: int = 20,
) -> str:
    if frame.empty:
        return "<p>No records available.</p>"

    columns = [column for column in columns if column in frame.columns]
    view = frame[columns].head(max_rows).copy()
    return view.to_html(
        index=False,
        border=0,
        classes="report-table",
        escape=True,
    )


def generate_html_report(
    *,
    analysis: dict,
    financial_events: pd.DataFrame,
    financial_summary: dict,
    scope_label: str,
    market_source_note: str,
) -> bytes:
    transitions = analysis["transitions"]
    triggers = analysis["product_triggers"]
    root_groups = analysis["root_cause_groups"]
    root_parameters = analysis["root_cause_parameters"]
    recommendations = analysis["recommendations"]
    data_quality = analysis["data_quality"]

    downgrades = int(
        transitions["TransitionType"].eq("Downgrade").sum()
    )
    upgrades = int(
        transitions["TransitionType"].eq("Upgrade").sum()
    )
    one_coil = int(transitions["TransientOneCoil"].sum())

    recommendation_html = "".join(
        f"""
        <section class="recommendation">
          <h3>{item['Priority']}. {escape(item['Recommendation'])}</h3>
          <p><strong>Estimated contribution:</strong>
          {'' if pd.isna(item['ContributionPct']) else f"{item['ContributionPct']:.1f}%"}</p>
          <ul>
            {''.join(f"<li>{escape(action)}</li>" for action in item['Actions'])}
          </ul>
          <p><strong>Verification:</strong> {escape(item['Verification'])}</p>
        </section>
        """
        for item in recommendations
    ) or "<p>No recommendation could be generated from the available data.</p>"

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MMCA Grade Transition Analysis Report</title>
<style>
body {{
  font-family: Arial, sans-serif;
  max-width: 1100px;
  margin: 32px auto;
  padding: 0 24px;
  line-height: 1.5;
  color: #1f2933;
}}
h1, h2, h3 {{ color: #12344d; }}
.subtitle {{ color: #52616b; }}
.kpis {{
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 12px;
  margin: 20px 0;
}}
.kpi {{
  border: 1px solid #d8e0e5;
  border-radius: 10px;
  padding: 14px;
  background: #f8fafb;
}}
.kpi strong {{ display: block; font-size: 24px; margin-top: 5px; }}
.report-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin: 12px 0 24px;
}}
.report-table th, .report-table td {{
  border: 1px solid #d8e0e5;
  padding: 7px;
  text-align: left;
}}
.report-table th {{ background: #eaf2f7; }}
.note {{
  background: #fff8df;
  border-left: 5px solid #d49b00;
  padding: 12px 16px;
}}
.recommendation {{
  border: 1px solid #d8e0e5;
  border-radius: 10px;
  padding: 14px 18px;
  margin: 12px 0;
}}
footer {{ margin-top: 36px; color: #66717d; font-size: 12px; }}
@media print {{
  body {{ margin: 0; max-width: none; }}
  .recommendation {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<h1>MMCA Grade Transition Analysis Report</h1>
<p class="subtitle">{escape(scope_label)}</p>

<div class="kpis">
  <div class="kpi">Coils analysed<strong>{len(analysis['coils']):,}</strong></div>
  <div class="kpi">Grade transitions<strong>{len(transitions):,}</strong></div>
  <div class="kpi">Downgrades<strong>{downgrades:,}</strong></div>
  <div class="kpi">Upgrades<strong>{upgrades:,}</strong></div>
  <div class="kpi">One-coil fluctuations<strong>{one_coil:,}</strong></div>
  <div class="kpi">Estimated loss<strong>{_money(financial_summary['TotalEstimatedLossMYR'])}</strong></div>
  <div class="kpi">Average loss / downgrade<strong>{_money(financial_summary['AverageLossPerDowngradeMYR'])}</strong></div>
  <div class="kpi">Potential savings<strong>{_money(financial_summary['PotentialSavingsMYR'])}</strong></div>
  <div class="kpi">Net revenue protected<strong>{_money(financial_summary['PotentialNetRevenueProtectedMYR'])}</strong></div>
</div>

<div class="note">
<strong>Financial interpretation:</strong> Loss and savings figures are scenario
estimates based on the selected copper benchmark, grade-step commercial penalty,
remelt loss, preventable share and intervention effectiveness. They are not
audited accounting figures. The preceding stable grade is used as the temporary commercial target. {escape(market_source_note)}
</div>

<h2>Executive findings</h2>
<p>
The analysis identified {len(transitions):,} sudden changes between consecutive
coils. Downgrades represented {downgrades / max(len(transitions), 1) * 100:.1f}%
of all transitions. One-coil fluctuations represented
{one_coil / max(len(transitions), 1) * 100:.1f}% of transitions and should be
reviewed separately from sustained process shifts.
</p>

<h2>Operational context of grade transitions</h2>
{_table_html(
    analysis['event_context_summary'],
    ['EventContext', 'Events'],
    max_rows=10,
)}

<h2>Root-cause contribution by process group</h2>
{_table_html(root_groups, ['ParameterGroup', 'ContributionPct'], max_rows=10)}

<h2>Leading process parameters</h2>
{_table_html(root_parameters, ['ParameterGroup', 'Parameter', 'ContributionPct'], max_rows=15)}

<h2>Leading product grading triggers</h2>
{_table_html(
    triggers.loc[triggers['TriggerRank'].le(3)] if not triggers.empty else triggers,
    [
        'TransitionID', 'Parameter', 'ParameterGroup', 'PreviousValue',
        'CurrentValue', 'PreviousParameterGrade', 'CurrentParameterGrade',
        'TriggerScore'
    ],
    max_rows=30,
)}

<h2>Actionable recommendations</h2>
{recommendation_html}

<h2>Highest estimated financial-loss events</h2>
{_table_html(
    financial_events.sort_values('EstimatedLossMYR', ascending=False),
    [
        'TransitionID', 'StartDateTime', 'GradePair', 'AffectedWeightMT',
        'CopperPriceMYRMT', 'EstimatedLossMYR', 'PotentialSavingsMYR'
    ],
    max_rows=25,
)}

<h2>Transition register</h2>
{_table_html(
    transitions,
    [
        'TransitionID', 'StartDateTime', 'PreviousCoilID', 'CoilID',
        'GradePair', 'TransitionType', 'PersistenceCoils',
        'AffectedWeightMT', 'EventContext'
    ],
    max_rows=50,
)}

<h2>Data-quality observations</h2>
{_table_html(
    data_quality.sort_values(['FrozenChannel', 'MissingFraction'], ascending=[False, False]),
    [
        'Parameter', 'ParameterGroup', 'MissingFraction', 'UniqueValues',
        'FrozenChannel', 'Minimum', 'Maximum'
    ],
    max_rows=30,
)}

<h2>Method limitations</h2>
<ul>
  <li>Process-driver scores indicate statistical association, temporal proximity and engineering relevance. They do not prove causation.</li>
  <li>Raw-material causation cannot be confirmed without timestamped cathode and scrap charge records.</li>
  <li>Financial estimates require company-approved commercial penalties and implementation-cost assumptions.</li>
  <li>Manual grades, contaminated coils, startup and stoppage events are flagged and should be interpreted separately.</li>
</ul>

<footer>
Generated by MMCA Grade Transition Intelligence. The report should be reviewed
by Quality Control, Production and Process Engineering before operational use.
</footer>
</body>
</html>"""
    return html.encode("utf-8")


def generate_excel_report(
    *,
    analysis: dict,
    financial_events: pd.DataFrame,
    financial_summary: dict,
    assumptions: dict,
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        workbook = writer.book
        header = workbook.add_format(
            {
                "bold": True,
                "font_color": "white",
                "bg_color": "#12344D",
                "border": 1,
            }
        )
        money = workbook.add_format({"num_format": 'MYR #,##0.00'})
        percent = workbook.add_format({"num_format": "0.0%"})
        date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})

        summary_rows = [
            ["Metric", "Value"],
            ["Coils analysed", len(analysis["coils"])],
            ["Grade transitions", len(analysis["transitions"])],
            [
                "Downgrades",
                int(
                    analysis["transitions"]["TransitionType"]
                    .eq("Downgrade")
                    .sum()
                ),
            ],
            [
                "Upgrades",
                int(
                    analysis["transitions"]["TransitionType"]
                    .eq("Upgrade")
                    .sum()
                ),
            ],
            [
                "One-coil fluctuations",
                int(analysis["transitions"]["TransientOneCoil"].sum()),
            ],
            [
                "Total estimated loss (MYR)",
                financial_summary["TotalEstimatedLossMYR"],
            ],
            [
                "Average loss per downgrade (MYR)",
                financial_summary["AverageLossPerDowngradeMYR"],
            ],
            [
                "Gross copper value exposed (MYR)",
                financial_summary["GrossCopperValueExposedMYR"],
            ],
            [
                "Potential savings (MYR)",
                financial_summary["PotentialSavingsMYR"],
            ],
            [
                "Potential net revenue protected (MYR)",
                financial_summary["PotentialNetRevenueProtectedMYR"],
            ],
        ]
        pd.DataFrame(summary_rows[1:], columns=summary_rows[0]).to_excel(
            writer, sheet_name="Executive Summary", index=False
        )

        sheets = {
            "Transitions": analysis["transitions"],
            "Product Triggers": analysis["product_triggers"],
            "Root Cause Candidates": analysis["root_cause_candidates"],
            "Root Cause Groups": analysis["root_cause_groups"],
            "Root Cause Parameters": analysis["root_cause_parameters"],
            "Financial Events": financial_events,
            "Data Quality": analysis["data_quality"],
        }
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)

        recommendations = []
        for item in analysis["recommendations"]:
            recommendations.append(
                {
                    "Priority": item["Priority"],
                    "RootCauseGroup": item["RootCauseGroup"],
                    "ContributionPct": item["ContributionPct"],
                    "Recommendation": item["Recommendation"],
                    "Actions": " | ".join(item["Actions"]),
                    "Verification": item["Verification"],
                }
            )
        pd.DataFrame(recommendations).to_excel(
            writer, sheet_name="Recommendations", index=False
        )
        pd.DataFrame(
            [{"Assumption": key, "Value": value} for key, value in assumptions.items()]
        ).to_excel(writer, sheet_name="Financial Assumptions", index=False)

        for sheet_name, worksheet in writer.sheets.items():
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, 0, max(0, worksheet.dim_colmax))
            worksheet.set_row(0, 22, header)
            worksheet.set_column(0, min(worksheet.dim_colmax, 20), 18)
            if sheet_name in {"Transitions", "Financial Events"}:
                worksheet.set_column(0, min(worksheet.dim_colmax, 20), 19)

    return buffer.getvalue()
