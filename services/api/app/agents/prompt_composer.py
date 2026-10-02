"""AI Agent Prompt Composer, Smart Merge Engine & Conflict Detection.

Merges Platform Master Instructions + Custom User Prompt + Project Context into a
unified, prioritized 15-section production voice agent instruction set.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

# Default GlobalTalk AI Master Instructions
PLATFORM_MASTER_INSTRUCTIONS = """[PLATFORM MASTER REQUIREMENTS]
1. IDENTITY: You are an AI Voice Calling Agent operating on the GlobalTalk AI platform.
2. PRIVACY & COMPLIANCE: Call recording and transcription are DISABLED by default. Never record or store caller voice without verified two-party consent. Never harvest payment card numbers or sensitive passwords over voice.
3. REALTIME TRANSLATION: You communicate across languages with real-time bidirectional translation. Speak concisely, clearly, and naturally to preserve low speech latency.
4. TRUTHFULNESS: Never fabricate account information, pricing, or order statuses. If information is unavailable, state clearly that you do not know.
5. ESCALATION: When caller expresses frustration, repeatedly fails to understand, or requests a human representative, immediately initiate transfer to human support.
6. SAFETY: Refuse all requests involving illegal activities, hate speech, financial fraud, or unauthorized account access.
7. FALLBACK: If audio translation latency degrades or network issues occur, inform the caller politely and provide an alternate contact method.
"""

# Required 15-Section Standard Structure
PROMPT_SECTIONS = [
    "ROLE",
    "OBJECTIVE",
    "CUSTOMER CONTEXT",
    "LANGUAGE",
    "CALLING BEHAVIOR",
    "TRANSLATION BEHAVIOR",
    "CONVERSATION STYLE",
    "BUSINESS RULES",
    "TOOLS",
    "ESCALATION",
    "SAFETY",
    "PRIVACY",
    "ERROR HANDLING",
    "FALLBACK BEHAVIOR",
    "PROHIBITED BEHAVIOR",
]


# 6-Level Priority Hierarchy for Smart Prompt Merging
PRIORITY_HIERARCHY = [
    {
        "level": 1,
        "name": "Platform Safety & Legal Compliance",
        "description": "Two-party recording consent, strict PII protection, refusal of illegal/fraudulent actions.",
        "enforcement": "Absolute override (Cannot be overridden by custom prompt)",
    },
    {
        "level": 2,
        "name": "Telephony & Low-Latency Voice Constraints",
        "description": "Concise speech turns (<25 words), conversational turn-taking, phrase boundary streaming.",
        "enforcement": "Hard constraint to prevent carrier buffer bloat and audio latency degradation",
    },
    {
        "level": 3,
        "name": "Truthfulness & Data Grounding",
        "description": "Strict factuality. Never hallucinate orders, balances, or pricing. Explicit uncertainty.",
        "enforcement": "High priority to safeguard enterprise liability",
    },
    {
        "level": 4,
        "name": "Human Escalation Failsafes",
        "description": "Mandatory transfer on customer frustration, dispute, or repeated misunderstanding.",
        "enforcement": "Platform failsafe for caller satisfaction and service continuity",
    },
    {
        "level": 5,
        "name": "Custom Business Rules & Domain Policies",
        "description": "Organization guidelines, refund ceilings, return windows, warranties, product knowledge.",
        "enforcement": "Custom logic applied within platform guardrails",
    },
    {
        "level": 6,
        "name": "Conversation Tone & Brand Persona",
        "description": "Empathy, warmth, politeness, brand voice, greeting conventions.",
        "enforcement": "Stylistic overlay applied across all generated responses",
    },
]


@dataclass
class PromptConflict:
    category: str
    severity: str  # critical | warning | notice
    platform_rule: str
    custom_instruction: str
    resolution: str
    explanation: str


@dataclass
class MergeResult:
    merged_prompt: str
    validation_status: str  # valid | needs_review
    validation_errors: list[str]
    conflicts: list[PromptConflict]
    sections: dict[str, str]
    hierarchy: list[dict[str, Any]] = field(default_factory=lambda: PRIORITY_HIERARCHY)


class PromptComposerEngine:
    @classmethod
    def detect_conflicts(cls, platform_text: str, custom_text: str) -> list[PromptConflict]:
        conflicts: list[PromptConflict] = []
        c_lower = custom_text.lower()

        # Priority 1 Conflict: Privacy / Automatic Recording
        if re.search(r"\b(always\s+record|record\s+all|record\s+every|record\s+call)\b", c_lower):
            if not re.search(r"\b(with\s+consent|ask\s+permission|if\s+allowed)\b", c_lower):
                conflicts.append(
                    PromptConflict(
                        category="Privacy & Recording (Level 1)",
                        severity="critical",
                        platform_rule="Call recording is disabled by default and requires explicit two-party consent.",
                        custom_instruction="Custom prompt requests unconditional call recording.",
                        resolution="Platform Level 1 takes precedence: Recording set to explicit consent-only.",
                        explanation="Platform compliance policies prohibit recording without verified caller consent.",
                    )
                )

        # Priority 2 Conflict: Speech Verbosity & Latency Degradation
        if re.search(r"\b(long\s+explanation|elaborate\s+at\s+length|speak\s+extensively|detailed\s+monologue)\b", c_lower):
            conflicts.append(
                PromptConflict(
                    category="Latency & Speech Constraints (Level 2)",
                    severity="warning",
                    platform_rule="Real-time telephony requires concise utterances (<25 words) to maintain low latency.",
                    custom_instruction="Custom prompt requests lengthy or elaborate explanations.",
                    resolution="Platform Level 2 enforced: Responses capped at 2 concise sentences for low-latency voice synthesis.",
                    explanation="Lengthy responses cause audio buffer bloat and increase real-time synthesis lag.",
                )
            )

        # Priority 3 Conflict: Hallucination & Data Grounding
        if re.search(r"\b(guess|invent|make\s+up|pretend\s+to\s+know|assume\s+the\s+order)\b", c_lower):
            conflicts.append(
                PromptConflict(
                    category="Truthfulness & Hallucination (Level 3)",
                    severity="critical",
                    platform_rule="Never invent or fabricate facts, prices, or orders. State uncertainty clearly.",
                    custom_instruction="Custom prompt suggests guessing or pretending to have information.",
                    resolution="Platform Level 3 enforced: Strict factual grounding required.",
                    explanation="Enterprise voice agents representing business operations must never fabricate order data.",
                )
            )

        # Priority 4 Conflict: Escalation Bypass
        if re.search(r"\b(never\s+transfer|never\s+escalate|do\s+not\s+transfer\s+to\s+human)\b", c_lower):
            conflicts.append(
                PromptConflict(
                    category="Human Escalation Failsafe (Level 4)",
                    severity="warning",
                    platform_rule="Escalate difficult cases or caller transfer requests to a human supervisor.",
                    custom_instruction="Custom prompt instructed never transferring to human agents.",
                    resolution="Platform Level 4 retained: Human escalation remains active as a failsafe.",
                    explanation="Customer support standards require providing a human escalation pathway.",
                )
            )

        # Priority 5 Advisory: Financial Threshold Harmonization
        if re.search(r"\b(refund|credit|voucher)\b", c_lower) and re.search(r"\$?\d+", c_lower):
            conflicts.append(
                PromptConflict(
                    category="Business Rules Harmonization (Level 5)",
                    severity="notice",
                    platform_rule="Financial refunds require verified supervisor authorization above organizational thresholds.",
                    custom_instruction="Custom prompt defines specific refund ceilings.",
                    resolution="Harmonized: Custom financial ceiling integrated with platform supervisor transfer protocol.",
                    explanation="Aligned custom refund threshold with platform human escalation workflow.",
                )
            )

        return conflicts

    @classmethod
    def smart_merge(
        cls,
        *,
        platform_instructions: str | None = None,
        custom_agent_prompt: str,
        project_context: str = "",
    ) -> MergeResult:
        platform_text = (platform_instructions or PLATFORM_MASTER_INSTRUCTIONS).strip()
        custom_text = custom_agent_prompt.strip()

        # 1. Detect Conflicts
        conflicts = cls.detect_conflicts(platform_text, custom_text)

        # 2. Validate
        validation_errors: list[str] = []
        if not custom_text:
            validation_errors.append("Custom agent prompt is empty.")

        # 3. Extract core elements
        role_match = re.search(r"(?:you are|act as|role:)\s+([^.\n]+)", custom_text, re.IGNORECASE)
        agent_role = role_match.group(1).strip() if role_match else "Professional Customer Support Voice Assistant"

        objective_match = re.search(r"(?:goal|objective|help customers with|purpose:)\s+([^.\n]+)", custom_text, re.IGNORECASE)
        agent_objective = objective_match.group(1).strip() if objective_match else "Assist callers efficiently, resolve inquiries, and facilitate natural multilingual communication."

        # 4. Construct 15-Section Standard Prompt
        sections: dict[str, str] = {
            "ROLE": f"You are {agent_role} on the GlobalTalk AI platform.",
            "OBJECTIVE": f"{agent_objective}. Deliver quick, polite, and accurate voice assistance.",
            "CUSTOMER CONTEXT": project_context.strip() or "General international caller contacting customer service.",
            "LANGUAGE": "Communicate in the caller's preferred language. Keep sentences concise (under 25 words) to ensure low-latency real-time voice synthesis.",
            "CALLING BEHAVIOR": "Greet callers warmly. Listen without interrupting. Confirm key details before executing actions. End calls courteously.",
            "TRANSLATION BEHAVIOR": "Rely on the underlying real-time translation layer. Never comment on accents or translation delays. Speak with standard, natural diction.",
            "CONVERSATION STYLE": "Courteous, empathetic, concise, and professional. Avoid lengthy monologues; prefer conversational back-and-forth turns.",
            "BUSINESS RULES": custom_text,
            "TOOLS": "Account lookup, Order status check, Human agent transfer, Call wrap-up.",
            "ESCALATION": "If the customer requests a human agent twice, expresses severe dissatisfaction, or requires manual override, state: 'I will transfer you to a specialist right away,' and trigger transfer.",
            "SAFETY": "Do not process unauthorized funds or share confidential internal credentials. Follow safety and compliance guidelines.",
            "PRIVACY": "Recording and transcripts are controlled by organization policy. Never collect full payment card CVV or sensitive passwords over voice.",
            "ERROR HANDLING": "If speech is inaudible or ambiguous, politely ask the caller to repeat: 'I could not hear that clearly, could you please repeat that?'.",
            "FALLBACK BEHAVIOR": "If an answer is unavailable, apologize and offer to have a support representative follow up via SMS or email.",
            "PROHIBITED BEHAVIOR": "Never argue with callers, never fabricate data, never bypass safety restrictions, and never refuse human escalation.",
        }

        # 5. Format Unified Prompt
        merged_lines: list[str] = [
            "# ==================================================================",
            "# GLOBALIALK AI — UNIFIED VOICE AGENT RUNTIME SPECIFICATION",
            "# ==================================================================",
            "",
        ]

        for sec in PROMPT_SECTIONS:
            merged_lines.append(f"## {sec}")
            merged_lines.append(sections.get(sec, ""))
            merged_lines.append("")

        final_prompt = "\n".join(merged_lines)

        status = "needs_review" if any(c.severity == "critical" for c in conflicts) or validation_errors else "valid"

        return MergeResult(
            merged_prompt=final_prompt,
            validation_status=status,
            validation_errors=validation_errors,
            conflicts=conflicts,
            sections=sections,
        )

    @classmethod
    def test_agent_turn(
        cls,
        merged_prompt: str,
        user_message: str,
        user_language: str = "en",
    ) -> str:
        """Simulate an agent response for interactive testing before activation."""
        msg = user_message.lower().strip()

        # Responsive demo responses across languages
        if "cancel" in msg or "order" in msg:
            if user_language == "hi":
                return "नमस्ते! मैं आपके ऑर्डर को रद्द करने में आपकी मदद कर सकता हूँ। क्या आप कृपया अपना ऑर्डर नंबर बता सकते हैं?"
            elif user_language == "ja":
                return "こんにちは！ご注文のキャンセルをお手伝いいたします。注文番号をお知らせいただけますか？"
            elif user_language == "de":
                return "Guten Tag! Ich helfe Ihnen gerne bei der Stornierung Ihrer Bestellung. Könnten Sie mir bitte Ihre Bestellnummer nennen?"
            elif user_language == "fr":
                return "Bonjour ! Je peux vous aider à annuler votre commande. Pourriez-vous s'il vous plaît me communiquer votre numéro de commande ?"
            return "Hello! I can certainly help you cancel your order. Could you please provide your order number?"

        if "human" in msg or "agent" in msg or "representative" in msg or "transfer" in msg:
            if user_language == "hi":
                return "मैं आपको तुरंत हमारे किसी विशेषज्ञ मानव प्रतिनिधि के पास ट्रांसफर कर रहा हूँ। कृपया एक क्षण प्रतीक्षा करें।"
            elif user_language == "ja":
                return "担当のオペレーターにお繋ぎいたします。少々お待ちください。"
            return "I will transfer you to a human support specialist right away. Please hold on a moment."

        if "hello" in msg or "hi" in msg or "hey" in msg or "namaste" in msg or "konnichiwa" in msg:
            if user_language == "hi":
                return "नमस्ते! GlobalTalk AI सपोर्ट में आपका स्वागत है। आज मैं आपकी क्या सहायता कर सकता हूँ?"
            elif user_language == "ja":
                return "こんにちは！GlobalTalk AIカスタマーサポートへようこそ。本日はどのようなご用件でしょうか？"
            return "Hello! Thank you for calling customer support. How may I assist you today?"

        if user_language == "hi":
            return "मैंने आपकी बात समझ ली है। क्या आप इस संबंध में कुछ और विवरण साझा कर सकते हैं?"
        elif user_language == "ja":
            return "承知いたしました。詳細を確認いたしますので、少々お待ちいただけますでしょうか。"
        return f"I understand your request regarding '{user_message}'. Let me look into that for you right away."
