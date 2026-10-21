"""Thin NOC owner tagging from a curated YAML alias list."""

from __future__ import annotations

from pathlib import Path

import yaml


def default_noc_path(repo_root: Path) -> Path:
    return repo_root / "config" / "noc_owners.yml"


def load_noc_aliases(path: Path | None = None, *, repo_root: Path | None = None) -> list[str]:
    if path is None:
        if repo_root is None:
            raise ValueError("path or repo_root required")
        path = default_noc_path(repo_root)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    aliases = data.get("noc_owners") or []
    return [str(a).strip() for a in aliases if str(a).strip()]


def is_noc_owner(owner: object, aliases: list[str]) -> bool:
    if owner is None or (isinstance(owner, float) and pd_isna(owner)):
        return False
    text = str(owner).strip().lower()
    if not text or text == "nan":
        return False
    return any(a.lower() in text for a in aliases)


def pd_isna(v) -> bool:
    try:
        import pandas as pd

        return bool(pd.isna(v))
    except Exception:
        return False


def attach_noc_flag(
    df,
    *,
    owner_col: str = "owner",
    aliases: list[str] | None = None,
    repo_root: Path | None = None,
):
    import pandas as pd

    out = df.copy()
    al = aliases if aliases is not None else load_noc_aliases(repo_root=repo_root)
    if owner_col not in out.columns:
        out["is_noc"] = False
        return out
    out["is_noc"] = out[owner_col].map(lambda v: is_noc_owner(v, al))
    return out
