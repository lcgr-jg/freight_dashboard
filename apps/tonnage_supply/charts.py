"""Plotly charts for tonnage-supply app."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def history_figure(series: pd.DataFrame, *, metric_label: str = "Count") -> go.Figure:
    fig = go.Figure()
    if series is None or series.empty or "Date" not in series.columns:
        fig.update_layout(title="Historical availability", template="plotly_white", height=320)
        return fig

    df = series.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    value_col = "value" if "value" in df.columns else next(
        (c for c in df.columns if c != "Date" and pd.api.types.is_numeric_dtype(df[c])),
        None,
    )
    if value_col is None:
        fig.update_layout(title="Historical availability", template="plotly_white", height=320)
        return fig

    df = df.dropna(subset=["Date"]).sort_values("Date")
    y = pd.to_numeric(df[value_col], errors="coerce")
    fig.add_trace(go.Bar(x=df["Date"], y=y, name=metric_label, marker_color="#1f2a44"))
    ma = y.rolling(10, min_periods=3).mean()
    fig.add_trace(
        go.Scatter(x=df["Date"], y=ma, name="10d MA", mode="lines", line=dict(color="#e67e22", width=2))
    )
    fig.update_layout(
        title="Historical availability",
        template="plotly_white",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis_title=metric_label,
    )
    return fig


def state_proximity_figure(vessels: pd.DataFrame) -> go.Figure:
    """Loaded/Ballast share + proximity bucket counts."""
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=1,
        cols=2,
        column_widths=[0.35, 0.65],
        subplot_titles=("State", "Proximity"),
        specs=[[{"type": "bar"}, {"type": "bar"}]],
    )
    if vessels is None or vessels.empty:
        fig.update_layout(template="plotly_white", height=320)
        return fig

    state_col = "vessel_state" if "vessel_state" in vessels.columns else None
    if state_col:
        states = vessels[state_col].fillna("Other").astype(str)
        counts = states.value_counts()
        colors = {"Loaded": "#2ecc71", "Ballast": "#e67e22", "Maintenance": "#95a5a6", "Other": "#7f8c8d"}
        fig.add_trace(
            go.Bar(
                x=counts.index.tolist(),
                y=counts.values.tolist(),
                marker_color=[colors.get(k, "#34495e") for k in counts.index],
                showlegend=False,
            ),
            row=1,
            col=1,
        )

    if "proximity" in vessels.columns:
        order = ["0-2 days", "2-4 days", "4-7 days", ">7 days"]
        prox = vessels["proximity"].fillna("unknown").astype(str)
        counts = prox.value_counts()
        xs = [k for k in order if k in counts.index] + [k for k in counts.index if k not in order]
        ys = [int(counts.get(k, 0)) for k in xs]
        fig.add_trace(
            go.Bar(x=xs, y=ys, marker_color="#1f2a44", showlegend=False),
            row=1,
            col=2,
        )

    fig.update_layout(template="plotly_white", height=320, margin=dict(l=40, r=20, t=50, b=40))
    return fig
