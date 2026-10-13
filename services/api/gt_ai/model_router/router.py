"""AI Model Router (PDD §7).

Input signals: task, source/target language, domain, intent (latency /
quality / cost / private_only), GPU availability, provider capability
metadata, tenant preference, and rolling provider health.

Output: RouteDecision(provider, model, reason).

No model names are hardcoded in business logic — selection happens here
from capability metadata + configuration.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from gt_ai.capabilities import LanguageCapability
from gt_ai.types import Intent, ProviderHealth, RouteDecision, Task

log = logging.getLogger("gt_ai.router")

#: How long a tripped provider is left alone before it is probed again.
DEFAULT_BREAKER_COOLDOWN_S = 30.0
#: Ceiling on that, for a provider that is simply not on this machine.
DEFAULT_BREAKER_MAX_COOLDOWN_S = 600.0
DEFAULT_BREAKER_ERROR_RATE = 0.5
DEFAULT_BREAKER_MIN_REQUESTS = 4


@dataclass
class ProviderSpec:
    """Capability metadata for one candidate provider of a task."""
    name: str
    model: str = ""
    task: Task = Task.MT
    quality_tier: int = 50          # 0..100
    cost_tier: int = 50             # 0..100
    latency_class: str = "fast"     # realtime | fast | batch
    private: bool = True            # self-hosted / on-tenant inference
    requires_gpu: bool = False
    #: language coverage: None = all, else set of ISO codes supported
    languages: set[str] | None = None
    #: language pairs explicitly validated (src,tgt); empty = any supported pair
    validated_pairs: set[tuple[str, str]] = field(default_factory=set)
    domains: set[str] = field(default_factory=lambda: {"general"})
    priority: int = 100             # tenant/config preference, higher first


LATENCY_WEIGHTS = {"realtime": 1.0, "fast": 0.6, "batch": 0.2}


@dataclass
class _Breaker:
    """One tripped provider, and when it may be asked again.

    `level` counts re-trips, so a provider that is merely flaky is probed
    every cooldown while one that is simply absent from this host is probed
    progressively less often instead of forever.
    """
    until: float
    level: int = 0


class ModelRouter:
    def __init__(
        self,
        providers: dict[Task, list[ProviderSpec]],
        gpu_available: bool = False,
        health: dict[tuple[str, str], ProviderHealth] | None = None,
        breakers: dict[tuple[str, str], "_Breaker"] | None = None,
        *,
        breaker_error_rate: float = DEFAULT_BREAKER_ERROR_RATE,
        breaker_min_requests: int = DEFAULT_BREAKER_MIN_REQUESTS,
        breaker_cooldown_s: float = DEFAULT_BREAKER_COOLDOWN_S,
        breaker_max_cooldown_s: float = DEFAULT_BREAKER_MAX_COOLDOWN_S,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.providers = providers
        self.gpu_available = gpu_available
        self.health: dict[tuple[str, str], ProviderHealth] = health or {}
        self.breaker_error_rate = breaker_error_rate
        self.breaker_min_requests = breaker_min_requests
        self.breaker_cooldown_s = breaker_cooldown_s
        self.breaker_max_cooldown_s = breaker_max_cooldown_s
        #: Monotonic, injectable: a cooldown is tested by moving the clock, not
        #: by sleeping.
        self._clock = clock or time.monotonic
        self._breakers: dict[tuple[str, str], _Breaker] = breakers if breakers is not None else {}

    @property
    def breakers(self) -> dict[tuple[str, str], "_Breaker"]:
        """Open circuits, so a registry reload can carry them instead of
        forgetting which providers this host has already refused."""
        return self._breakers

    # ------------------------------------------------------------------ #
    # Circuit breaker
    # ------------------------------------------------------------------ #
    @staticmethod
    def _hkey(task: Task, provider: str) -> tuple[str, str]:
        return (task.value if isinstance(task, Task) else task, provider)

    def circuit_open(self, task: Task, provider: str) -> bool:
        """True while a tripped provider is in its cooldown.

        Callers that reach a provider outside `route()` — the streamed voice
        walk, the hardcoded fallbacks — ask this, because a breaker only pays
        for itself if every path honours it.
        """
        b = self._breakers.get(self._hkey(task, provider))
        return b is not None and self._clock() < b.until

    def trip(self, task: Task, provider: str, reason: str) -> None:
        """Stop offering this provider until its cooldown expires.

        Used for a refusal that needs no statistics: a voice whose package is
        not installed will not be installed by being asked again next turn, and
        asking it costs the turn the room is waiting on.
        """
        self._trip(task, provider, reason)

    def _window_expired(self, key: tuple[str, str]) -> bool:
        """True when this provider was let out of its cooldown, so whatever
        happens to it next is a recovery probe and its result decides the
        breaker — not the rolling error rate, which was zeroed at the trip."""
        b = self._breakers.get(key)
        return b is not None and self._clock() >= b.until

    def _trip(self, task: Task, provider: str, reason: str) -> None:
        key = self._hkey(task, provider)
        prev = self._breakers.get(key)
        level = prev.level + 1 if prev else 0
        cooldown = min(self.breaker_max_cooldown_s,
                       self.breaker_cooldown_s * (2 ** level))
        self._breakers[key] = _Breaker(until=self._clock() + cooldown, level=level)
        h = self.health.setdefault(key, ProviderHealth())
        h.available = False
        # A trip describes the calls that just happened. Left cumulative,
        # `error_rate` can never fall back under the re-close threshold, and
        # the provider is dead until the process restarts — which is a circuit
        # that never closes, not a breaker.
        h.request_count = 0
        h.error_count = 0
        log.warning("circuit open for %s/%s (%s); not offering it for %.0fs",
                    task, provider, reason, cooldown)

    # ------------------------------------------------------------------ #
    def route(
        self,
        task: Task,
        *,
        source_lang: str | None = None,
        target_lang: str | None = None,
        domain: str = "general",
        intent: Intent = Intent.QUALITY_OPTIMIZED,
        tenant_preference: str | None = None,
        language_capability: LanguageCapability | None = None,
        latency_budget_ms: float | None = None,
        exclude: frozenset[str] = frozenset(),
    ) -> RouteDecision:
        if not self.providers.get(task):
            raise KeyError(f"no providers configured for task={task}")
        # Excluded before every filter below, including the degrade chain: a
        # caller walking candidates in order asks for the best route that is not
        # one it already tried, and a fallback that quietly re-offers a tried
        # provider ends the walk instead.
        candidates = [p for p in self.providers[task] if p.name not in exclude]
        if not candidates:
            raise KeyError(f"no providers left for task={task} after exclusions")

        # hard filters ------------------------------------------------- #
        def keep(p: ProviderSpec) -> bool:
            if intent == Intent.PRIVATE_ONLY and not p.private:
                return False
            if p.requires_gpu and not self.gpu_available:
                return False
            for lang in (source_lang, target_lang):
                if lang and lang != "auto" and p.languages is not None and lang not in p.languages:
                    return False
            if (
                source_lang and target_lang
                and p.validated_pairs
                and (source_lang, target_lang) not in p.validated_pairs
            ):
                return False
            if domain != "general" and p.domains and domain not in p.domains:
                return False
            k = (task.value if isinstance(task, Task) else task, p.name)
            h = self.health.get(k)
            if h and not h.available:
                # Half-open: once the cooldown has passed the provider is
                # offered again, and the result of that call either closes the
                # circuit or re-opens it for longer. Before the cooldown it is
                # not touched at all — that untouched cost is the point.
                b = self._breakers.get(k)
                if b is None or self._clock() < b.until:
                    return False
            return True

        filtered = [p for p in candidates if keep(p)]
        if not filtered:
            # degrade: allow GPU-less fallback only for quality/cost intents
            filtered = [
                p for p in candidates
                if not (h := self.health.get((task.value if isinstance(task, Task) else task, p.name))) or h.available
            ]
        if not filtered:
            filtered = self._prefer_closed(
                task, [p for p in candidates
                       if not (intent == Intent.PRIVATE_ONLY and not p.private)])
        if not filtered:
            filtered = self._prefer_closed(task, candidates)

        # scoring -------------------------------------------------------#
        def score(p: ProviderSpec) -> float:
            s = 0.0
            if intent == Intent.QUALITY_OPTIMIZED:
                s += p.quality_tier * 1.0
                s += LATENCY_WEIGHTS.get(p.latency_class, 0.5) * 20
                s -= p.cost_tier * 0.1
            elif intent == Intent.LATENCY_OPTIMIZED:
                s += LATENCY_WEIGHTS.get(p.latency_class, 0.5) * 60
                s += p.quality_tier * 0.3
                if latency_budget_ms:
                    s -= max(0.0, (p.cost_tier - 50)) * 0.05
            elif intent == Intent.COST_OPTIMIZED:
                s -= p.cost_tier * 1.0
                s += p.quality_tier * 0.3
            else:  # PRIVATE_ONLY
                s += 40 if p.private else -1000
                s += p.quality_tier * 0.5
            # self-hosted preference (PDD §4: hybrid router, private core):
            # external providers are the escape hatch, not the default.
            if intent != Intent.PRIVATE_ONLY and p.private:
                s += 15
            # tenant preference boost
            if tenant_preference and p.name == tenant_preference:
                s += 25
            # per-language preferred provider boost
            if language_capability is not None:
                pref = {
                    Task.STT: language_capability.stt_provider,
                    Task.MT: language_capability.mt_provider,
                    Task.TTS: language_capability.tts_provider,
                }.get(task)
                if pref and p.name == pref:
                    s += 15
            # health penalty
            k = (task.value if isinstance(task, Task) else task, p.name)
            h = self.health.get(k)
            if h:
                s -= h.error_rate * 60
                if h.ewma_latency_ms and intent == Intent.LATENCY_OPTIMIZED:
                    s -= min(30, h.ewma_latency_ms / 100)
            s += p.priority * 0.05
            return s

        best = max(filtered, key=score)
        decision = RouteDecision(
            provider=best.name,
            model=best.model or best.name,
            task=task,
            reason=f"intent={intent.value} domain={domain} "
                   f"pair={source_lang}->{target_lang} quality={best.quality_tier} "
                   f"latency_class={best.latency_class} private={best.private}",
            latency_budget_ms=latency_budget_ms,
        )
        log.debug("route %s -> %s (%s)", task, best.name, decision.reason)
        return decision

    def _prefer_closed(self, task: Task, pool: list[ProviderSpec]) -> list[ProviderSpec]:
        """From a pool reached only because nothing else survived the filters,
        drop the providers still in their cooldown — unless that is the whole
        pool, because a possibly-dead provider still beats no route at all.
        """
        closed = [p for p in pool if not self.circuit_open(task, p.name)]
        return closed or pool

    # ------------------------------------------------------------------ #
    def record_outcome(self, task: Task, provider: str, latency_ms: float, ok: bool) -> None:
        """Feedback loop: EWMA latency + error rate used in future routing."""
        key = (task.value if isinstance(task, Task) else task, provider)
        h = self.health.setdefault(key, ProviderHealth())
        h.request_count += 1
        alpha = 0.2
        h.ewma_latency_ms = (1 - alpha) * h.ewma_latency_ms + alpha * latency_ms
        if not ok:
            h.error_count += 1
            # A call that was allowed out of its cooldown *is* the probe: it
            # gets one failure, not a quorum, before the circuit re-opens for
            # longer. Otherwise the room pays the full timeout of a dead
            # provider on every turn that the probe happens to land in.
            if self._window_expired(key) or (
                    h.error_rate > self.breaker_error_rate
                    and h.request_count >= self.breaker_min_requests):
                self._trip(task, provider, f"error_rate={h.error_rate:.2f}")
        else:
            if key in self._breakers:
                # The probe answered. Close the circuit: forget the backoff,
                # and let the next outage start from the short cooldown again.
                del self._breakers[key]
                h.available = True
                log.info("circuit closed for %s/%s", task, provider)
            elif not h.available and h.error_rate < 0.2:
                h.available = True

    def mark_available(self, task: Task, provider: str, available: bool) -> None:
        key = self._hkey(task, provider)
        h = self.health.setdefault(key, ProviderHealth())
        h.available = available
        h.request_count = 0
        h.error_count = 0
        if available:
            # An operator or a probe saying "it is back" outranks the breaker's
            # own opinion; it would otherwise sit out its remaining cooldown.
            self._breakers.pop(key, None)


def now_ms() -> float:
    return time.time() * 1000
