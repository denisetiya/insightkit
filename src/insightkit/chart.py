"""Auto-chart: plotly figure JSON from a result set (best-effort, never crashes)."""

from __future__ import annotations

import polars as pl

_CHART_ROW_LIMIT = 500
_NUMERIC_DTYPES = frozenset(
    {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
        pl.Decimal,
    }
)


def _numeric_columns(df: pl.DataFrame) -> list[str]:
    return [c for c in df.columns if df.schema.get(c) in _NUMERIC_DTYPES]


def _category_column(df: pl.DataFrame, numeric: list[str]) -> str | None:
    for c in df.columns:
        if c not in numeric:
            return c
    return None


def build_chart(df: pl.DataFrame | None, max_rows: int = _CHART_ROW_LIMIT) -> str | None:
    """Return a plotly figure JSON string, or None when not chartable."""
    if df is None or df.height == 0 or len(df.columns) < 2:
        return None
    try:
        import plotly.graph_objects as go

        numeric = _numeric_columns(df)
        if not numeric:
            return None
        x_col = _category_column(df, numeric) or df.columns[0]
        y_col = numeric[0]
        frame = df.select([x_col, y_col]).head(max_rows)
        x_vals = frame[x_col].to_list()
        y_vals = frame[y_col].to_list()
        date_like = any(k in x_col.lower() for k in ("date", "time", "month", "year", "day"))
        if date_like:
            fig = go.Figure(go.Scatter(x=x_vals, y=y_vals, mode="lines+markers"))
        else:
            fig = go.Figure(go.Bar(x=x_vals, y=y_vals))
        return fig.to_json()
    except Exception:
        return None
