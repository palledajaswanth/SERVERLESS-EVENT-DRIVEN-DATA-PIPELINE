from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_access import (
    ANALYTICS_REJECTED_PATH,
    DB_PATH,
    ROOT,
    SCENARIO_NAMES,
    available_runs,
    latest_timestamp,
    load_analytics_summary,
    load_cloudwatch,
    load_cold_start,
    load_comparison,
    load_cost,
    load_events,
    load_negative_tests,
    load_pricing,
    load_rejected_events,
    load_saturation,
    load_summary,
    load_trace,
)

st.set_page_config(
    page_title="Serverless Pipeline Research Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- visual system ----------
st.markdown(
    """
<style>
:root {
  --bg: #06101d;
  --panel: #0b1727;
  --panel2: #0f2034;
  --stroke: rgba(148,163,184,.18);
  --muted: #91a4ba;
  --text: #e9f1fb;
  --blue: #38bdf8;
  --cyan: #22d3ee;
  --green: #34d399;
  --amber: #fbbf24;
  --red: #fb7185;
}
.stApp { background: radial-gradient(circle at 80% 0%, rgba(56,189,248,.09), transparent 30%), #06101d; }
.block-container { max-width: 1500px; padding-top: 1.7rem; padding-bottom: 3rem; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#071321 0%,#091827 100%); border-right: 1px solid var(--stroke); }
[data-testid="stSidebar"] * { color: #dce8f5; }
h1,h2,h3 { letter-spacing: -.02em; }
.hero {
  padding: 24px 26px; border: 1px solid rgba(56,189,248,.20); border-radius: 22px;
  background: linear-gradient(135deg, rgba(14,116,144,.20), rgba(15,32,52,.78) 45%, rgba(11,23,39,.96));
  box-shadow: 0 18px 50px rgba(0,0,0,.20); margin-bottom: 18px;
}
.hero-kicker { color: #67e8f9; font-size: .78rem; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }
.hero-title { color: #f6fbff; font-size: 2.05rem; line-height: 1.15; font-weight: 800; margin: 7px 0 7px; }
.hero-sub { color: #a9bdd0; font-size: .98rem; max-width: 980px; }
.run-chip { display:inline-block; margin-top:12px; padding:6px 11px; border-radius:999px; border:1px solid rgba(56,189,248,.26); background:rgba(56,189,248,.08); color:#bae6fd; font-size:.78rem; }
.section-kicker { color:#67e8f9; font-size:.74rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; margin-bottom:4px; }
.section-title { color:#f4f8fc; font-size:1.55rem; font-weight:800; margin-bottom:3px; }
.section-copy { color:#8fa5bb; margin-bottom:16px; }
[data-testid="stMetric"] { background: linear-gradient(180deg,rgba(15,32,52,.92),rgba(9,24,39,.92)); border:1px solid var(--stroke); border-radius:16px; padding:14px 15px; box-shadow:0 8px 24px rgba(0,0,0,.12); }
[data-testid="stMetricLabel"] { color:#9fb2c7; }
[data-testid="stMetricValue"] { color:#f5f9fd; }
div[data-testid="stDataFrame"] { border:1px solid var(--stroke); border-radius:14px; overflow:hidden; }
.panel { background:linear-gradient(180deg,rgba(15,32,52,.88),rgba(8,22,36,.90)); border:1px solid var(--stroke); border-radius:18px; padding:16px 18px; margin: 5px 0 13px; }
.flow { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; align-items:stretch; margin:10px 0 5px; }
.flow-node { min-height:78px; border:1px solid rgba(56,189,248,.18); border-radius:14px; padding:11px; background:rgba(10,30,47,.78); }
.flow-node b { color:#eaf6ff; display:block; font-size:.86rem; }
.flow-node span { color:#8098af; font-size:.73rem; }
.status-pass,.status-hold,.status-fail,.status-info { display:inline-block; padding:4px 9px; border-radius:999px; font-size:.72rem; font-weight:800; letter-spacing:.05em; }
.status-pass { color:#a7f3d0; background:rgba(52,211,153,.12); border:1px solid rgba(52,211,153,.25); }
.status-hold { color:#fde68a; background:rgba(251,191,36,.11); border:1px solid rgba(251,191,36,.24); }
.status-fail { color:#fecdd3; background:rgba(251,113,133,.11); border:1px solid rgba(251,113,133,.24); }
.status-info { color:#bae6fd; background:rgba(56,189,248,.11); border:1px solid rgba(56,189,248,.24); }
.small-note { color:#8197ad; font-size:.78rem; }
hr { border-color: rgba(148,163,184,.12) !important; }
@media (max-width: 1000px) { .flow { grid-template-columns:repeat(2,1fr); } .hero-title { font-size:1.65rem; } }
</style>
""",
    unsafe_allow_html=True,
)

PLOT_BG = "rgba(0,0,0,0)"
GRID = "rgba(148,163,184,.11)"
TEXT = "#9fb2c7"
BLUE = "#38bdf8"
CYAN = "#22d3ee"
GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#fb7185"
PURPLE = "#a78bfa"


def style_fig(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=55, b=18),
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=TEXT),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#102238", font_color="#eef7ff"),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID)
    return fig


