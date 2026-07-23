from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mmca.analysis import AnalysisSettings, run_analysis
from mmca.finance import (
    FinancialAssumptions,
    calculate_financial_impact,
    fetch_market_history,
)
from mmca.grading import (
    evaluate_product_parameters,
    identify_product_triggers,
    load_grading_revisions,
)
from mmca.io import load_process_workbook, load_product_workbook
from mmca.reporting import generate_excel_report, generate_html_report


st.set_page_config(
    page_title="MMCA Grade Transition Intelligence",
    page_icon="🧭",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
    [data-testid="stMetric"] {
        border: 1px solid #dfe7ec;
        border-radius: 12px;
        padding: 12px;
        background: #f8fbfc;
    }
    .mmca-note {
        padding: 12px 14px;
        border-left: 5px solid #c88b00;
        background: #fff8dd;
        border-radius: 5px;
    }
    .mmca-good {
        padding: 12px 14px;
        border-left: 5px solid #178351;
        background: #edf9f3;
        border-radius: 5px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_product(file_bytes: bytes) -> pd.DataFrame:
    return load_product_workbook(file_bytes)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_process(file_bytes: bytes) -> pd.DataFrame:
    return load_process_workbook(file_bytes)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=4)
def cached_market_prices(start_date, end_date):
    return fetch_market_history(start_date, end_date)


def _money(value: float) -> str:
    return f"MYR {value:,.0f}"


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _filter_scope(
    coils: pd.DataFrame,
    process: pd.DataFrame,
    start_date,
    end_date,
    process_lag_minutes: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1)

    scoped_coils = coils.loc[
        coils["StartDateTime"].ge(start)
        & coils["StartDateTime"].lt(end)
    ].copy()

    if scoped_coils.empty:
        raise ValueError("No coils fall inside the selected date range.")

    process_start = (
        scoped_coils["StartDateTime"].min()
        - pd.Timedelta(minutes=process_lag_minutes + 60)
    )
    process_end = scoped_coils["FinishDateTime"].max() + pd.Timedelta(minutes=60)
    scoped_process = process.loc[
        process["ProcessTime"].between(process_start, process_end)
    ].copy()

    if scoped_process.empty:
        raise ValueError(
            "No process records overlap the selected coil-production range."
        )
    return scoped_coils.reset_index(drop=True), scoped_process.reset_index(drop=True)


def _prepare_analysis(
    product_file,
    process_file,
    scope_mode,
    selected_dates,
    baseline_coils,
    process_lag,
    minimum_score,
):
    product = cached_product(product_file.getvalue())
    process = cached_process(process_file.getvalue())

    if scope_mode == "All uploaded data":
        start_date = product["StartDateTime"].min().date()
        end_date = product["StartDateTime"].max().date()
    else:
        start_date, end_date = selected_dates

    scoped_coils, scoped_process = _filter_scope(
        product,
        process,
        start_date,
        end_date,
        process_lag,
    )

    revisions = load_grading_revisions(
        ROOT / "config" / "grading_rules.json"
    )
    product_summary, product_detail = evaluate_product_parameters(
        scoped_coils,
        revisions,
    )
    settings = AnalysisSettings(
        baseline_coils=baseline_coils,
        process_lag_minutes=process_lag,
        minimum_candidate_score=minimum_score,
    )
    analysis = run_analysis(
        scoped_coils,
        scoped_process,
        product_summary,
        product_detail,
        identify_product_triggers,
        settings,
    )
    analysis["scope"] = {
        "start_date": start_date,
        "end_date": end_date,
        "scope_mode": scope_mode,
        "process_lag_minutes": process_lag,
        "baseline_coils": baseline_coils,
        "minimum_candidate_score": minimum_score,
    }
    return analysis


def _plot_grade_timeline(coils: pd.DataFrame, transitions: pd.DataFrame):
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=coils["StartDateTime"],
            y=coils["Grade"],
            mode="lines",
            line={"width": 1.8},
            name="Recorded grade",
            hovertemplate=(
                "Coil %{customdata}<br>"
                "Time %{x|%Y-%m-%d %H:%M}<br>"
                "Grade %{y}<extra></extra>"
            ),
            customdata=coils["CoilID"],
        )
    )
    for transition_type, symbol in [("Downgrade", "triangle-down"), ("Upgrade", "triangle-up")]:
        subset = transitions.loc[
            transitions["TransitionType"].eq(transition_type)
        ]
        figure.add_trace(
            go.Scatter(
                x=subset["StartDateTime"],
                y=subset["Grade"],
                mode="markers",
                marker={"size": 9, "symbol": symbol},
                name=transition_type,
                customdata=np.stack(
                    [
                        subset["TransitionID"],
                        subset["GradePair"],
                        subset["CoilID"],
                    ],
                    axis=-1,
                ) if len(subset) else None,
                hovertemplate=(
                    "%{customdata[0]}<br>"
                    "%{customdata[1]}<br>"
                    "Coil %{customdata[2]}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        height=430,
        template="plotly_white",
        xaxis_title="Production time",
        yaxis_title="Metrod grade",
        yaxis={"dtick": 1, "range": [-0.3, 7.3]},
        legend={"orientation": "h"},
        margin={"l": 35, "r": 20, "t": 30, "b": 35},
    )
    return figure


def _show_recommendations(recommendations):
    if not recommendations:
        st.info("No recommendation could be generated from the selected range.")
        return
    for item in recommendations:
        contribution = (
            ""
            if pd.isna(item["ContributionPct"])
            else f" · estimated contribution {_pct(item['ContributionPct'])}"
        )
        with st.expander(
            f"Priority {item['Priority']}: {item['Recommendation']}{contribution}",
            expanded=item["Priority"] <= 2,
        ):
            for action in item["Actions"]:
                st.markdown(f"- {action}")
            st.markdown(f"**Verify by:** {item['Verification']}")


st.title("🧭 MMCA Grade Transition Intelligence")
st.caption(
    "Upload the monthly product and process workbooks, choose a date range, "
    "detect every sudden grade change, and generate an explainable QC report."
)

with st.sidebar:
    st.header("1. Upload company files")
    product_file = st.file_uploader(
        "Product data workbook",
        type=["xlsx"],
        help=(
            "Upload the CCR Coil Inspection Details workbook. The app "
            "automatically detects Master or Master_Simplified and the "
            "correct header row."
        ),
    )
    process_file = st.file_uploader(
        "Process data workbook",
        type=["xlsx"],
        help="Expected workbook: Process_Values with one-minute process records.",
    )

    product_preview = None
    if product_file is not None:
        try:
            product_preview = cached_product(product_file.getvalue())
            source_sheet = product_preview.attrs.get("source_sheet", "detected sheet")
            header_row = product_preview.attrs.get("header_row", "?")
            st.success(
                f"Product file validated: {len(product_preview):,} coils "
                f"from {source_sheet} (header row {header_row})"
            )
        except Exception as error:
            st.error(f"Product file error: {error}")

    st.header("2. Analysis scope")
    scope_mode = st.radio(
        "Choose scope",
        ["All uploaded data", "Select date range"],
    )

    date_value = None
    if product_preview is not None:
        minimum_date = product_preview["StartDateTime"].min().date()
        maximum_date = product_preview["StartDateTime"].max().date()
        if scope_mode == "Select date range":
            date_value = st.date_input(
                "Production dates",
                value=(minimum_date, maximum_date),
                min_value=minimum_date,
                max_value=maximum_date,
            )
        else:
            date_value = (minimum_date, maximum_date)
            st.caption(f"{minimum_date} to {maximum_date}")

    with st.expander("Advanced analysis settings"):
        baseline_coils = st.slider(
            "Stable coils used as local baseline",
            min_value=3,
            max_value=12,
            value=5,
        )
        process_lag = st.number_input(
            "Process-to-coil lag (minutes)",
            min_value=0.0,
            max_value=120.0,
            value=0.0,
            step=1.0,
            help=(
                "Shift the process influence window earlier when upstream "
                "material residence time is known."
            ),
        )
        minimum_score = st.slider(
            "Minimum root-cause candidate score",
            min_value=0,
            max_value=70,
            value=25,
        )

    analyse_button = st.button(
        "Run grade-change analysis",
        type="primary",
        use_container_width=True,
        disabled=(
            product_file is None
            or process_file is None
            or product_preview is None
            or not isinstance(date_value, tuple)
            or len(date_value) != 2
        ),
    )

if analyse_button:
    with st.spinner(
        "Loading the process workbook and analysing grade transitions..."
    ):
        try:
            st.session_state.analysis = _prepare_analysis(
                product_file,
                process_file,
                scope_mode,
                date_value,
                baseline_coils,
                process_lag,
                minimum_score,
            )
            st.session_state.pop("financial_events", None)
            st.session_state.pop("financial_summary", None)
        except Exception as error:
            st.exception(error)

analysis = st.session_state.get("analysis")

if analysis is None:
    st.markdown(
        """
        <div class="mmca-note">
        <strong>How to begin:</strong> upload the two company workbooks in the
        sidebar, select all data or a date range, and click
        <em>Run grade-change analysis</em>. No company workbook is included in
        the source repository.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

coils = analysis["coils"]
transitions = analysis["transitions"]
downgrades = transitions.loc[
    transitions["TransitionType"].eq("Downgrade")
]
upgrades = transitions.loc[
    transitions["TransitionType"].eq("Upgrade")
]
single_coil = transitions.loc[transitions["TransientOneCoil"]]

scope = analysis["scope"]
scope_label = (
    f"{scope['start_date']} to {scope['end_date']} "
    f"({scope['scope_mode'].lower()})"
)
st.markdown(
    f"""
    <div class="mmca-good">
    <strong>Analysis complete:</strong> {len(coils):,} coils and
    {len(transitions):,} grade transitions analysed for {scope_label}.
    </div>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs(
    [
        "Overview",
        "Transition investigator",
        "Root causes and actions",
        "Financial impact",
        "Download report",
    ]
)

with tabs[0]:
    metrics = st.columns(6)
    metrics[0].metric("Coils analysed", f"{len(coils):,}")
    metrics[1].metric("Grade transitions", f"{len(transitions):,}")
    metrics[2].metric(
        "Downgrades",
        f"{len(downgrades):,}",
        f"{len(downgrades) / max(len(transitions), 1) * 100:.1f}%",
    )
    metrics[3].metric("Upgrades", f"{len(upgrades):,}")
    metrics[4].metric(
        "One-coil fluctuations",
        f"{len(single_coil):,}",
        f"{len(single_coil) / max(len(transitions), 1) * 100:.1f}%",
    )
    metrics[5].metric(
        "Downgrade-affected weight",
        f"{downgrades['AffectedWeightMT'].sum():,.1f} MT",
    )

    st.plotly_chart(
        _plot_grade_timeline(coils, transitions),
        use_container_width=True,
    )

    left, right = st.columns(2)
    with left:
        grade_counts = (
            coils["Grade"].value_counts().sort_index().rename_axis("Grade").reset_index(name="Coils")
        )
        grade_figure = px.bar(
            grade_counts,
            x="Grade",
            y="Coils",
            title="Coil distribution by grade",
            text_auto=True,
        )
        grade_figure.update_layout(template="plotly_white", height=380)
        st.plotly_chart(grade_figure, use_container_width=True)

    with right:
        pair_counts = (
            transitions["GradePair"]
            .value_counts()
            .head(12)
            .rename_axis("Grade pair")
            .reset_index(name="Events")
        )
        pair_figure = px.bar(
            pair_counts,
            x="Events",
            y="Grade pair",
            orientation="h",
            title="Most frequent grade transitions",
            text_auto=True,
        )
        pair_figure.update_layout(
            template="plotly_white",
            height=380,
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(pair_figure, use_container_width=True)

    st.subheader("Transition register")
    table_columns = [
        "TransitionID",
        "StartDateTime",
        "PreviousCoilID",
        "CoilID",
        "GradePair",
        "TransitionType",
        "PersistenceCoils",
        "AffectedWeightMT",
        "EventContext",
    ]
    st.dataframe(
        transitions[table_columns],
        use_container_width=True,
        hide_index=True,
    )

with tabs[1]:
    if transitions.empty:
        st.info("No grade transition exists in the selected range.")
    else:
        event_options = {
            (
                f"{row.TransitionID} · {row.GradePair} · "
                f"{row.CoilID} · {row.StartDateTime:%Y-%m-%d %H:%M}"
            ): row.TransitionID
            for row in transitions.itertuples(index=False)
        }
        selected_label = st.selectbox(
            "Select a grade-change event",
            options=list(event_options),
        )
        selected_id = event_options[selected_label]
        event = transitions.loc[
            transitions["TransitionID"].eq(selected_id)
        ].iloc[0]

        event_metrics = st.columns(6)
        event_metrics[0].metric("Transition", event["GradePair"])
        event_metrics[1].metric("Type", event["TransitionType"])
        event_metrics[2].metric("Previous coil", event["PreviousCoilID"])
        event_metrics[3].metric("Current coil", event["CoilID"])
        event_metrics[4].metric(
            "Persistence", f"{int(event['PersistenceCoils'])} coils"
        )
        event_metrics[5].metric(
            "Affected weight", f"{event['AffectedWeightMT']:.2f} MT"
        )

        if event["EventContext"] != "Normal production":
            st.warning(
                f"Context flag: {event['EventContext']}. "
                "Interpret this event separately from a normal quality transition."
            )

        trigger_table = analysis["product_triggers"].loc[
            analysis["product_triggers"]["TransitionID"].eq(selected_id)
        ].sort_values("TriggerRank")
        candidate_table = analysis["root_cause_candidates"].loc[
            analysis["root_cause_candidates"]["TransitionID"].eq(selected_id)
        ].sort_values("CandidateRank")

        left, right = st.columns(2)
        with left:
            st.subheader("Product grading triggers")
            if trigger_table.empty:
                st.info(
                    "No deterministic product trigger was isolated from the "
                    "available graded parameters."
                )
            else:
                st.dataframe(
                    trigger_table[
                        [
                            "TriggerRank",
                            "Parameter",
                            "ParameterGroup",
                            "PreviousValue",
                            "CurrentValue",
                            "PreviousParameterGrade",
                            "CurrentParameterGrade",
                            "TriggerScore",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        with right:
            st.subheader("Probable process drivers")
            if candidate_table.empty:
                st.info("Insufficient process evidence for this event.")
            else:
                st.dataframe(
                    candidate_table[
                        [
                            "CandidateRank",
                            "Parameter",
                            "ParameterGroup",
                            "CandidateScore",
                            "RobustZ",
                            "StepZ",
                            "ConfidenceBand",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        top_parameters = candidate_table["Parameter"].head(4).tolist()
        if top_parameters:
            st.subheader("Process traces around the event")
            event_time = pd.Timestamp(event["StartDateTime"])
            trace = analysis["process_mapped"].loc[
                analysis["process_mapped"]["ProcessTime"].between(
                    event_time - pd.Timedelta(minutes=45),
                    event_time + pd.Timedelta(minutes=45),
                ),
                ["ProcessTime", *top_parameters],
            ].melt(
                id_vars="ProcessTime",
                var_name="Parameter",
                value_name="Value",
            )
            trace_figure = px.line(
                trace,
                x="ProcessTime",
                y="Value",
                facet_row="Parameter",
                title="Top-ranked process parameters",
            )
            trace_figure.add_vline(x=event_time, line_dash="dash")
            trace_figure.update_yaxes(matches=None)
            trace_figure.update_layout(
                template="plotly_white",
                height=max(420, 190 * len(top_parameters)),
                showlegend=False,
            )
            st.plotly_chart(trace_figure, use_container_width=True)

with tabs[2]:
    left, right = st.columns(2)
    with left:
        st.subheader("Root-cause contribution by process group")
        groups = analysis["root_cause_groups"]
        if groups.empty:
            st.info("No root-cause contribution could be calculated.")
        else:
            fig = px.bar(
                groups,
                x="ContributionPct",
                y="ParameterGroup",
                orientation="h",
                text="ContributionPct",
            )
            fig.update_traces(texttemplate="%{text:.1f}%")
            fig.update_layout(
                template="plotly_white",
                height=380,
                yaxis={"categoryorder": "total ascending"},
                xaxis_title="Estimated contribution (%)",
            )
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Leading individual parameters")
        parameters = analysis["root_cause_parameters"].head(12)
        if not parameters.empty:
            fig = px.bar(
                parameters,
                x="ContributionPct",
                y="Parameter",
                color="ParameterGroup",
                orientation="h",
                text="ContributionPct",
            )
            fig.update_traces(texttemplate="%{text:.1f}%")
            fig.update_layout(
                template="plotly_white",
                height=380,
                yaxis={"categoryorder": "total ascending"},
                xaxis_title="Estimated contribution (%)",
            )
            st.plotly_chart(fig, use_container_width=True)

    context_summary = analysis["event_context_summary"]
    if not context_summary.empty:
        st.subheader("Operational context of grade transitions")
        context_figure = px.bar(
            context_summary,
            x="Events",
            y="EventContext",
            orientation="h",
            text="Events",
        )
        context_figure.update_layout(
            template="plotly_white",
            height=300,
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(context_figure, use_container_width=True)

    st.subheader("Recommended QC and process actions")
    _show_recommendations(analysis["recommendations"])

    with st.expander("Parameters included in the process analysis"):
        st.write(
            ", ".join(analysis["important_process_parameters"])
        )
        st.caption(
            "The SCU colour-coded channels are excluded from causal ranking "
            "because their physical meaning was not documented in the supplied files."
        )

with tabs[3]:
    st.subheader("Scenario-based financial impact")
    st.markdown(
        """
        <div class="mmca-note">
        Actual grade-to-grade selling-price differences, rework costs and a
        structured planned-grade field were not present in the uploaded
        workbooks. The preceding stable grade is therefore used as the temporary
        commercial target for downgrades. The result is an editable opportunity-
        loss scenario, not an audited accounting loss.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("financial_form"):
        c1, c2 = st.columns(2)
        with c1:
            automatic_price = st.toggle(
                "Use historical daily COMEX HG benchmark",
                value=True,
                help=(
                    "The app attempts to retrieve the daily HG=F close and "
                    "converts USD/lb to USD/metric tonne. Manual values remain "
                    "available as a fallback."
                ),
            )
            manual_price = st.number_input(
                "Fallback copper price (USD/metric tonne)",
                min_value=1000.0,
                value=10000.0,
                step=100.0,
            )
            usd_myr = st.number_input(
                "Fallback USD/MYR exchange rate",
                min_value=1.0,
                value=4.50,
                step=0.01,
            )
            grade_discount = st.number_input(
                "Commercial penalty per grade step (%)",
                min_value=0.0,
                max_value=20.0,
                value=0.50,
                step=0.10,
            )
        with c2:
            remelt_loss = st.number_input(
                "Additional Grade 0 remelt/recovery loss (%)",
                min_value=0.0,
                max_value=30.0,
                value=3.0,
                step=0.5,
            )
            preventable_share = st.slider(
                "Share of estimated loss considered preventable (%)",
                0,
                100,
                50,
            )
            effectiveness = st.slider(
                "Expected intervention effectiveness (%)",
                0,
                100,
                60,
            )
            implementation_cost = st.number_input(
                "Implementation cost for selected period (MYR)",
                min_value=0.0,
                value=0.0,
                step=1000.0,
            )
        financial_button = st.form_submit_button(
            "Calculate financial impact",
            type="primary",
        )

    if financial_button:
        assumptions = FinancialAssumptions(
            price_mode="automatic" if automatic_price else "manual",
            manual_copper_price_usd_mt=manual_price,
            manual_usd_myr=usd_myr,
            grade_step_discount_pct=grade_discount,
            grade_zero_remelt_loss_pct=remelt_loss,
            preventable_share_pct=preventable_share,
            intervention_effectiveness_pct=effectiveness,
            implementation_cost_myr=implementation_cost,
        )

        copper_history = pd.Series(dtype=float)
        fx_history = pd.Series(dtype=float)
        market_note = "Manual copper-price and exchange-rate inputs were used."

        if automatic_price:
            try:
                with st.spinner("Retrieving historical daily copper and FX benchmarks..."):
                    copper_history, fx_history = cached_market_prices(
                        scope["start_date"],
                        scope["end_date"],
                    )
                market_note = (
                    "Daily COMEX HG benchmark and USD/MYR market data were "
                    "retrieved automatically; manual values were used for any gaps."
                )
            except Exception as error:
                st.warning(
                    "Automatic market-price retrieval failed. "
                    f"Manual fallback values were used. Details: {error}"
                )
                market_note = (
                    "Automatic retrieval failed; manual fallback values were used."
                )

        financial_events, financial_summary = calculate_financial_impact(
            transitions,
            assumptions,
            copper_history,
            fx_history,
        )
        st.session_state.financial_events = financial_events
        st.session_state.financial_summary = financial_summary
        st.session_state.financial_assumptions = assumptions.__dict__
        st.session_state.market_note = market_note

    financial_summary = st.session_state.get("financial_summary")
    financial_events = st.session_state.get("financial_events")

    if financial_summary:
        money_metrics = st.columns(6)
        money_metrics[0].metric(
            "Average copper benchmark",
            _money(financial_summary["AverageCopperPriceMYRMT"]) + "/MT",
        )
        money_metrics[1].metric(
            "Estimated total loss",
            _money(financial_summary["TotalEstimatedLossMYR"]),
        )
        money_metrics[2].metric(
            "Average loss per downgrade",
            _money(financial_summary["AverageLossPerDowngradeMYR"]),
        )
        money_metrics[3].metric(
            "Copper value exposed",
            _money(financial_summary["GrossCopperValueExposedMYR"]),
        )
        money_metrics[4].metric(
            "Potential savings",
            _money(financial_summary["PotentialSavingsMYR"]),
        )
        money_metrics[5].metric(
            "Potential net revenue protected",
            _money(
                financial_summary[
                    "PotentialNetRevenueProtectedMYR"
                ]
            ),
        )

        top_loss = financial_events.sort_values(
            "EstimatedLossMYR", ascending=False
        ).head(20)
        loss_figure = px.bar(
            top_loss,
            x="TransitionID",
            y="EstimatedLossMYR",
            color="GradePair",
            title="Highest estimated loss events",
            hover_data=[
                "StartDateTime",
                "AffectedWeightMT",
                "CopperPriceMYRMT",
            ],
        )
        loss_figure.update_layout(
            template="plotly_white",
            yaxis_title="Estimated loss (MYR)",
        )
        st.plotly_chart(loss_figure, use_container_width=True)

with tabs[4]:
    financial_events = st.session_state.get("financial_events")
    financial_summary = st.session_state.get("financial_summary")
    assumptions = st.session_state.get("financial_assumptions")
    market_note = st.session_state.get(
        "market_note",
        "Financial impact has not yet been calculated.",
    )

    if financial_summary is None:
        st.info(
            "Open the Financial impact tab and calculate the commercial "
            "scenario before downloading the complete report."
        )
    else:
        html_report = generate_html_report(
            analysis=analysis,
            financial_events=financial_events,
            financial_summary=financial_summary,
            scope_label=scope_label,
            market_source_note=market_note,
        )
        excel_report = generate_excel_report(
            analysis=analysis,
            financial_events=financial_events,
            financial_summary=financial_summary,
            assumptions=assumptions,
        )

        st.download_button(
            "Download detailed HTML report",
            data=html_report,
            file_name="MMCA_grade_transition_report.html",
            mime="text/html",
            use_container_width=True,
        )
        st.download_button(
            "Download detailed Excel report",
            data=excel_report,
            file_name="MMCA_grade_transition_report.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

        with st.expander("Report methodology and limitations", expanded=True):
            st.markdown(
                """
                - Product triggers are calculated from the applicable Revision
                  19 or Revision 20 grading criteria.
                - Process candidates are ranked using local robust deviation,
                  change from the preceding coil, data completeness and
                  product-process relevance.
                - Contribution percentages are normalised statistical
                  attribution weights, not proven causal shares.
                - The monetary result is scenario-based and must be replaced
                  with company-approved grade realisation, rework and remelt
                  assumptions for accounting use.
                - Potential net revenue protected is prospective. It is not
                  revenue already realised.
                """
            )
