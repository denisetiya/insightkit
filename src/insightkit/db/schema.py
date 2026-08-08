"""Schema metadata model + prompt-ready summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

NUMERIC_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint", "real", "double", "float",
    "numeric", "decimal", "number", "money",
}
DATE_TYPES = {"date", "datetime", "timestamp", "time"}


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    nullable: bool = True
    is_pk: bool = False
    fk_ref: str | None = None  # "table.column"


@dataclass
class TableMeta:
    name: str
    columns: list[ColumnMeta] = field(default_factory=list)
    row_count: int | None = None
    sample: dict[str, list[str]] = field(default_factory=dict)

    def column(self, name: str) -> ColumnMeta | None:
        return next((c for c in self.columns if c.name.lower() == name.lower()), None)


@dataclass
class SchemaMetadata:
    db_key: str
    dialect: str
    tables: list[TableMeta] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def table(self, name: str) -> TableMeta | None:
        return next((t for t in self.tables if t.name.lower() == name.lower()), None)

    def render(self, max_tables: int = 200, max_cols_per_table: int = 40) -> str:
        """Compact text representation injected into the LLM prompt."""
        lines: list[str] = []
        for t in self.tables[:max_tables]:
            cols = t.columns[:max_cols_per_table]
            col_str = ", ".join(
                f"{c.name} {c.data_type}"
                f"{' PK' if c.is_pk else ''}"
                f"{' FK->' + c.fk_ref if c.fk_ref else ''}"
                for c in cols
            )
            lines.append(f"TABLE {t.name} ({col_str})")
            if t.sample:
                sample_str = "; ".join(
                    f"{col}={vals[:5]}" for col, vals in t.sample.items() if vals
                )
                if sample_str:
                    lines.append(f"  samples: {sample_str}")
        return "\n".join(lines)
