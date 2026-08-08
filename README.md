# InsightKit

Enterprise-grade, on-prem text-to-SQL analytics library (Python).

Natural language → SQL → insight. Installed inside your infrastructure; connects to your database (read-only); audit, guardrails, and RBAC built in.

> **Status:** MVP in development. PRD: `docs/PRD.md`.

## Quick start (planned)

```bash
pip install insightkit
insightkit init    # config: DB DSN + LLM (self-host default: Ollama/vLLM)
insightkit ask "What was total revenue last month?"
```

## License

Apache-2.0
