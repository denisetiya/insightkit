"""Semantic layer — YAML metric definitions + glossary + aliases for consistent answers."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class MetricDef(BaseModel):
    name: str
    definition: str
    description: str = ""


class SemanticLayer(BaseModel):
    metrics: list[MetricDef] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    aliases: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None) -> SemanticLayer:
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Semantic file not found: {p}")
        data = yaml.safe_load(p.read_text()) or {}
        return cls(**data)

    def render(self) -> str:
        """Text injected into the prompt (METRIC DEFINITIONS section)."""
        lines: list[str] = []
        for m in self.metrics:
            line = f"- {m.name} = {m.definition}"
            if m.description:
                line += f"  # {m.description}"
            lines.append(line)
        for term, definition in self.glossary.items():
            lines.append(f"- {term}: {definition}")
        for alias, target in self.aliases.items():
            lines.append(f"- '{alias}' means '{target}'")
        return "\n".join(lines)
