"""In-memory request metrics — latency percentiles, token spend, cache hit rate."""

from __future__ import annotations

import statistics
from collections import deque
from datetime import UTC, datetime


class Metrics:
    def __init__(self, max_samples: int = 500) -> None:
        self.latencies: deque[int] = deque(maxlen=max_samples)
        self.tokens_total = 0
        self.requests = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.errors = 0
        self.started_at = datetime.now(UTC)

    def record(self, latency_ms: int, tokens: int, cached: bool, ok: bool) -> None:
        self.latencies.append(latency_ms)
        self.tokens_total += tokens
        self.requests += 1
        if cached:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        if not ok:
            self.errors += 1

    def snapshot(self) -> dict:
        lats = sorted(self.latencies)
        total = len(lats)
        p50 = lats[int(total * 0.5)] if total else 0
        p95 = lats[min(int(total * 0.95), total - 1)] if total else 0
        cache_total = self.cache_hits + self.cache_misses
        return {
            "requests": self.requests,
            "errors": self.errors,
            "latency_ms": {
                "p50": p50,
                "p95": p95,
                "mean": round(statistics.mean(lats), 1) if total else 0,
            },
            "tokens_total": self.tokens_total,
            "cache_hit_rate": round(self.cache_hits / cache_total, 3) if cache_total else 0.0,
            "uptime_s": round((datetime.now(UTC) - self.started_at).total_seconds()),
        }