def section(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f'<div class="section-kicker">{kicker}</div><div class="section-title">{title}</div><div class="section-copy">{copy}</div>',
        unsafe_allow_html=True,
    )


def pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}%"


def ms(value: float | None) -> str:
    return "—" if value is None else f"{value:,.1f} ms"


def eps(value: float | None) -> str:
    return "—" if value is None else f"{value:,.1f}/s"


def usd(value: float | None) -> str:
    if value is None:
        return "—"
    value = float(value)
    if abs(value) >= 1:
        return f"${value:,.4f}"
    if abs(value) >= 0.01:
        return f"${value:,.6f}"
    return f"${value:,.10f}"


def status_badge(status: str) -> str:
    s = (status or "UNKNOWN").upper()
    cls = "status-pass" if s == "PASS" else "status-hold" if s == "HOLD" else "status-fail" if s == "FAIL" else "status-info"
    return f'<span class="{cls}">{s}</span>'


def json_compact(value: Any, limit: int = 180) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str, separators=(",", ": "))
        except Exception:
            text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


@st.cache_data(ttl=20, show_spinner=False)
def cached_events() -> pd.DataFrame:
    return load_events()


# ---------- context / sidebar ----------
runs = available_runs()
selected_run = None

with st.sidebar:
    st.markdown("### ⚡ Serverless Lab")
    st.caption("AWS event-driven pipeline · research dashboard")
    st.markdown("---")
    if runs:
        selected_run = st.selectbox("Experiment run", runs, index=0, help="Metrics and evidence below are scoped to this run where applicable.")
    else:
        st.info("No experiment runs found yet.")
    page = st.radio(
        "Dashboard section",
        [
            "Overview",
            "Event Analytics",
            "Baseline vs AWS",
            "Cold Start Analysis",
            "Cost Analysis",
            "Negative Tests",
        ],
        index=0,
    )
    st.markdown("---")
    if DB_PATH.exists():
        db_time = datetime.fromtimestamp(DB_PATH.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        st.markdown(status_badge("READY") + "  **DuckDB analytics**", unsafe_allow_html=True)
        st.caption(f"Updated {db_time}")
    else:
        st.markdown(status_badge("MISSING") + "  **DuckDB analytics**", unsafe_allow_html=True)
    if selected_run:
        st.caption(f"Evidence: `evidence/runs/{selected_run}`")
    if st.button("↻ Refresh dashboard data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown(
    f"""
<div class="hero">
  <div class="hero-kicker">Cloud-native performance & reliability evidence</div>
  <div class="hero-title">Serverless Event-Driven Data Pipeline</div>
  <div class="hero-sub">One dashboard for stored-event analytics, always-on vs AWS performance, cold starts, normalized cost evidence, and the five mandatory recovery/security tests.</div>
  <div class="run-chip">Selected evidence run: {selected_run or 'No run selected'}</div>
</div>
""",
    unsafe_allow_html=True,
)

if not DB_PATH.exists():
    st.warning("DuckDB analytics database is not available yet. Run `./scripts/run_dashboard.ps1` so S3 data is synchronized and analytics are rebuilt.")

events = cached_events() if DB_PATH.exists() else pd.DataFrame()
aws_summary = load_summary(selected_run, "aws")
baseline_summary = load_summary(selected_run, "baseline")

# ---------- OVERVIEW ----------
if page == "Overview":
    section("01 · System overview", "Operational snapshot", "The current state of stored pipeline data plus the selected experiment run.")

    total = int(len(events)) if not events.empty else 0
    event_types = int(events["event_type"].nunique()) if not events.empty and "event_type" in events else 0
    success_rate = None
    if aws_summary and aws_summary.get("count"):
        success_rate = float(aws_summary.get("success_count", 0)) * 100.0 / float(aws_summary["count"])
    avg_processing = None
    if not events.empty and "processing_ms" in events.columns:
        valid = events["processing_ms"].dropna()
        avg_processing = float(valid.mean()) if not valid.empty else None
    latest = latest_timestamp(events)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Stored events", f"{total:,}")
    c2.metric("AWS success rate", pct(success_rate))
    c3.metric("Event types", f"{event_types:,}")
    c4.metric("Avg processing", ms(avg_processing))
    c5.metric("Latest processed", latest.strftime("%d %b · %H:%M UTC") if latest is not None else "—")

    st.markdown("#### Pipeline path")
    st.markdown(
        """
<div class="flow">
  <div class="flow-node"><b>1 · API Gateway</b><span>Receives simulated HTTP events</span></div>
  <div class="flow-node"><b>2 · Ingestion Lambda</b><span>Validates and normalizes input</span></div>
  <div class="flow-node"><b>3 · Amazon SQS</b><span>Durably buffers work</span></div>
  <div class="flow-node"><b>4 · Transform Lambda</b><span>Processes queued records</span></div>
  <div class="flow-node"><b>5 · S3 + DynamoDB</b><span>Stores data + idempotency status</span></div>
  <div class="flow-node"><b>6 · DuckDB + UI</b><span>Analyzes actual stored output</span></div>
</div>
""",
        unsafe_allow_html=True,
    )

    if events.empty:
        st.info("No stored events are available in DuckDB yet.")
    else:
        left, right = st.columns([1.65, 1])
        with left:
            ts = events.dropna(subset=["processed_at"]).copy()
            if not ts.empty:
                span = ts["processed_at"].max() - ts["processed_at"].min()
                bucket = "5min" if span <= pd.Timedelta(hours=8) else "1h" if span <= pd.Timedelta(days=3) else "1D"
                ts["bucket"] = ts["processed_at"].dt.floor(bucket)
                trend = ts.groupby("bucket", as_index=False).size().rename(columns={"size": "events"})
                fig = px.area(trend, x="bucket", y="events", title="Processed events over time", markers=True)
                fig.update_traces(line_color=BLUE, fillcolor="rgba(56,189,248,.14)")
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
        with right:
            by_type = events.groupby("event_type", dropna=False).size().reset_index(name="events").sort_values("events", ascending=False)
            fig = px.pie(by_type, names="event_type", values="events", hole=.64, title="Event mix", color_discrete_sequence=[BLUE, GREEN, PURPLE, AMBER, CYAN, RED])
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})

        st.markdown("#### Recent processed events")
        cols = [c for c in ["event_id", "event_type", "source", "value", "processing_ms", "processed_at"] if c in events.columns]
        recent = events.sort_values("processed_at", ascending=False, na_position="last")[cols].head(12).copy()
        st.dataframe(recent, use_container_width=True, hide_index=True, column_config={"processing_ms": st.column_config.NumberColumn("Processing (ms)", format="%.2f")})

    cw = load_cloudwatch(selected_run)
    if cw and isinstance(cw.get("functions"), dict):
        st.markdown("#### CloudWatch function telemetry")
        rows = []
        for fn, metrics in cw["functions"].items():
            inv = sum(float(x.get("Sum", 0)) for x in metrics.get("invocations", []))
            err = sum(float(x.get("Sum", 0)) for x in metrics.get("errors", []))
            dur = [float(x.get("Average", 0)) for x in metrics.get("duration_average_ms", [])]
            rows.append({"Function": fn, "Invocations": int(inv), "Errors": int(err), "Avg duration (ms)": round(sum(dur) / len(dur), 2) if dur else None})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------- EVENT ANALYTICS ----------
