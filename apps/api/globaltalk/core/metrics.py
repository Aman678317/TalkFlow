"""Prometheus-style metrics registry (exposed at /metrics). Zero-dependency implementation."""
from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self.hist: dict[tuple[str, tuple], list[float]] = defaultdict(list)
        self.gauges: dict[tuple[str, tuple], float] = {}

    def inc(self, name: str, labels: dict | None = None, value: float = 1) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self.counters[key] += value

    def observe(self, name: str, value: float, labels: dict | None = None) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            bucket = self.hist[key]
            bucket.append(value)
            if len(bucket) > 2000:
                del bucket[:1000]

    def gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        with self._lock:
            self.gauges[(name, tuple(sorted((labels or {}).items())))] = value

    # convenience wrappers used across the app
    def observe_request(self, path: str, status: int, duration_s: float) -> None:
        route = path.split("?")[0]
        if route.startswith("/ws"):
            route = "/ws"
        self.inc("http_requests_total", {"route": route, "status": str(status)})
        self.observe("http_request_duration_seconds", duration_s, {"route": route})

    def observe_translation(self, provider: str, pair: str, ms: float) -> None:
        self.observe("translation_latency_ms", ms, {"provider": provider, "pair": pair})
        self.inc("translations_total", {"provider": provider, "pair": pair})

    def observe_stt(self, provider: str, lang: str, ms: float) -> None:
        self.observe("stt_latency_ms", ms, {"provider": provider, "lang": lang})

    def observe_tts(self, provider: str, lang: str, ms: float) -> None:
        self.observe("tts_latency_ms", ms, {"provider": provider, "lang": lang})

    def observe_e2e(self, pair: str, ms: float) -> None:
        self.observe("realtime_e2e_latency_ms", ms, {"pair": pair})

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), v in sorted(self.counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{{{_fmt(labels)}}} {v}")
            for (name, labels), v in sorted(self.gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{{{_fmt(labels)}}} {v}")
            for (name, labels), vals in sorted(self.hist.items()):
                if not vals:
                    continue
                s = sorted(vals)
                n = len(s)

                def q(p: float) -> float:
                    return s[min(n - 1, int(p * n))]
                lines.append(f"# TYPE {name} summary")
                lines.append(f'{name}{{quantile="0.5",{_fmt(labels)}}} {q(0.5):.3f}')
                lines.append(f'{name}{{quantile="0.95",{_fmt(labels)}}} {q(0.95):.3f}')
                lines.append(f'{name}{{quantile="0.99",{_fmt(labels)}}} {q(0.99):.3f}')
                lines.append(f"{name}_count{{{_fmt(labels)}}} {n}")
                lines.append(f"{name}_sum{{{_fmt(labels)}}} {sum(s):.3f}")
        return "\n".join(lines) + "\n"


def _fmt(labels: tuple) -> str:
    return ",".join(f'{k}="{v}"' for k, v in labels)


metrics = Metrics()
