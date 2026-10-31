"""OpenAI Agents SDK Acoustic Environment Intelligence and Advisory Agent."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import AudioChunk, AudioQualityMetrics

# Disable OpenAI cloud tracing export when using local Ollama or offline
try:
    set_tracing_disabled(True)
except Exception:
    pass

log = get_logger("acoustic_intelligence")


# --- Function Implementations for Acoustic Tools ---

def assess_acoustic_environment_fn(
    snr_db: float,
    clipping_ratio: float,
    noise_level_db: float,
    speech_duration_ms: int,
) -> str:
    """Evaluates acoustic telemetry and classifies room/microphone environment."""
    issues = []
    if clipping_ratio > 0.01:
        issues.append(f"Severe audio clipping ({clipping_ratio * 100:.1f}%) - microphone gain is too high.")
    if snr_db < 10.0:
        issues.append(f"Low SNR ({snr_db:.1f} dB) - heavy background ambient noise detected.")
    if noise_level_db > -30.0:
        issues.append(f"High background noise floor ({noise_level_db:.1f} dBFS).")
    if speech_duration_ms < 300:
        issues.append("Very short acoustic utterance burst.")

    if not issues:
        return "Acoustic environment is optimal. Good signal-to-noise ratio and clean voice envelope."
    return "Acoustic assessment: " + " ".join(issues)


def recommend_tuning_action_fn(
    current_status: str,
    issues_summary: str,
) -> str:
    """Formulates dynamic DSP tuning recommendations based on acoustic symptoms."""
    recommendations = []
    if "clipping" in issues_summary.lower():
        recommendations.append("Reduce microphone input gain or advise speaker to back away from microphone.")
    if "low snr" in issues_summary.lower() or "background noise" in issues_summary.lower():
        recommendations.append("Increase spectral noise suppression aggressiveness to preserve speech clarity.")
    if current_status == "poor":
        recommendations.append("Flag downstream STT for potential acoustic degradation and lower transcription confidence.")

    if not recommendations:
        return "No parameter adjustments required. Maintain current pipeline tuning."
    return "Recommended actions: " + "; ".join(recommendations)


def flag_segment_for_review_fn(
    segment_id: str,
    reason: str,
) -> str:
    """Flags a compromised audio segment for quality audit or supervisor review."""
    return f"Segment {segment_id} flagged for review: {reason}"


# OpenAI Agents SDK Function Tools
assess_acoustic_environment = function_tool(assess_acoustic_environment_fn)
recommend_tuning_action = function_tool(recommend_tuning_action_fn)
flag_segment_for_review = function_tool(flag_segment_for_review_fn)


class AcousticIntelligenceAgent:
    """AI Audio Intelligence Agent powered by OpenAI Agents SDK.
    
    Acts as a high-level acoustic intelligence and advisory agent outside the 50 ms audio loop.
    Decides whether audio quality is sufficient, diagnoses acoustic degradation, and suggests
    parameter tuning without introducing latency into the real-time streaming pipeline.
    """

    def __init__(self):
        self.enabled = settings.llm_agent.enabled
        self.model_name = settings.llm_agent.model
        self.base_url = settings.llm_agent.base_url
        self.api_key = settings.llm_agent.api_key
        self.agent: Optional[Agent] = None
        self._llm_available = False

        if self.enabled and settings.llm_agent.provider != "disabled":
            try:
                client = AsyncOpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    timeout=settings.llm_agent.timeout_seconds,
                )
                model_wrapper = OpenAIChatCompletionsModel(
                    model=self.model_name,
                    openai_client=client,
                )
                self.agent = Agent(
                    name="AudioIntelligenceAgent",
                    instructions=(
                        "You are the Audio Intelligence Agent for TalkFlow. Your responsibility is to analyze "
                        "acoustic telemetry (SNR, clipping, noise floor, speech envelope), diagnose audio problems, "
                        "and recommend intelligent pipeline adaptations to ensure high-quality speech translation. "
                        "Use your acoustic tools to evaluate metrics and recommend tuning actions."
                    ),
                    tools=[
                        assess_acoustic_environment,
                        recommend_tuning_action,
                        flag_segment_for_review,
                    ],
                    model=model_wrapper,
                )
                self._llm_available = True
                log.info(f"OpenAI Agents SDK Audio Intelligence Agent initialized with model: {self.model_name}")
            except Exception as e:
                log.warning(f"Could not initialize OpenAI Agents SDK client ({e}). Operating in deterministic heuristic mode.")
                self._llm_available = False

    async def analyze_segment(self, chunk: AudioChunk) -> Dict[str, Any]:
        """Analyzes a committed audio chunk. Executes out-of-band to guarantee 0 ms audio latency impact."""
        q = chunk.quality

        # Fast path if quality is already good and clean
        if q.quality_status == "good" and not q.issues:
            return {
                "agent": "audio_intelligence",
                "segment_id": chunk.segment_id,
                "acoustic_status": "optimal",
                "recommendation": "continue_current_tuning",
                "flagged_for_review": False,
                "provider": "fast_path",
            }

        # If LLM agent is available and segment has issues, invoke the OpenAI Agents SDK runner
        if self._llm_available and self.agent is not None:
            try:
                prompt = (
                    f"Evaluate audio segment {chunk.segment_id}. Telemetry:\n"
                    f"- SNR: {q.snr_db} dB\n"
                    f"- Clipping Ratio: {q.clipping_ratio * 100:.2f}%\n"
                    f"- RMS: {q.rms}\n"
                    f"- Peak: {q.peak}\n"
                    f"- Noise Floor: {q.noise_level_db} dBFS\n"
                    f"- Speech Duration: {q.speech_duration_ms} ms\n"
                    f"- Detected Issues: {', '.join(q.issues) if q.issues else 'None'}\n"
                    f"Provide an acoustic diagnosis and determine whether to recommend tuning or flag the segment."
                )
                result = await asyncio.wait_for(
                    Runner.run(self.agent, prompt),
                    timeout=settings.llm_agent.timeout_seconds,
                )
                output_text = str(result.final_output) if hasattr(result, "final_output") else "Analysis completed."
                log.info(f"Agent diagnostic for {chunk.segment_id}: {output_text[:120]}...")
                return {
                    "agent": "audio_intelligence",
                    "segment_id": chunk.segment_id,
                    "acoustic_status": q.quality_status,
                    "diagnosis": output_text,
                    "flagged_for_review": q.quality_status == "poor",
                    "provider": f"agent_sdk:{self.model_name}",
                }
            except Exception as exc:
                log.debug(f"LLM agent query skipped ({exc}), falling back to deterministic diagnostics.")

        # Deterministic Expert Heuristic Mode (Honest degradation fallback)
        diagnosis, should_flag = self._deterministic_diagnostics(chunk)
        return {
            "agent": "audio_intelligence",
            "segment_id": chunk.segment_id,
            "acoustic_status": q.quality_status,
            "diagnosis": diagnosis,
            "flagged_for_review": should_flag,
            "provider": "deterministic_heuristics",
        }

    def _deterministic_diagnostics(self, chunk: AudioChunk) -> tuple[str, bool]:
        q = chunk.quality
        recs = []
        should_flag = False

        if q.clipping_ratio > 0.01:
            recs.append("Input microphone gain exceeds safe range; clipping detected.")
            should_flag = True
        if q.snr_db < 10.0:
            recs.append("High ambient noise floor; increased spectral attenuation advised.")
        if q.quality_status == "poor":
            should_flag = True
            recs.append("Quality status poor; advise downstream STT to apply fallback confidence.")

        diag = " ".join(recs) if recs else "Acoustic metrics within acceptable operating thresholds."
        return diag, should_flag