elif page == "Event Analytics":
    section("02 · Stored-data analytics", "Explore the events actually written to S3", "Filter the synchronized DuckDB dataset by type and source, then inspect distributions, timing and recent records.")
    if events.empty:
        st.info("No event data available. Run the S3 sync/analytics rebuild first.")
    else:
        f1, f2 = st.columns(2)
        types = sorted(str(x) for x in events["event_type"].dropna().unique())
        sources = sorted(str(x) for x in events["source"].dropna().unique())
        with f1:
            selected_types = st.multiselect("Event type", types, default=types)
        with f2:
            selected_sources = st.multiselect("Source", sources, default=sources)

        filtered = events.copy()
        if selected_types:
            filtered = filtered[filtered["event_type"].astype(str).isin(selected_types)]
        else:
            filtered = filtered.iloc[0:0]
        if selected_sources:
            filtered = filtered[filtered["source"].astype(str).isin(selected_sources)]
        else:
            filtered = filtered.iloc[0:0]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Filtered events", f"{len(filtered):,}")
        m2.metric("Sources", f"{filtered['source'].nunique():,}" if not filtered.empty else "0")
        m3.metric("Average value", f"{filtered['value'].mean():,.2f}" if not filtered.empty else "—")
        m4.metric("Median processing", ms(float(filtered["processing_ms"].median())) if not filtered.empty and filtered["processing_ms"].notna().any() else "—")

        if filtered.empty:
            st.warning("The current filters return no events.")
        else:
            a, b = st.columns(2)
            with a:
                dist = filtered.groupby("event_type", as_index=False).size().rename(columns={"size": "events"})
                fig = px.bar(dist.sort_values("events"), x="events", y="event_type", orientation="h", title="Event distribution by type", color="events", color_continuous_scale=["#164e63", BLUE])
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
            with b:
                fig = px.histogram(filtered, x="value", color="event_type", nbins=35, barmode="overlay", opacity=.64, title="Value distribution", color_discrete_sequence=[BLUE, GREEN, PURPLE, AMBER, CYAN, RED])
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})

            a, b = st.columns(2)
            with a:
                fig = px.box(filtered, x="event_type", y="value", points="outliers", title="Value range by event type", color="event_type", color_discrete_sequence=[BLUE, GREEN, PURPLE, AMBER, CYAN, RED])
                fig.update_layout(showlegend=False)
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
            with b:
                proc = filtered.dropna(subset=["processing_ms"])
                if not proc.empty:
                    fig = px.histogram(proc, x="processing_ms", nbins=35, title="Pipeline processing-time distribution")
                    fig.update_traces(marker_color=CYAN)
                    st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
                else:
                    st.info("Processing-time timestamps are not available in the stored records.")

            st.markdown("#### Recent filtered events")
            show_cols = [c for c in ["event_id", "event_type", "source", "value", "received_at", "processed_at", "processing_ms", "processor_request_id"] if c in filtered.columns]
            st.dataframe(filtered.sort_values("processed_at", ascending=False, na_position="last")[show_cols].head(100), use_container_width=True, hide_index=True)

        analytics_summary = load_analytics_summary() or {}
        rejected = load_rejected_events()
        st.markdown("#### Analytics data quality")
        q1, q2, q3 = st.columns(3)
        q1.metric("S3 JSON files seen", f"{int(analytics_summary.get('source_files', len(events))):,}")
        q2.metric("Inserted into DuckDB", f"{int(analytics_summary.get('inserted_events', len(events))):,}")
        q3.metric("Rejected files", f"{len(rejected):,}")
        if rejected:
            with st.expander("Show rejected-file diagnostics"):
                st.dataframe(pd.DataFrame(rejected), use_container_width=True, hide_index=True)
                st.caption(f"Evidence source: {ANALYTICS_REJECTED_PATH.relative_to(ROOT)}")

