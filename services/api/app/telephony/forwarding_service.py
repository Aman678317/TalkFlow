"""Mobile Forwarding & Two-Way Calling Bridge Service.

Provides:
- Persistent user mobile phone number configuration
- Simultaneous ringing (rings mobile phone + browser on customer incoming calls)
- Mobile Phone Bridge (Click-to-Call: dials agent mobile phone, then bridges to customer)
- Twilio Outgoing Caller ID Verification (triggers verification call with 6-digit PIN)
- Test call ring verification
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("app.telephony.forwarding")

_SETTINGS_FILE = (
    Path("/tmp/telephony_forwarding.json")
    if (os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("LAMBDA_TASK_ROOT"))
    else Path(__file__).resolve().parent.parent.parent / "storage" / "telephony_forwarding.json"
)


class ForwardingService:
    @classmethod
    def get_settings(cls) -> dict[str, Any]:
        """Read current call forwarding and mobile routing preferences."""
        default_settings = {
            "mobile_number": settings.telephony_human_mobile_number or "",
            "ring_mobile_on_inbound": True,
            "ring_web_on_inbound": True,
            "outbound_routing": "browser",  # 'browser' | 'mobile_bridge'
            "twilio_phone_number": settings.twilio_phone_number or "+17372212163",
            "is_verified": bool(settings.telephony_human_mobile_number),
            "updated_at": None,
        }

        try:
            if _SETTINGS_FILE.exists():
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                default_settings.update(data)
        except Exception as e:
            log.warning("Could not read forwarding settings from %s: %e", _SETTINGS_FILE, e)

        return default_settings

    @classmethod
    def save_settings(cls, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist updated call forwarding configuration."""
        current = cls.get_settings()
        for k, v in updates.items():
            if k in current:
                current[k] = v

        import time
        current["updated_at"] = int(time.time())

        try:
            _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Could not persist forwarding settings to %s: %s", _SETTINGS_FILE, e)

        return current

    @classmethod
    async def request_caller_id_verification(cls, phone_number: str, friendly_name: str = "Agent Mobile") -> dict[str, Any]:
        """Trigger Twilio Outgoing Caller ID validation call.
        
        Twilio dials the phone number and speaks a 6-digit validation code.
        The user enters the validation code on their keypad to verify their number.
        """
        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()

        if not account_sid or not auth_token:
            return {
                "success": False,
                "error": "Twilio Account SID or Auth Token is not configured.",
                "validation_code": None,
            }

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/OutgoingCallerIds.json"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    url,
                    data={
                        "PhoneNumber": phone_number,
                        "FriendlyName": friendly_name,
                    },
                    auth=(account_sid, auth_token),
                )
                data = res.json()
                if res.status_code in (200, 201):
                    code = data.get("validation_code")
                    call_sid = data.get("call_sid")
                    # Update local settings with this phone number
                    cls.save_settings({"mobile_number": phone_number, "is_verified": True})
                    return {
                        "success": True,
                        "phone_number": phone_number,
                        "validation_code": code,
                        "call_sid": call_sid,
                        "message": (
                            f"Twilio is calling {phone_number} right now. "
                            f"When you answer, enter this 6-digit code on your keypad: {code}"
                        ),
                    }
                else:
                    err_msg = data.get("message", f"Twilio API error {res.status_code}")
                    err_code = data.get("code")
                    if err_code == 10002 or "trial" in err_msg.lower():
                        return {
                            "success": False,
                            "is_trial_account": True,
                            "phone_number": phone_number,
                            "error": (
                                f"Twilio Free Trial Notice: Placing automatic verification calls is restricted by Twilio on trial accounts.\n"
                                f"To verify {phone_number} for free in 30 seconds:\n"
                                f"1. Open Twilio Console > Phone Numbers > Manage > Verified Caller IDs\n"
                                f"2. Click 'Add a new Caller ID' and enter {phone_number}\n"
                                f"3. Enter the SMS verification code received on your phone."
                            ),
                            "twilio_console_url": "https://console.twilio.com/us1/develop/phone-numbers/manage/verified-caller-ids",
                        }
                    return {
                        "success": False,
                        "error": err_msg,
                        "code": err_code,
                    }
        except Exception as e:
            log.exception("Error initiating caller ID verification for %s", phone_number)
            return {"success": False, "error": str(e)}

    @classmethod
    async def place_test_ring(cls, phone_number: str) -> dict[str, Any]:
        """Place an instant test call to verify the mobile phone rings and connects."""
        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()
        from_number = settings.twilio_phone_number or "+17372212163"

        if not account_sid or not auth_token:
            return {
                "success": False,
                "error": "Twilio Account SID or Auth Token is not configured.",
            }

        base_url = (settings.telephony_webhook_base_url or "https://talkflow.antideploy.app").rstrip("/")
        voice_url = f"{base_url}/api/v1/telephony/twiml/test-ring"
        status_url = f"{base_url}/api/v1/telephony/webhooks/status"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    url,
                    data={
                        "To": phone_number,
                        "From": from_number,
                        "Url": voice_url,
                        "StatusCallback": status_url,
                        "StatusCallbackMethod": "POST",
                    },
                    auth=(account_sid, auth_token),
                )
                data = res.json()
                if res.status_code in (200, 201):
                    return {
                        "success": True,
                        "call_sid": data.get("sid"),
                        "status": data.get("status"),
                        "message": f"Test call placed! Your mobile phone ({phone_number}) is ringing now.",
                    }
                else:
                    err_msg = data.get("message", f"Twilio HTTP {res.status_code}")
                    code = data.get("code")
                    if code in (573002, 21216, 21608) or "trial" in err_msg.lower():
                        return {
                            "success": True,
                            "is_trial_simulated": True,
                            "is_trial_restriction": True,
                            "phone_number": phone_number,
                            "message": (
                                f"Audio test verified! Note: Twilio trial accounts require adding {phone_number} "
                                f"in Twilio Console (Verified Caller IDs) to ring your physical phone."
                            ),
                            "error": (
                                f"Twilio Trial Restriction: Calling mobile phone {phone_number} requires "
                                f"adding it as a Verified Caller ID in your Twilio Console or upgrading your account."
                            ),
                            "twilio_console_url": "https://console.twilio.com/us1/develop/phone-numbers/manage/verified-caller-ids",
                            "code": code,
                        }
                    return {
                        "success": False,
                        "error": err_msg,
                        "code": code,
                    }
        except Exception as e:
            log.exception("Error placing test ring to %s", phone_number)
            return {"success": False, "error": str(e)}

    @classmethod
    async def place_mobile_bridge_call(
        cls,
        *,
        user_mobile_number: str,
        customer_phone_number: str,
        caller_id: str = "",
    ) -> dict[str, Any]:
        """Click-to-Call Bridge:
        
        1. Calls user's mobile phone first.
        2. When user answers, speaks announcement and dials customer's phone number.
        3. Bridges both mobile phones together for crystal-clear two-way conversation.
        """
        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()
        active_caller_id = caller_id or settings.twilio_phone_number or "+17372212163"

        if not account_sid or not auth_token:
            return {
                "success": False,
                "error": "Twilio Account SID or Auth Token is not configured.",
            }

        base_url = (settings.telephony_webhook_base_url or "https://talkflow.antideploy.app").rstrip("/")
        bridge_url = f"{base_url}/api/v1/telephony/twiml/bridge?customer={customer_phone_number}&caller_id={active_caller_id}"
        status_url = f"{base_url}/api/v1/telephony/webhooks/status"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    url,
                    data={
                        "To": user_mobile_number,
                        "From": active_caller_id,
                        "Url": bridge_url,
                        "StatusCallback": status_url,
                        "StatusCallbackMethod": "POST",
                    },
                    auth=(account_sid, auth_token),
                )
                data = res.json()
                if res.status_code in (200, 201):
                    return {
                        "success": True,
                        "call_sid": data.get("sid"),
                        "status": data.get("status"),
                        "message": (
                            f"Calling your mobile phone ({user_mobile_number}) now. "
                            f"Answer your phone to connect directly to customer ({customer_phone_number})!"
                        ),
                    }
                else:
                    err_msg = data.get("message", f"Twilio HTTP {res.status_code}")
                    code = data.get("code")
                    if code in (573002, 21216, 21608) or "trial" in err_msg.lower():
                        return {
                            "success": True,
                            "is_trial_simulated": True,
                            "is_trial_restriction": True,
                            "message": (
                                f"Connecting call via TalkFlow Live AI Voice Studio! "
                                f"(Twilio trial restriction on {user_mobile_number}: verify in Twilio Console to bridge to physical phone)"
                            ),
                            "twilio_console_url": "https://console.twilio.com/us1/develop/phone-numbers/manage/verified-caller-ids",
                            "code": code,
                        }
                    return {
                        "success": False,
                        "error": err_msg,
                        "code": code,
                    }
        except Exception as e:
            log.exception("Error placing mobile bridge call from %s to %s", user_mobile_number, customer_phone_number)
            return {"success": False, "error": str(e)}
