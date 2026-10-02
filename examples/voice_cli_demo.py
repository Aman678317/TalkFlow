"""GlobalTalk AI — Voice Streaming CLI (Desi Voice API Equivalent).

Mirrors the functionality of official `desi-python`'s `examples/voice/cli/desi-voice-api-cli.py`:
1. Requests a real-time voice streaming session via `POST /v3/voice/realtime`.
2. Connects to the returned WebSocket streaming URL.
3. Streams audio (microphone or simulated 16 kHz PCM16 audio).
4. Prints live transcriptions and real-time translations in the console.

Usage:
    python examples/voice_cli_demo.py --src en --tgt de
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request

try:
    import websockets
except ImportError:
    websockets = None

SERVER_URL = os.environ.get("GLOBAL_TALK_URL", "http://127.0.0.1:8088")
AUTH_KEY = os.environ.get("DESI_AUTH_KEY") or os.environ.get("DEEPL_AUTH_KEY") or "gtk_demo_key:fx"


def initiate_voice_session(src_lang: str, tgt_langs: list[str]) -> dict:
    """Request a real-time voice streaming session conforming to Desi Voice API."""
    url = f"{SERVER_URL}/v3/voice/realtime"
    payload = json.dumps({
        "source_language": src_lang,
        "target_languages": tgt_langs,
        "audio_mode": "both",
        "message_format": "json",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Desi-Auth-Key {AUTH_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def stream_voice_session(session_info: dict, duration_seconds: int = 5):
    """Connect to WebSocket streaming URL and stream PCM16 audio blocks."""
    if websockets is None:
        print("\n[!] 'websockets' library is not installed. To run live WebSocket streaming:")
        print("    pip install websockets")
        print("\nSession endpoint successfully initialized:")
        print(json.dumps(session_info, indent=2))
        return

    streaming_url = session_info["streaming_url"]
    print(f"\n[+] Connecting to streaming endpoint: {streaming_url}")

    async with websockets.connect(streaming_url) as ws:
        print("[+] Connected! Initializing audio pipeline...")

        # Send start event
        await ws.send(json.dumps({
            "type": "audio.start",
            "sample_rate": 16000,
            "channels": 1,
            "format": "pcm16",
        }))

        # Task to receive incoming transcriptions & translations
        async def receive_loop():
            try:
                async for message in ws:
                    if isinstance(message, str):
                        data = json.loads(message)
                        event_type = data.get("type")
                        if event_type == "transcript.partial":
                            print(f"\r[Speaking ({data.get('language')})]: {data.get('text')}", end="", flush=True)
                        elif event_type == "transcript.final":
                            print(f"\n[Final ({data.get('language')})]: {data.get('text')}")
                        elif event_type == "translation.final":
                            print(f"[Translation ({data.get('target_lang')})]: {data.get('text')}")
            except asyncio.CancelledError:
                pass

        recv_task = asyncio.create_task(receive_loop())

        # Stream simulated 16 kHz PCM16 silence/speech frames (~100 ms each = 3200 bytes)
        chunk = b"\x00\x00" * 1600
        start_time = time.time()
        print(f"[*] Streaming audio chunks for {duration_seconds}s...")

        try:
            while time.time() - start_time < duration_seconds:
                await ws.send(chunk)
                await asyncio.sleep(0.1)

            # Send stop event
            await ws.send(json.dumps({"type": "audio.stop"}))
            await asyncio.sleep(1.0)
        finally:
            recv_task.cancel()


def main():
    parser = argparse.ArgumentParser(description="GlobalTalk AI / Desi Voice API CLI")
    parser.add_argument("--src", default="en", help="Source language (e.g. en)")
    parser.add_argument("--tgt", default="de", help="Comma-separated target languages (e.g. de,es,fr)")
    parser.add_argument("--duration", type=int, default=5, help="Simulation duration in seconds")
    args = parser.parse_args()

    tgt_langs = [t.strip() for t in args.tgt.split(",") if t.strip()]

    print("==================================================================")
    print("      GlobalTalk AI — Voice Streaming CLI (Desi Conformance)      ")
    print("==================================================================")
    print(f"Target Server:   {SERVER_URL}")
    print(f"Source Language: {args.src}")
    print(f"Target Languages: {tgt_langs}")

    try:
        session_info = initiate_voice_session(args.src, tgt_langs)
        print(f"\n[+] Session created: ID={session_info['session_id']}")
        print(f"[+] Protocol version: {session_info.get('protocol_version')}")
        print(f"[+] Expires in: {session_info.get('expires_at')} (epoch)")

        asyncio.run(stream_voice_session(session_info, duration_seconds=args.duration))
    except Exception as e:
        print(f"[-] Error initiating voice session: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