# ---------- BASELINE VS AWS ----------
elif page == "Baseline vs AWS":
    section("03 · Controlled comparison", "Always-on FastAPI vs AWS serverless", "Compare the same workload shape across throughput, latency, errors and scaling behavior. Values are read from the selected run's raw experiment summaries.")
    if not baseline_summary or not aws_summary:
        st.info("This run does not contain both `baseline_summary.json` and `aws_summary.json`. Run the controlled experiments first or select another run.")
    else:
        b, a = baseline_summary, aws_summary
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Baseline throughput", eps(float(b.get("throughput_events_per_second", 0))))
        k2.metric("AWS throughput", eps(float(a.get("throughput_events_per_second", 0))))
        k3.metric("Baseline p95", ms(float(b.get("p95_ms", 0))))
        k4.metric("AWS p95", ms(float(a.get("p95_ms", 0))))

        latency = pd.DataFrame(
            [
                {"Metric": label, "Baseline": b.get(key), "AWS": a.get(key)}
                for label, key in [("p50", "p50_ms"), ("p95", "p95_ms"), ("p99", "p99_ms")]
            ]
        ).melt(id_vars="Metric", var_name="Target", value_name="Latency (ms)")
        left, right = st.columns([1.15, 1])
        with left:
            fig = px.bar(latency, x="Metric", y="Latency (ms)", color="Target", barmode="group", title="Latency percentiles", color_discrete_map={"Baseline": BLUE, "AWS": AMBER})
            st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
        with right:
            rate_df = pd.DataFrame(
                [
                    {"Target": "Baseline", "Throughput (events/s)": b.get("throughput_events_per_second", 0), "Error rate (%)": b.get("error_rate_percent", 0)},
                    {"Target": "AWS", "Throughput (events/s)": a.get("throughput_events_per_second", 0), "Error rate (%)": a.get("error_rate_percent", 0)},
                ]
            )
            fig = go.Figure()
            fig.add_bar(x=rate_df["Target"], y=rate_df["Throughput (events/s)"], name="Throughput", marker_color=[BLUE, AMBER])
            fig.update_layout(title="Observed throughput", yaxis_title="events/s")
            st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})

        sat_b = load_saturation(selected_run, "baseline")
        sat_a = load_saturation(selected_run, "aws")
        if sat_b or sat_a:
            rows = []
            for target, data in [("Baseline", sat_b), ("AWS", sat_a)]:
                for item in data:
                    rows.append({"Target": target, "Concurrency": item.get("concurrency"), "Throughput": item.get("throughput_events_per_second"), "p95_ms": item.get("p95_ms"), "Error rate (%)": item.get("error_rate_percent")})
            sat = pd.DataFrame(rows)
            st.markdown("#### Scaling / saturation sweep")
            l, r = st.columns(2)
            with l:
                fig = px.line(sat, x="Concurrency", y="Throughput", color="Target", markers=True, title="Throughput vs concurrency", color_discrete_map={"Baseline": BLUE, "AWS": AMBER})
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
            with r:
                fig = px.line(sat, x="Concurrency", y="p95_ms", color="Target", markers=True, title="p95 latency vs concurrency", color_discrete_map={"Baseline": BLUE, "AWS": AMBER})
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
        else:
            st.info("No saturation sweep is attached to this run. `full_run.ps1` creates it unless `-SkipSaturation` is used.")

        comparison = load_comparison(selected_run)
        metrics = [
            ("Throughput (events/s)", "throughput_events_per_second", "Higher is better"),
            ("Error rate (%)", "error_rate_percent", "Lower is better"),
            ("p50 latency (ms)", "p50_ms", "Lower is better"),
            ("p95 latency (ms)", "p95_ms", "Lower is better"),
            ("p99 latency (ms)", "p99_ms", "Lower is better"),
        ]
        table = []
        for label, key, direction in metrics:
            delta = None
            if comparison:
                delta = (comparison.get("delta", {}).get(key) or {}).get("percent_vs_baseline")
            table.append({"KPI": label, "Baseline": b.get(key), "AWS": a.get(key), "AWS vs baseline (%)": delta, "Interpretation": direction})
        st.markdown("#### KPI comparison table")
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True, column_config={"AWS vs baseline (%)": st.column_config.NumberColumn(format="%.2f%%")})

        base_trace = load_trace(selected_run, "baseline")
        aws_trace = load_trace(selected_run, "aws")
        if not base_trace.empty and not aws_trace.empty and "latency_ms" in base_trace and "latency_ms" in aws_trace:
            t1 = base_trace.loc[base_trace.get("ok", True).astype(str).str.lower().eq("true"), ["latency_ms"]].copy() if "ok" in base_trace else base_trace[["latency_ms"]].copy()
            t2 = aws_trace.loc[aws_trace.get("ok", True).astype(str).str.lower().eq("true"), ["latency_ms"]].copy() if "ok" in aws_trace else aws_trace[["latency_ms"]].copy()
            t1["Target"] = "Baseline"; t2["Target"] = "AWS"
            raw = pd.concat([t1, t2], ignore_index=True)
            fig = px.box(raw, x="Target", y="latency_ms", points=False, title="Raw request-latency distribution", color="Target", color_discrete_map={"Baseline": BLUE, "AWS": AMBER})
            st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})

