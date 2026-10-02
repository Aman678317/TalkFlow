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
from dataclasses import dataclass, field

from gt_ai.capabilities import LanguageCapability
from gt_ai.types import Intent, ProviderHealth, RouteDecision, Task

log = logging.getLogger("gt_ai.router")


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


class ModelRouter:
    def __init__(
        self,
        providers: dict[Task, list[ProviderSpec]],
        gpu_available: bool = False,
        health: dict[tuple[str, str], ProviderHealth] | None = None,
    ) -> None:
        self.providers = providers
        self.gpu_available = gpu_available
        self.health: dict[tuple[str, str], ProviderHealth] = health or {}

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
    ) -> RouteDecision:
        candidates = list(self.providers.get(task, []))
        if not candidates:
            raise KeyError(f"no providers configured for task={task}")

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
            filtered = [
                p for p in candidates
                if not (intent == Intent.PRIVATE_ONLY and not p.private)
            ]
        if not filtered:
            filtered = candidates

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
            if h.error_rate > 0.5 and h.request_count >= 4:
                h.available = False
                log.warning("provider %s/%s marked unhealthy (error_rate=%.2f)", task, provider, h.error_rate)
        else:
            if not h.available and h.error_rate < 0.2:
                h.available = True

    def mark_available(self, task: Task, provider: str, available: bool) -> None:
        key = (task.value if isinstance(task, Task) else task, provider)
        h = self.health.setdefault(key, ProviderHealth())
        h.available = available
        h.request_count = 0
        h.error_count = 0


def now_ms() -> float:
    return time.time() * 1000
