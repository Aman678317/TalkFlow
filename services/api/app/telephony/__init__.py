"""GlobalTalk AI Telephony Subsystem.

Provides carrier-grade PSTN/VoIP international calling with bidirectional
real-time AI translation, provider abstraction (Twilio, Telnyx, LiveKit SIP, Simulated),
media stream transcoding (G.711 μ-law 8kHz <-> PCM16 16kHz), and call state lifecycle.
"""
from app.telephony.service import TelephonyService
from app.telephony.call_service import CallService
from app.telephony.phone_number_service import PhoneNumberService
from app.telephony.media_stream_service import MediaStreamService
from app.telephony.webhook_service import TelephonyWebhookService

__all__ = [
    "TelephonyService",
    "CallService",
    "PhoneNumberService",
    "MediaStreamService",
    "TelephonyWebhookService",
]
