"""Text language ID: langid (pure-python statistical) + script heuristic fusion."""
from __future__ import annotations

from ai.interfaces import DetectionResult
from ai.providers.fallback import ScriptHeuristicLangID

_script = ScriptHeuristicLangID()


class LangIdDetector:
    name = "langid"

    def healthy(self) -> bool:
        try:
            import langid  # noqa: F401
            return True
        except ImportError:
            try:
                import importlib.util
                return importlib.util.find_spec("langdetect") is not None
            except Exception:
                return False

    def detect(self, text: str) -> DetectionResult:
        # Non-Latin scripts: script heuristic is more reliable than statistical langid.
        script_result = _script.detect(text)
        if script_result.confidence >= 0.6:
            return script_result
        try:
            import langid
            import math
            lang, score = langid.classify(text)
            ranking = langid.rank(text)
            # score is a log-probability; normalize with a softmax over the ranking window.
            scores = [s for _, s in ranking[:4]]
            m = max(scores) if scores else 0.0
            exps = [math.exp(s - m) for s in scores]
            conf = exps[0] / sum(exps) if exps else 0.0
            alts = [(l, math.exp(s - m) / sum(exps)) for (l, s) in ranking[:4]] if exps else []
            return DetectionResult(language=lang, confidence=round(min(conf, 0.99), 4),
                                   provider=self.name, alternatives=alts)
        except ImportError:
            try:
                import importlib
                langdetect = importlib.import_module("langdetect")
                probs = langdetect.detect_langs(text)
                if probs:
                    best = probs[0]
                    alts = [(p.lang, round(p.prob, 4)) for p in probs]
                    return DetectionResult(language=best.lang, confidence=round(best.prob, 4),
                                           provider=self.name, alternatives=alts)
            except Exception:
                pass
            return script_result if script_result.confidence > 0 else DetectionResult(
                language="en", confidence=0.1, provider=self.name)
        except Exception:
            return script_result if script_result.confidence > 0 else DetectionResult(
                language="en", confidence=0.1, provider=self.name)