# ---------- COLD START ----------
elif page == "Cold Start Analysis":
    section("04 · Startup behavior", "Cold-start analysis", "The experiment changes a harmless Lambda environment nonce before each request to force fresh execution environments, then retains every request latency.")
    cold = load_cold_start(selected_run)
    if cold.empty or "latency_ms" not in cold.columns:
        st.info("No `cold_start_trials.csv` exists for this run. Run NT-1 / the full acceptance campaign first.")
    else:
        lat = pd.to_numeric(cold["latency_ms"], errors="coerce").dropna()
        ok = cold["ok"] if "ok" in cold.columns else pd.Series([True] * len(cold))
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Trials", f"{len(cold):,}")
        c2.metric("Success rate", pct(float(ok.mean() * 100)))
        c3.metric("p50", ms(float(lat.quantile(.50))) if not lat.empty else "—")
        c4.metric("p95", ms(float(lat.quantile(.95))) if not lat.empty else "—")
        c5.metric("p99", ms(float(lat.quantile(.99))) if not lat.empty else "—")

        l, r = st.columns(2)
        with l:
            fig = px.histogram(cold, x="latency_ms", nbins=min(20, max(5, len(cold) // 2)), title="Cold-start latency distribution")
            fig.update_traces(marker_color=CYAN)
            st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
        with r:
            fig = px.line(cold, x="trial", y="latency_ms", markers=True, title="Latency by cold-start trial")
            fig.update_traces(line_color=BLUE, marker_color=AMBER)
            if not lat.empty:
                fig.add_hline(y=float(lat.quantile(.95)), line_dash="dash", line_color=RED, annotation_text="p95")
            st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})

        st.markdown("#### Trial evidence")
        st.dataframe(cold, use_container_width=True, hide_index=True, column_config={"latency_ms": st.column_config.NumberColumn("Latency (ms)", format="%.3f")})

        nt1 = next((x for x in load_negative_tests(selected_run) if x.get("test_id") == "NT-1"), None)
        if nt1:
            st.markdown("#### NT-1 acceptance evidence")
            st.markdown(status_badge(str(nt1.get("status", "UNKNOWN"))), unsafe_allow_html=True)
            st.write("**Expected:**", nt1.get("expected", "—"))
            st.write("**Observed:**", nt1.get("observed", "—"))
            st.write("**Recovery:**", nt1.get("recovery", "—"))
            st.caption(str(nt1.get("residual_risk", "")))

# ---------- COST ----------
elif page == "Cost Analysis":
    section("05 · Economics", "Cost-per-event and component analysis", "Cost evidence distinguishes measured Lambda usage, declared request-count bounds, captured AWS pricing and the modeled always-on baseline.")
    cost = load_cost(selected_run)
    pricing = load_pricing()
    if not cost:
        st.info("No `cost_analysis.json` is available for the selected run. Run pricing capture and cost analysis first.")
        if pricing:
            st.caption(f"A pricing snapshot is available from {pricing.get('captured_at', 'unknown time')} for {pricing.get('region', 'unknown region')}.")
    elif str(cost.get("status", "")).upper() != "OK":
        st.markdown(status_badge(str(cost.get("status", "HOLD"))), unsafe_allow_html=True)
        st.warning(f"Cost analysis is not publishable for this run yet: {cost.get('reason', 'incomplete evidence')}")
        if cost.get("missing"):
            st.write("Missing normalized price dimensions:", cost["missing"])
    else:
        srv = cost.get("serverless", {})
        base = cost.get("always_on_baseline", {})
        serverless_total = srv.get("estimated_total_usd")
        serverless_per = srv.get("estimated_cost_per_accepted_event_usd")
        baseline_total = base.get("modeled_cost_for_measured_run_usd")
        baseline_per = base.get("modeled_cost_per_successful_event_usd")
        per_million = pricing.get("estimated_serverless_usd_per_million_events") if pricing else None

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Serverless run cost", usd(serverless_total))
        c2.metric("Serverless / event", usd(serverless_per))
        c3.metric("Baseline modeled run", usd(baseline_total))
        c4.metric("Baseline / event", usd(baseline_per))
        c5.metric("Pre-spend / 1M events", usd(per_million))

        component = srv.get("component_cost_usd", {})
        if component:
            comp = pd.DataFrame([{"Component": k.replace("_", " ").title(), "USD": float(v)} for k, v in component.items()]).sort_values("USD", ascending=True)
            left, right = st.columns([1.2, 1])
            with left:
                fig = px.bar(comp, x="USD", y="Component", orientation="h", title="Serverless cost breakdown", color="USD", color_continuous_scale=["#164e63", CYAN])
                fig.update_layout(coloraxis_showscale=False)
                st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})
            with right:
                compare = pd.DataFrame([{"Architecture": "AWS serverless", "Cost/event": serverless_per}, {"Architecture": "Always-on baseline", "Cost/event": baseline_per}]).dropna()
                if not compare.empty:
                    fig = px.bar(compare, x="Architecture", y="Cost/event", title="Normalized cost per successful event", color="Architecture", color_discrete_map={"AWS serverless": GREEN, "Always-on baseline": BLUE})
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(style_fig(fig), use_container_width=True, config={"displaylogo": False})

        st.markdown("#### Measurement basis")
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="panel"><b>Serverless</b><br><span class="small-note">Lambda invocation count and billed GB-seconds come from CloudWatch REPORT lines. SQS/S3/DynamoDB request counts are declared conservative bounds over accepted events.</span></div>', unsafe_allow_html=True)
            usage_rows = []
            for label, key in [("Ingestion Lambda", "lambda_ingestion_usage"), ("Transformer Lambda", "lambda_transformer_usage")]:
                u = srv.get(key, {})
                usage_rows.append({"Function": label, "Report invocations": u.get("invocations_from_report_lines"), "Billed ms": u.get("billed_ms_sum"), "GB-seconds": u.get("gb_seconds")})
            st.dataframe(pd.DataFrame(usage_rows), use_container_width=True, hide_index=True)
        with right:
            st.markdown('<div class="panel"><b>Always-on baseline</b><br><span class="small-note">Performance is measured locally; cost is modeled using the captured on-demand price of the declared EC2 reference instance. It is not presented as an AWS invoice.</span></div>', unsafe_allow_html=True)
            st.write("**Modeled instance:**", base.get("modeled_instance", "—"))
            st.write("**Measured elapsed:**", f"{float(base.get('measured_elapsed_seconds', 0)):,.3f} s")
            st.write("**Captured hourly rate:**", usd(base.get("captured_hourly_rate_usd")))

        limitations = cost.get("limitations", [])
        if limitations:
            with st.expander("Cost assumptions and limitations"):
                for item in limitations:
                    st.markdown(f"- {item}")
                if pricing:
                    st.caption(f"Pricing source: {pricing.get('source', 'AWS pricing snapshot')} · captured {pricing.get('captured_at', '—')}")

