"""System 02: Customer Support Triage Graph - Node Definitions & Tools.

Implements the nodes for:
1. Classifier (Structured JSON routing)
2. Billing Specialist Agent
3. Technical Support Specialist Agent
4. Human Escalation Node
"""

import json
import re
from typing import TypedDict, Optional, List, Dict, Any


class TicketState(TypedDict):
    """Shared state for support ticket triage graph."""
    ticket: str
    category: str
    confidence: float
    reasoning: str
    route: str  # "billing" | "tech" | "low_conf"
    sentiment: str  # "neutral" | "positive" | "angry"
    response: Optional[str]
    escalated: bool
    escalation_reason: Optional[str]
    history: List[Dict[str, str]]


# --- Tools for Specialists ---

def get_order(order_id: str) -> dict:
    """Mock API tool for order lookup."""
    orders = {
        "ord_101": {"id": "ord_101", "amount": 29.00, "status": "paid", "plan": "Pro Monthly"},
        "ord_102": {"id": "ord_102", "amount": 199.00, "status": "paid", "plan": "Annual Enterprise"},
    }
    return orders.get(order_id, {"id": order_id, "amount": 45.00, "status": "paid", "plan": "Pro Monthly"})


def issue_refund(order_id: str, amount: float) -> dict:
    """Mock API tool for refund issuance."""
    if amount > 50.0:
        return {
            "status": "pending_approval",
            "message": f"Refund of ${amount:.2f} requires manager approval before issuance.",
        }
    return {
        "status": "success",
        "message": f"Successfully refunded ${amount:.2f} for order {order_id}.",
    }


def search_kb(query: str) -> list[str]:
    """Mock internal knowledge base retrieval."""
    kb_articles = {
        "webrtc": [
            "Ensure UDP ports 50000-60000 are unblocked on your corporate firewall.",
            "Verify browser camera/microphone permissions in Site Settings.",
            "Check that hardware acceleration is enabled in Chrome/Edge.",
        ],
        "latency": [
            "Inspect WebSocket round-trip ping latency via chrome://webrtc-internals.",
            "Switch from WiFi to Ethernet to eliminate 2.4GHz packet jitter.",
            "Enable client-side echo cancellation toggle in Meeting Settings.",
        ],
        "audio": [
            "Check default audio input device selection in system settings.",
            "Verify microphone sample rate is configured to 48kHz.",
        ],
    }
    for key, articles in kb_articles.items():
        if key in query.lower():
            return articles
    return [
        "Standard Step 1: Clear browser cache and service workers.",
        "Standard Step 2: Test in an Incognito / Private window to disable conflicting extensions.",
        "Standard Step 3: Run connectivity probe at /api/v1/health.",
    ]


# --- Graph Nodes ---

def classify_ticket(state: TicketState) -> Dict[str, Any]:
    """Classifier Node: Evaluates ticket category, confidence, and angry sentiment."""
    text = state["ticket"].lower()

    # Rule-based / Structured Classifier Engine (Guaranteed zero-failure format)
    billing_keywords = ["charge", "charged", "bill", "billing", "refund", "invoice", "payment", "subscription", "price", "card"]
    tech_keywords = ["error", "crash", "bug", "webrtc", "mic", "microphone", "camera", "latency", "lag", "disconnect", "connect", "audio", "video"]
    angry_keywords = ["angry", "furious", "unacceptable", "scam", "ridiculous", "terrible", "worst", "sue", "lawyer", "cancel my account immediately"]

    detected_sentiment = "angry" if any(w in text for w in angry_keywords) else "neutral"

    billing_score = sum(1 for w in billing_keywords if w in text)
    tech_score = sum(1 for w in tech_keywords if w in text)

    if billing_score > tech_score and billing_score > 0:
        category = "billing"
        confidence = min(0.6 + (billing_score * 0.15), 0.98)
        reasoning = f"Detected high-signal billing terms ({billing_score} matches)."
    elif tech_score > billing_score and tech_score > 0:
        category = "tech"
        confidence = min(0.6 + (tech_score * 0.15), 0.98)
        reasoning = f"Detected technical/system terms ({tech_score} matches)."
    else:
        category = "general"
        confidence = 0.45
        reasoning = "Ambiguous inquiry lacking clear domain keywords."

    # Route decision: If confidence < 0.6 or sentiment is angry -> low_conf / escalate
    if confidence < 0.6:
        route = "low_conf"
    elif detected_sentiment == "angry":
        route = "low_conf"  # Fast escalation for distressed users
    else:
        route = category

    return {
        "category": category,
        "confidence": confidence,
        "reasoning": reasoning,
        "sentiment": detected_sentiment,
        "route": route,
    }


def billing_agent(state: TicketState) -> Dict[str, Any]:
    """Billing Specialist Node: Handles refunds, invoices, plan changes."""
    ticket = state["ticket"]
    
    # Check for refund request
    if "refund" in ticket.lower() or "charged twice" in ticket.lower():
        order = get_order("ord_101")
        refund_res = issue_refund(order["id"], order["amount"])
        
        if refund_res["status"] == "pending_approval":
            response = (
                f"Hello, I located your order {order['id']} for ${order['amount']:.2f} ({order['plan']}). "
                f"Because this exceeds $50.00, our system has submitted this for immediate manager approval. "
                "You will receive confirmation via email within 2 hours."
            )
        else:
            response = (
                f"Hello, I located your order {order['id']} for ${order['amount']:.2f} ({order['plan']}). "
                f"{refund_res['message']} Your funds will return to your original payment method in 3–5 business days."
            )
    else:
        response = (
            "Hello, our Billing team has reviewed your inquiry. You can download all past invoices "
            "and update your payment method directly at https://talkflow.ai/billing. "
            "Let us know if you need customized VAT receipt details."
        )

    return {
        "response": response,
        "escalated": False,
    }


def tech_agent(state: TicketState) -> Dict[str, Any]:
    """Tech Support Specialist Node: Concrete troubleshooting with KB lookup."""
    ticket = state["ticket"]
    kb_solutions = search_kb(ticket)
    
    steps = "\n".join(f"{i+1}. {step}" for i, step in enumerate(kb_solutions))
    response = (
        f"Hello, thanks for reaching out. Let's troubleshoot your issue:\n\n"
        f"{steps}\n\n"
        "If you still encounter issues after completing these concrete steps, reply with your "
        "browser console log and our engineering team will assist."
    )

    return {
        "response": response,
        "escalated": False,
    }


def human_escalation(state: TicketState) -> Dict[str, Any]:
    """Escalation Node: Routes low-confidence or angry tickets to human queue."""
    sentiment_flag = " (High Priority: Angry Sentiment)" if state.get("sentiment") == "angry" else ""
    reason = state.get("reasoning", "Low classifier confidence")
    
    escalation_message = (
        f"[TICKET ESCALATED TO HUMAN QUEUE{sentiment_flag}]\n"
        f"Reason: {reason} (Confidence: {state.get('confidence', 0):.2f})\n"
        f"Customer Message: \"{state['ticket']}\"\n"
        "Status: Assigned to Senior Support Specialist on-call (Slack alert posted)."
    )
    
    return {
        "response": escalation_message,
        "escalated": True,
        "escalation_reason": reason,
    }
