"""
Tonnage supply Dash app (v0).

Run from freight_dashboard/:
  python -m apps.tonnage_supply.app
  # or
  python apps/tonnage_supply/app.py

Then open http://127.0.0.1:8050
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python apps/tonnage_supply/app.py` without installing the package.
_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO / "apps") not in sys.path:
    sys.path.insert(0, str(_REPO / "apps"))

import dash
from dash import Input, Output, State, dcc, html, dash_table, no_update
import dash_bootstrap_components as dbc

try:
    from apps.tonnage_supply import charts, config, map_view, tables
except ImportError:  # running as script from apps/tonnage_supply/
    import charts
    import config
    import map_view
    import tables

from freight.kpler import (
    fetch_location_options,
    fetch_product_filter_options,
    liquids_config,
    liquids_vessel_type_labels,
)
from freight.tonnage_supply import load_tonnage_bundle

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    title="Tonnage supply",
)
server = app.server


def _bootstrap_options():
    """Best-effort location/product lists; empty if credentials missing at import."""
    locations = [{"label": config.DEFAULT_DESTINATION, "value": config.DEFAULT_DESTINATION}]
    products: list[dict] = []
    try:
        cfg = liquids_config(config.REPO_ROOT)
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        loc = fetch_location_options(cfg, cache_path=config.CACHE_DIR / "locations.parquet")
        # Prefer freight-useful names; always keep Fujairah first.
        names = loc["name"].astype(str).tolist()
        preferred = [config.DEFAULT_DESTINATION, "Mideast Gulf", "Singapore", "China", "Houston"]
        ordered = []
        for p in preferred:
            if p in names and p not in ordered:
                ordered.append(p)
        for n in names:
            if n not in ordered:
                ordered.append(n)
            if len(ordered) >= config.LOCATION_DROPDOWN_LIMIT:
                break
        locations = [{"label": n, "value": n} for n in ordered]

        prod = fetch_product_filter_options(cfg, cache_path=config.CACHE_DIR / "products.parquet")
        products = [
            {
                "label": f"{r['family']} › {r['label']}" if r["level"] == "group" else r["label"],
                "value": r["label"],
            }
            for _, r in prod.iterrows()
        ]
    except Exception as exc:  # noqa: BLE001
        print("bootstrap options skipped:", type(exc).__name__, exc)
    return locations, products


_LOCATIONS, _PRODUCTS = _bootstrap_options()
_VESSEL_TYPES = [{"label": t, "value": t} for t in liquids_vessel_type_labels()]


def _filter_bar():
    return dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label("Location"),
                                dcc.Dropdown(
                                    id="f-location",
                                    options=_LOCATIONS,
                                    value=config.DEFAULT_DESTINATION,
                                    clearable=False,
                                    searchable=True,
                                ),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Match next port call"),
                                dbc.Switch(id="f-match-next", value=config.DEFAULT_MATCH_NEXT_PORT),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("ETA (days)"),
                                dcc.Dropdown(
                                    id="f-eta",
                                    options=[
                                        {"label": "ETA 0 - 7 days", "value": 7},
                                        {"label": "ETA 0 - 14 days", "value": 14},
                                        {"label": "ETA 0 - 21 days", "value": 21},
                                    ],
                                    value=config.DEFAULT_ETA,
                                    clearable=False,
                                ),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Avg speed (kn)"),
                                dbc.Input(id="f-speed", type="number", value=config.DEFAULT_SPEED, min=5, max=20),
                            ],
                            md=1,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Units"),
                                dbc.RadioItems(
                                    id="f-metric",
                                    options=[
                                        {"label": "Count", "value": "count"},
                                        {"label": "Deadweight", "value": "deadweight"},
                                    ],
                                    value=config.DEFAULT_METRIC,
                                    inline=True,
                                ),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("State"),
                                dbc.RadioItems(
                                    id="f-state",
                                    options=[
                                        {"label": "All", "value": "all"},
                                        {"label": "Loaded", "value": "Loaded"},
                                        {"label": "Ballast", "value": "Ballast"},
                                    ],
                                    value=config.DEFAULT_STATE,
                                    inline=True,
                                ),
                            ],
                            md=2,
                        ),
                    ],
                    className="g-2",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Label("Vessel classification"),
                                dcc.Dropdown(
                                    id="f-vessel-types",
                                    options=_VESSEL_TYPES,
                                    value=config.DEFAULT_VESSEL_TYPES,
                                    multi=True,
                                ),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Build year min / max"),
                                dbc.InputGroup(
                                    [
                                        dbc.Input(
                                            id="f-year-min",
                                            type="number",
                                            value=config.DEFAULT_BUILD_YEAR_MIN,
                                        ),
                                        dbc.Input(
                                            id="f-year-max",
                                            type="number",
                                            value=config.DEFAULT_BUILD_YEAR_MAX,
                                        ),
                                    ]
                                ),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Last products"),
                                dcc.Dropdown(
                                    id="f-products",
                                    options=_PRODUCTS,
                                    value=None,
                                    multi=True,
                                    placeholder="All products",
                                ),
                            ],
                            md=3,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("Sanctions"),
                                dbc.RadioItems(
                                    id="f-sanctions",
                                    options=[
                                        {"label": "All", "value": "all"},
                                        {"label": "Sanctioned", "value": "sanctioned"},
                                        {"label": "Clean", "value": "clean"},
                                    ],
                                    value=config.DEFAULT_SANCTION_VIEW,
                                    inline=True,
                                ),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                dbc.Label("AIS dark (>10d)"),
                                dbc.RadioItems(
                                    id="f-ais-dark",
                                    options=[
                                        {"label": "All", "value": "all"},
                                        {"label": "Non-dark", "value": "non_dark"},
                                    ],
                                    value=config.DEFAULT_AIS_DARK_VIEW,
                                    inline=True,
                                ),
                            ],
                            md=2,
                        ),
                        dbc.Col(
                            [
                                dbc.Label(" "),
                                dbc.Button("Apply", id="btn-apply", color="primary", className="w-100"),
                                html.A("Reset all", id="btn-reset", href="#", className="small d-block mt-1"),
                            ],
                            md=2,
                        ),
                    ],
                    className="g-2 mt-1",
                ),
            ]
        ),
        className="mb-3",
    )


app.layout = dbc.Container(
    [
        dcc.Store(id="store-bundle"),
        dcc.Store(id="store-status"),
        html.H3("Tonnage supply", className="mt-3 mb-1"),
        html.P(id="status-line", className="text-muted small"),
        _filter_bar(),
        dbc.Row(
            [
                dbc.Col(dcc.Loading(dcc.Graph(id="chart-history")), md=7),
                dbc.Col(dcc.Loading(dcc.Graph(id="chart-state")), md=5),
            ]
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H5("Vessel list", className="mt-3"),
                        dcc.Loading(
                            dash_table.DataTable(
                                id="vessel-table",
                                page_size=20,
                                sort_action="native",
                                filter_action="native",
                                style_table={"overflowX": "auto"},
                                style_cell={"fontSize": 12, "padding": "6px", "textAlign": "left"},
                                style_header={"fontWeight": "600", "backgroundColor": "#f0f2f5"},
                            )
                        ),
                    ],
                    md=7,
                ),
                dbc.Col(
                    dcc.Loading(html.Div(id="map-container")),
                    md=5,
                ),
            ]
        ),
    ],
    fluid=True,
)


@app.callback(
    Output("f-location", "value"),
    Output("f-match-next", "value"),
    Output("f-eta", "value"),
    Output("f-speed", "value"),
    Output("f-metric", "value"),
    Output("f-state", "value"),
    Output("f-vessel-types", "value"),
    Output("f-year-min", "value"),
    Output("f-year-max", "value"),
    Output("f-products", "value"),
    Output("f-sanctions", "value"),
    Output("f-ais-dark", "value"),
    Input("btn-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_n):
    return (
        config.DEFAULT_DESTINATION,
        config.DEFAULT_MATCH_NEXT_PORT,
        config.DEFAULT_ETA,
        config.DEFAULT_SPEED,
        config.DEFAULT_METRIC,
        config.DEFAULT_STATE,
        config.DEFAULT_VESSEL_TYPES,
        config.DEFAULT_BUILD_YEAR_MIN,
        config.DEFAULT_BUILD_YEAR_MAX,
        None,
        config.DEFAULT_SANCTION_VIEW,
        config.DEFAULT_AIS_DARK_VIEW,
    )


@app.callback(
    Output("store-bundle", "data"),
    Output("status-line", "children"),
    Input("btn-apply", "n_clicks"),
    State("f-location", "value"),
    State("f-match-next", "value"),
    State("f-eta", "value"),
    State("f-speed", "value"),
    State("f-metric", "value"),
    State("f-state", "value"),
    State("f-vessel-types", "value"),
    State("f-year-min", "value"),
    State("f-year-max", "value"),
    State("f-products", "value"),
    State("f-sanctions", "value"),
    State("f-ais-dark", "value"),
)
def load_data(
    _n, location, match_next, eta, speed, metric, state, vtypes, ymin, ymax, products, sanctions, ais_dark
):
    # Initial load + Apply only (filters are State — change then click Apply)
    try:
        vessel_states = None if not state or state == "all" else [state]
        products = products or None
        bundle = load_tonnage_bundle(
            config.REPO_ROOT,
            destination=location or config.DEFAULT_DESTINATION,
            eta=int(eta or config.DEFAULT_ETA),
            speed=int(speed or config.DEFAULT_SPEED),
            metric=metric or config.DEFAULT_METRIC,
            vessel_types=vtypes or config.DEFAULT_VESSEL_TYPES,
            vessel_states=vessel_states,
            products=products,
            build_year_min=int(ymin or config.DEFAULT_BUILD_YEAR_MIN),
            build_year_max=int(ymax or config.DEFAULT_BUILD_YEAR_MAX),
            match_next_port_call=bool(match_next),
            sanction_view=sanctions or "all",
            ais_dark_view=ais_dark or "all",
            cache_dir=config.CACHE_DIR,
        )
        vessels = bundle["vessels"]
        series = bundle["series"]
        payload = {
            "vessels": vessels.to_json(date_format="iso", orient="split"),
            "series": series.to_json(date_format="iso", orient="split"),
            "meta": {
                "fetched_at": bundle["fetched_at"],
                "n_matcher": bundle["n_matcher"],
                "n_visible": bundle["n_visible"],
                "destination": bundle["destination"],
                "metric": metric or config.DEFAULT_METRIC,
            },
        }
        status = (
            f"{bundle['destination']} · matcher {bundle['n_matcher']} · "
            f"visible {bundle['n_visible']} · fetched {bundle['fetched_at']}"
        )
        return payload, status
    except Exception as exc:  # noqa: BLE001
        return no_update, f"Error: {type(exc).__name__}: {exc}"


@app.callback(
    Output("chart-history", "figure"),
    Output("chart-state", "figure"),
    Output("vessel-table", "data"),
    Output("vessel-table", "columns"),
    Output("map-container", "children"),
    Input("store-bundle", "data"),
)
def render(bundle):
    import pandas as pd

    meta = bundle.get("meta") or {} if bundle else {}
    # Remount map Graph on every fetch — Scattermap often keeps old camera/traces
    # when only the figure prop is updated in place.
    map_rev = f"{meta.get('destination', '')}|{meta.get('fetched_at', '')}"

    empty_hist = charts.history_figure(pd.DataFrame())
    empty_state = charts.state_proximity_figure(pd.DataFrame())

    def _map_graph(fig):
        # Unique id remounts the map (dcc.Graph has no React ``key`` prop in Dash 4).
        safe = "".join(ch if ch.isalnum() else "-" for ch in map_rev)[:80]
        return dcc.Graph(
            id=f"vessel-map-{safe}",
            figure=fig,
            config={"scrollZoom": True},
        )

    if not bundle:
        return (
            empty_hist,
            empty_state,
            [],
            [],
            _map_graph(map_view.vessels_map(pd.DataFrame(), revision=map_rev)),
        )

    vessels = pd.read_json(bundle["vessels"], orient="split")
    series = pd.read_json(bundle["series"], orient="split")
    metric = meta.get("metric", "count")
    metric_label = "Deadweight" if metric == "deadweight" else "Count"

    table = tables.vessels_for_table(vessels)
    cols = [{"name": c, "id": c} for c in table.columns]
    fig_map = map_view.vessels_map(
        vessels,
        destination=meta.get("destination"),
        revision=map_rev,
    )
    return (
        charts.history_figure(series, metric_label=metric_label),
        charts.state_proximity_figure(vessels),
        table.to_dict("records"),
        cols,
        _map_graph(fig_map),
    )


def main():
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
