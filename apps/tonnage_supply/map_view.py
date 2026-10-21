"""Vessel map — Plotly scattermap (same spirit as polygon_tracker).

OpenStreetMap ignores non-circle marker symbols. Shuttle ships are drawn as a
black halo + colored core + ◆ text so they stay obvious in the browser.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

_SHUTTLE_GLYPH = "◆"


def _as_bool_series(s: pd.Series) -> pd.Series:
    """Robust bool after JSON round-trip (avoids bool('False') == True)."""

    def _one(v) -> bool:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        return str(v).strip().lower() in {"1", "true", "yes", "y", "t"}

    return s.map(_one).astype(bool)


def _color_for(row: pd.Series) -> str:
    if bool(row.get("sanctioned_any")):
        return "#c0392b"
    state = str(row.get("vessel_state") or "").lower()
    if state == "loaded":
        return "#2ecc71"
    if state == "ballast":
        return "#e67e22"
    return "#34495e"


def _hover(df: pd.DataFrame) -> pd.Series:
    name = df["vessel"] if "vessel" in df.columns else df.get("imo", pd.Series([""] * len(df)))
    shuttle = (
        _as_bool_series(df["shuttle_available"]).map({True: "Yes", False: "No"})
        if "shuttle_available" in df.columns
        else pd.Series(["—"] * len(df), index=df.index)
    )
    return (
        name.astype(str)
        + "<br>State: "
        + df.get("vessel_state", pd.Series([""] * len(df))).astype(str)
        + "<br>Owner: "
        + df.get("owner", pd.Series([""] * len(df))).astype(str)
        + "<br>Shuttle: "
        + shuttle.astype(str)
        + "<br>Sanctioned: "
        + df.get("sanctioned_label", pd.Series([""] * len(df))).astype(str)
        + "<br>Pos: "
        + df.get("position_source", pd.Series([""] * len(df))).astype(str)
    )


def _add_trace(fig: go.Figure, kwargs: dict, *, use_mapbox: bool) -> None:
    fig.add_trace(go.Scattermapbox(**kwargs) if use_mapbox else go.Scattermap(**kwargs))


def _add_fleet(fig: go.Figure, fleet: pd.DataFrame, *, use_mapbox: bool) -> None:
    if fleet.empty:
        return
    labels = fleet["vessel"] if "vessel" in fleet.columns else fleet.get("imo", pd.Series([""] * len(fleet)))
    _add_trace(
        fig,
        dict(
            lat=fleet["latitude"],
            lon=fleet["longitude"],
            mode="markers",
            marker=dict(size=9, color=fleet.apply(_color_for, axis=1).tolist(), opacity=0.9),
            text=labels.astype(str),
            hovertext=_hover(fleet),
            hoverinfo="text",
            name="Fleet",
            showlegend=True,
        ),
        use_mapbox=use_mapbox,
    )


def _add_shuttle(fig: go.Figure, shuttle: pd.DataFrame, *, use_mapbox: bool) -> None:
    """Halo + core + ◆ text. Does not rely on marker.symbol (broken on OSM)."""
    if shuttle.empty:
        return
    shuttle = shuttle.copy()
    shuttle["_color"] = shuttle.apply(_color_for, axis=1)
    first = True
    for color, grp in shuttle.groupby("_color", sort=False):
        hover = _hover(grp)
        # 1) Black halo (drawn first, underneath)
        _add_trace(
            fig,
            dict(
                lat=grp["latitude"],
                lon=grp["longitude"],
                mode="markers",
                marker=dict(size=18, color="#111111", opacity=0.95),
                hoverinfo="skip",
                name="Shuttle",
                legendgroup="shuttle",
                showlegend=False,
            ),
            use_mapbox=use_mapbox,
        )
        # 2) Colored core + diamond character
        _add_trace(
            fig,
            dict(
                lat=grp["latitude"],
                lon=grp["longitude"],
                mode="markers+text",
                marker=dict(size=11, color=str(color), opacity=1.0),
                text=[_SHUTTLE_GLYPH] * len(grp),
                textfont=dict(size=16, color="#111111", family="Arial Black, Arial, sans-serif"),
                textposition="middle center",
                hovertext=hover,
                hoverinfo="text",
                name="Shuttle",
                legendgroup="shuttle",
                showlegend=first,
            ),
            use_mapbox=use_mapbox,
        )
        first = False


def vessels_map(
    vessels: pd.DataFrame,
    *,
    destination: str | None = None,
    revision: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    # Fresh uirevision each Apply/fetch — otherwise Plotly keeps old pan/zoom
    # (and sometimes stale map traces) when only marker data changes.
    ui_rev = revision or destination or "default"
    title_dest = f" — {destination}" if destination else ""
    empty_layout = dict(
        title=f"Vessel map{title_dest}",
        map=dict(style="open-street-map", center=dict(lat=25.0, lon=56.0), zoom=4),
        margin=dict(l=0, r=0, t=40, b=0),
        height=480,
        uirevision=ui_rev,
    )
    if vessels is None or vessels.empty or "latitude" not in vessels.columns:
        fig.update_layout(**empty_layout)
        return fig

    df = vessels.dropna(subset=["latitude", "longitude"]).copy()
    if df.empty:
        empty_layout["title"] = "Vessel map (no positions)"
        fig.update_layout(**empty_layout)
        return fig

    if "shuttle_available" not in df.columns:
        df["shuttle_available"] = False
    else:
        df["shuttle_available"] = _as_bool_series(df["shuttle_available"])

    shuttle = df.loc[df["shuttle_available"]]
    fleet = df.loc[~df["shuttle_available"]]
    center = dict(lat=float(df["latitude"].median()), lon=float(df["longitude"].median()))
    legend = dict(orientation="h", yanchor="bottom", y=1.02, x=0)

    try:
        _add_fleet(fig, fleet, use_mapbox=False)
        _add_shuttle(fig, shuttle, use_mapbox=False)
        fig.update_layout(
            title=f"Vessel map{title_dest} (black ring + {_SHUTTLE_GLYPH} = shuttle)",
            map=dict(style="open-street-map", center=center, zoom=4),
            margin=dict(l=0, r=0, t=50, b=0),
            height=480,
            legend=legend,
            uirevision=ui_rev,
        )
    except Exception:
        fig = go.Figure()
        _add_fleet(fig, fleet, use_mapbox=True)
        _add_shuttle(fig, shuttle, use_mapbox=True)
        fig.update_layout(
            title=f"Vessel map{title_dest} (black ring + {_SHUTTLE_GLYPH} = shuttle)",
            mapbox=dict(style="open-street-map", center=center, zoom=4),
            margin=dict(l=0, r=0, t=50, b=0),
            height=480,
            legend=legend,
            uirevision=ui_rev,
        )
    return fig