# ---------- NEGATIVE TESTS ----------
elif page == "Negative Tests":
    section("06 · Reliability & assurance", "Five mandatory negative tests", "Review PASS/HOLD/FAIL status, expected vs observed behavior, recovery action, recovery time and residual risk without hiding incomplete tests.")
    tests = load_negative_tests(selected_run)
    if not tests:
        st.info("No negative-test evidence exists for this run. Run `./scripts/run_negative_tests.ps1 -RunId <run>` or the full project workflow.")
    else:
        statuses = [str(t.get("status", "UNKNOWN")).upper() for t in tests]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tests executed", len(tests))
        c2.metric("PASS", statuses.count("PASS"))
        c3.metric("HOLD", statuses.count("HOLD"))
        c4.metric("FAIL", statuses.count("FAIL"))

        summary_rows = []
        for t in tests:
            tid = str(t.get("test_id", "—"))
            summary_rows.append(
                {
                    "Test": tid,
                    "Scenario": SCENARIO_NAMES.get(tid, tid),
                    "Status": str(t.get("status", "UNKNOWN")).upper(),
                    "Observed": json_compact(t.get("observed", "—")),
                    "Recovery time (s)": t.get("recovery_time_seconds"),
                    "Evidence": t.get("evidence_file"),
                }
            )
        summary = pd.DataFrame(summary_rows)
        st.dataframe(summary, use_container_width=True, hide_index=True, column_config={"Recovery time (s)": st.column_config.NumberColumn(format="%.3f")})

        st.markdown("#### Test details")
        for t in tests:
            tid = str(t.get("test_id", "—"))
            status = str(t.get("status", "UNKNOWN")).upper()
            title = f"{tid} · {SCENARIO_NAMES.get(tid, tid)} · {status}"
            with st.expander(title, expanded=False):
                st.markdown(status_badge(status), unsafe_allow_html=True)
                st.write("**Fixture:**", t.get("fixture_id", "—"))
                if "precondition" in t:
                    st.write("**Precondition:**", t.get("precondition"))
                st.write("**Expected safe behavior:**", t.get("expected", "—"))
                st.write("**Observed:**")
                if isinstance(t.get("observed"), (dict, list)):
                    st.json(t.get("observed"), expanded=True)
                else:
                    st.write(t.get("observed", "—"))
                if t.get("recovery_time_seconds") is not None:
                    st.write("**Recovery time:**", f"{float(t['recovery_time_seconds']):,.3f} seconds")
                st.write("**Recovery procedure:**", t.get("recovery", "—"))
                st.write("**Residual risk:**", t.get("residual_risk", "—"))
                st.caption(f"Evidence file: {t.get('evidence_file', '—')} · executed {t.get('executed_at', '—')}")

st.markdown("---")
st.caption("Dashboard values are sourced from the local DuckDB database and versioned evidence under `evidence/runs/`. Missing measurements are shown as unavailable/HOLD rather than fabricated.")
