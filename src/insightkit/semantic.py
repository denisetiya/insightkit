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
        try:
            data = yaml.safe_load(p.read_text())
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid semantic YAML {p}: {exc}") from exc
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"Invalid semantic file {p}: top level must be a mapping")
        try:
            return cls(**data)
        except Exception as exc:
            raise ValueError(f"Invalid semantic file {p}: {exc}") from exc

    def render(self, max_chars: int = 4000) -> str:
        """Text injected into the prompt (METRIC DEFINITIONS section)."""
        lines: list[str] = []
        for m in self.metrics:
            name = m.name.strip()
            definition = m.definition.strip()
            if not name or not definition:
                continue
            line = f"- {name} = {definition}"
            if m.description.strip():
                line += f"  # {m.description.strip()}"
            lines.append(line)
        for term, definition in sorted(self.glossary.items()):
            term = term.strip()
            text = definition.strip() if isinstance(definition, str) else str(definition)
            if term and text:
                lines.append(f"- {term}: {text}")
        for alias, target in sorted(self.aliases.items()):
            alias = alias.strip()
            target = target.strip() if isinstance(target, str) else str(target)
            if alias and target:
                lines.append(f"- '{alias}' means '{target}'")
        rendered = "\n".join(lines)
        if len(rendered) > max_chars:
            return rendered[:max_chars]
        return rendered
