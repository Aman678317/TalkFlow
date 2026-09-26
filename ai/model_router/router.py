"""Model Router (sections 7/79). Selects provider/model per task from capability metadata +
health + intent, with an ordered fallback chain. No model names are hardcoded in business
logic — everything flows through this router and the DB-backed registry.

Intents: quality_optimized | latency_optimized | cost_optimized | private_only |
         offline_only | experimental
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ai.interfaces import ProviderUnavailable
from globaltalk.core.logging import get_logger

log = get_logger("router")


@dataclass
class RouteRequest:
    task: str                        # stt | mt | tts | vad | llm | embedding | langid
    source_language: str = ""
    target_language: str = ""
    domain: str = "general"
    intent: str = "quality_optimized"
    latency_target_ms: float | None = None
    require_gpu: bool | None = None  # None = don't care
    private_only: bool = False
    tenant_policy: dict = field(default_factory=dict)
    feature_flags: dict = field(default_factory=dict)


@dataclass
class Route:
    provider_name: str
    provider: object
    model: str = ""
    version: str = ""
    reason: str = ""
    fallbacks: list["Route"] = field(default_factory=list)


class ModelRouter:
    """Holds live provider instances; consults each provider's real capability report."""

    def __init__(self):
        self._providers: dict[str, dict[str, object]] = {}  # task -> name -> instance
        self._health: dict[str, bool] = {}

    def register(self, task: str, name: str, provider, *, priority: int = 100) -> None:
        self._providers.setdefault(task, {})[name] = provider
        self._priority = getattr(self, "_priority", {})
        self._priority[(task, name)] = priority

    def health(self, task: str, name: str) -> bool:
        key = f"{task}:{name}"
        if key not in self._health:
            p = self._providers.get(task, {}).get(name)
            try:
                self._health[key] = bool(p and p.healthy())
            except Exception:
                self._health[key] = False
        return self._health[key]

    def invalidate_health(self) -> None:
        self._health.clear()

    def _candidates(self, req: RouteRequest) -> list[object]:
        providers = self._providers.get(req.task, {})
        cands = []
        for name, p in providers.items():
            if not self.health(req.task, name):
                continue
            if req.task == "mt":
                src, tgt = req.source_language.split("-")[0], req.target_language.split("-")[0]
                pairs = p.supported_pairs() if hasattr(p, "supported_pairs") else set()
                # passthrough claims no pairs — kept only as explicit last resort
                if pairs and (src, tgt) not in pairs and src != tgt:
                    # allow pivot only when policy permits and intent is not premium-latency
                    allow_pivot = req.tenant_policy.get("allow_pivot_translation", True)
                    if not allow_pivot:
                        continue
            if req.task in ("stt", "tts", "langid"):
                langs = p.supported_languages() if hasattr(p, "supported_languages") else set()
                probe = req.source_language or req.target_language
                if langs and probe and probe.split("-")[0] not in langs:
                    continue
            cands.append(p)

        def sort_key(p):
            prio = self._priority.get((req.task, getattr(p, "name", "")), 100)
            if req.intent == "latency_optimized":
                prio -= 10 if getattr(p, "name", "") in ("faster-whisper", "argos", "kokoro") else 0
            if req.intent == "quality_optimized":
                prio -= 10 if getattr(p, "name", "") in ("vllm", "indicconformer") else 0
            return prio

        return sorted(cands, key=sort_key)

    def route(self, req: RouteRequest) -> Route | None:
        cands = self._candidates(req)
        if not cands:
            return None
        primary, *rest = cands
        route = Route(provider_name=getattr(primary, "name", "?"), provider=primary,
                      reason=f"intent={req.intent};healthy={len(cands)}")
        route.fallbacks = [
            Route(provider_name=getattr(p, "name", "?"), provider=p, reason="fallback")
            for p in rest
        ]
        log.info("route_selected", extra={"task": req.task, "provider": route.provider_name,
                                          "pair": f"{req.source_language}->{req.target_language}",
                                          "intent": req.intent,
                                          "fallbacks": [f.provider_name for f in route.fallbacks]})
        return route

    def execute(self, req: RouteRequest, call, *args, **kwargs):
        """Run `call(provider, *args)` down the fallback chain.

        Returns (result, route_used). Raises ProviderUnavailable when every candidate failed —
        callers then apply their domain-specific final fallback (captions-only, passthrough…).
        """
        # ensure memory headroom BEFORE routing: health probes may load models
        try:
            from ai.memory_guard import ensure_headroom
            ensure_headroom(req.task)
        except Exception:
            pass
        route = self.route(req)
        if route is None:
            raise ProviderUnavailable(req.task, "no healthy provider registered")
        errors = []
        for cand in [route, *route.fallbacks]:
            try:
                result = call(cand.provider, *args, **kwargs)
                return result, cand
            except ProviderUnavailable as exc:
                errors.append(f"{cand.provider_name}: {exc.reason}")
                # NOTE: ProviderUnavailable is REQUEST-level (e.g. pair not covered) —
                # it must not blacklist the provider process-wide.
                log.warning("route_fallback", extra={"task": req.task,
                                                     "failed": cand.provider_name,
                                                     "reason": exc.reason})
            except Exception as exc:
                errors.append(f"{cand.provider_name}: {type(exc).__name__}: {exc}")
                log.exception("route_provider_error", extra={"task": req.task,
                                                             "provider": cand.provider_name})
        raise ProviderUnavailable(req.task, " | ".join(errors))
