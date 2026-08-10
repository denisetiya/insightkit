# InsightKit

Enterprise-grade, on-prem text-to-SQL analytics library (Python).

Natural language → SQL → insight. Installed inside your infrastructure; connects to your database (read-only); audit, guardrails, and RBAC built in.

> **Status:** MVP v0.1.0. PRD: `docs/PRD.md` · Full docs: [docs/index.md](docs/index.md)

## Quick start

```bash
pip install insightkit
insightkit example-config -o insightkit.yml   # edit DSN + LLM
insightkit init -c insightkit.yml --create-admin admin
insightkit ask "berapa total revenue bulan lalu?" -c insightkit.yml
```

Or run the API server: `insightkit serve -c insightkit.yml` → `POST /api/v1/ask` (SSE).

## Docs

- [Install & deploy](docs/install.md) — pip / Docker / on-prem / air-gapped
- [Config](docs/config.md) — YAML + env reference
- [CLI](docs/cli.md) — all commands
- [API](docs/api.md) — per-endpoint, curl + TypeScript examples
- [Security](docs/security.md) — guardrails, RBAC, audit, PII
- [Eval](docs/eval.md) — golden set regression gate

## License

Apache-2.0
