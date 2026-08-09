"""InsightKit CLI — init / ask / serve / refresh / eval / golden / semantic / user."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from insightkit.config import Config
from insightkit.eval import load_golden, run_eval
from insightkit.pipeline import InsightKit
from insightkit.semantic import SemanticLayer

app = typer.Typer(
    help="InsightKit — enterprise text-to-SQL analytics (on-prem).", no_args_is_help=True
)

DEFAULT_CONFIG = "insightkit.yml"
DEFAULT_GOLDEN = "golden.yml"


def load_config(path: str) -> Config:
    return Config.from_yaml(path)


def _run(coro):
    return asyncio.run(coro)


@app.command()
def example_config(
    output: Path = typer.Option(
        Path(DEFAULT_CONFIG), "--output", "-o", help="Where to write the template"
    ),
) -> None:
    """Write a config template to start from."""
    template = {
        "database": {"url": "postgresql+psycopg://user:pass@localhost:5432/mydb"},
        "llm": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "model": "qwen2.5-coder",
            "fast_model": None,
        },
        "security": {"row_limit": 10000, "query_timeout_s": 30, "forbidden_tables": []},
        "insight": {"language": "en"},
        "cache": {"ttl_s": 300},
        "api": {"jwt_secret": "change-me-in-production", "rate_limit_per_min": 60},
    }
    output.write_text(json.dumps(template, indent=2) + "\n")
    typer.echo(f"Config template written to {output}")


@app.command()
def init(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    semantic: Path | None = typer.Option(None, "--semantic", help="semantic.yml path"),
    create_admin: str | None = typer.Option(
        None, "--create-admin", help="username for the admin user"
    ),
) -> None:
    """Connect to the DB, introspect + cache the schema, ready the meta store."""
    cfg = load_config(config)
    sem = SemanticLayer.load(semantic)
    kit = InsightKit(cfg, semantic=sem)

    async def _init() -> None:
        api_key = await kit.init(create_admin=create_admin)
        await kit.close()
        return api_key

    api_key = _run(_init())
    typer.echo(f"Connected OK — schema cached (db_key={kit.db_key})")
    if api_key:
        typer.echo(f"Admin user '{create_admin}' created. API key (show once): {api_key}")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language question"),
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    semantic: Path | None = typer.Option(None, "--semantic"),
    user: str = typer.Option("cli", "--user", "-u"),
    role: str = typer.Option("analyst", "--role", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """Ask a question in natural language; get an insight."""
    cfg = load_config(config)
    sem = SemanticLayer.load(semantic)
    kit = InsightKit(cfg, semantic=sem)

    async def _ask() -> None:
        result = await kit.ask(question, user=user, role=role)
        await kit.close()
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "question": result.question,
                        "sql": result.sql,
                        "insight": result.insight,
                        "chart": result.chart,
                        "status": result.status,
                        "error": result.error,
                        "latency_ms": result.latency_ms,
                        "tokens": result.tokens,
                        "model": result.model,
                        "cached": result.cached,
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"SQL: {result.sql}")
            typer.echo("")
            typer.echo(result.insight)
            typer.echo("")
            typer.echo(
                f"[{result.status}] {result.latency_ms}ms, {result.tokens} tokens, "
                f"model={result.model}" + (" (cached)" if result.cached else "")
            )

    _run(_ask())


@app.command()
def refresh(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Re-introspect the database schema."""
    cfg = load_config(config)
    kit = InsightKit(cfg)

    async def _refresh() -> None:
        await kit.refresh_schema()
        await kit.close()

    _run(_refresh())
    typer.echo("Schema refreshed")


@app.command()
def serve(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    semantic: Path | None = typer.Option(None, "--semantic"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
) -> None:
    """Start the REST API server (FastAPI + SSE)."""
    from insightkit.api.app import run_server

    cfg = load_config(config)
    run_server(cfg, semantic_path=semantic, host=host, port=port)


@app.command()
def eval(
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
    golden: Path = typer.Option(Path(DEFAULT_GOLDEN), "--golden", "-g"),
    threshold: float = typer.Option(0.9, "--threshold"),
    semantic: Path | None = typer.Option(None, "--semantic"),
) -> None:
    """Run the golden-set evaluation; exit non-zero below threshold (CI gate)."""
    cfg = load_config(config)
    cases = load_golden(golden)
    result = _run(run_eval(cfg, cases, client=None))

    for failure in result.failures:
        typer.echo(f"FAIL {failure['question']}: {failure['reason']}")
    typer.echo(f"Score: {result.score:.0%} ({result.correct}/{result.total})")
    if result.score < threshold:
        raise typer.Exit(code=1)


@app.command()
def golden(
    golden: Path = typer.Option(Path(DEFAULT_GOLDEN), "--golden", "-g"),
) -> None:
    """Validate and preview a golden-set file."""
    cases = load_golden(golden)
    typer.echo(f"Golden set: {len(cases)} cases")
    for case in cases:
        expected = case.sql_expected or case.result_keywords or "(status ok)"
        typer.echo(f"  - {case.question}  →  {expected}")


@app.command()
def semantic(
    path: Path = typer.Argument(..., help="semantic.yml path"),
) -> None:
    """Validate and preview a semantic-layer file."""
    sem = SemanticLayer.load(path)
    typer.echo(
        f"Metrics: {len(sem.metrics)}, glossary: {len(sem.glossary)}, "
        f"aliases: {len(sem.aliases)}"
    )
    rendered = sem.render()
    if rendered:
        typer.echo(rendered)


@app.command()
def user(
    action: str = typer.Argument(..., help="create | delete | list"),
    username: str | None = typer.Option(None, "--username"),
    role: str = typer.Option("analyst", "--role"),
    config: str = typer.Option(DEFAULT_CONFIG, "--config", "-c"),
) -> None:
    """Manage API users (create shows the API key once)."""
    cfg = load_config(config)
    from insightkit.security.users import UserStore

    store = UserStore(cfg)

    async def _run_action() -> None:
        if action == "create":
            if not username:
                raise typer.BadParameter("--username required for create")
            key = await store.create(username, role)
            typer.echo(f"User '{username}' ({role}) created. API key: {key}")
        elif action == "delete":
            if not username:
                raise typer.BadParameter("--username required for delete")
            ok = await store.delete(username)
            typer.echo("Deleted" if ok else "User not found")
        elif action == "list":
            for u in await store.list_users():
                typer.echo(f"{u['username']}\t{u['role']}\t{u['created_at']}")
        else:
            raise typer.BadParameter("action must be create | delete | list")

    _run(_run_action())


if __name__ == "__main__":
    app()
