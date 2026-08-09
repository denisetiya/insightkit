"""Auto-chart — plotly figure JSON from a result set (best-effort, never crashes)."""

from __future__ import annotations

import polars as pl


def build_chart(df: pl.DataFrame | None) -> str | None:
    """Return a plotly figure JSON string, or None when not chartable."""
    if df is None or df.height == 0:
        return None
    try:
        import plotly.graph_objects as go

        cols = df.columns
        if len(cols) < 2:
            return None
        numeric: list[str] = []
        for c in cols:
            try:
                if df[c].dtype in {
                    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                    pl.Float32, pl.Float64,
                    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                }:
                    numeric.append(c)
            except Exception:
                continue
        if not numeric:
            return None
        x_col = next((c for c in cols if c not in numeric), cols[0])
        y_col = numeric[0]
        x_vals = df[x_col].to_list()
        y_vals = df[y_col].to_list()
        date_like = any(k in x_col.lower() for k in ("date", "time", "month", "year", "day"))
        if date_like:
            fig = go.Figure(go.Scatter(x=x_vals, y=y_vals, mode="lines+markers"))
        else:
            fig = go.Figure(go.Bar(x=x_vals, y=y_vals))
        return fig.to_json()
    except Exception:
        return None
