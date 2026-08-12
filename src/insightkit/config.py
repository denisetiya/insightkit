"""Configuration (pydantic-settings + YAML, env override via INSIGHTKIT_*)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DB_SCHEMES = {"postgresql", "mysql", "sqlite"}

_ENV_PREFIX = "INSIGHTKIT_"


def _env_overrides() -> dict:
    """Parse INSIGHTKIT_<SECTION>__<KEY> env vars into a nested dict (env wins over YAML)."""
    out: dict = {}
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        parts = key[len(_ENV_PREFIX) :].lower().split("__")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class DatabaseConfig(BaseModel):
    url: str = Field(..., description="SQLAlchemy async DSN, e.g. postgresql+psycopg://user:pass@host:5432/db")


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen2.5-coder"
    fast_model: str | None = None
    timeout_s: float = 60.0
    max_retries: int = 2


class SecurityConfig(BaseModel):
    row_limit: int = 10_000
    query_timeout_s: float = 30.0
    pii_mask: bool = True
    forbidden_tables: list[str] = Field(default_factory=list)


class PromptConfig(BaseModel):
    max_tokens: int = 3_000
    max_few_shots: int = 3
    max_tables: int = 200
    relevant_tables: int = 8  # filter schema ke N tabel relevan untuk prompt


class CacheConfig(BaseModel):
    ttl_s: int = 300


class InsightConfig(BaseModel):
    language: str = "en"

    @model_validator(mode="after")
    def _check_language(self) -> InsightConfig:
        if self.language not in {"en", "id"}:
            raise ValueError("insight.language must be 'en' or 'id'")
        return self


class APIConfig(BaseModel):
    jwt_secret: str = Field(default_factory=lambda: secrets.token_hex(32))
    jwt_expire_min: int = 60
    rate_limit_per_min: int = 60
    host: str = "0.0.0.0"
    port: int = 8000


class StorageConfig(BaseModel):
    path: Path = Path.home() / ".insightkit"
    meta_db: str = "meta.db"

    def ensure(self) -> Path:
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path / self.meta_db


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INSIGHTKIT_", env_nested_delimiter="__", extra="ignore"
    )

    database: DatabaseConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    insight: InsightConfig = Field(default_factory=InsightConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {p} (run 'insightkit init' first)")
        data = yaml.safe_load(p.read_text()) or {}
        data = _deep_merge(data, _env_overrides())  # env INSIGHTKIT_* wins
        return cls(**data)

    def to_yaml(self, path: str | Path) -> None:
        payload = self.model_dump(mode="json")
        Path(path).write_text(yaml.safe_dump(payload, sort_keys=False))
