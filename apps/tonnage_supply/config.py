"""Defaults and paths for the tonnage-supply Dash app."""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
CACHE_DIR = APP_DIR / ".cache"

DEFAULT_DESTINATION = "Fujairah"
DEFAULT_ETA = 7
DEFAULT_SPEED = 11
DEFAULT_METRIC = "count"  # count | deadweight
DEFAULT_STATE = "all"  # all | Loaded | Ballast
DEFAULT_SANCTION_VIEW = "all"  # all | sanctioned | clean
DEFAULT_AIS_DARK_VIEW = "all"  # all | non_dark (>10d since last AIS)
DEFAULT_VESSEL_TYPES = ["VLCC"]
DEFAULT_BUILD_YEAR_MIN = 2010
DEFAULT_BUILD_YEAR_MAX = 2026
DEFAULT_MATCH_NEXT_PORT = False
SERIES_LOOKBACK_DAYS = 90

# Keep API payload small for location dropdown
LOCATION_DROPDOWN_LIMIT = 800
