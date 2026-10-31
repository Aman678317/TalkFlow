"""CLI demonstration script for Neural Translation Agent."""
from __future__ import annotations

import argparse
import asyncio
from app.models.schemas import TranslationRequestSchema
from app.translation.engine import translation_engine


async def main() -> None:
    parser = argparse.ArgumentParser(description="TalkFlow Neural Translation CLI")
    parser.add_argument("--text", type=str, required=True, help="Input source text")
    parser.add_argument("--source", type=str, default="auto", help="Source ISO language code or 'auto'")
    parser.add_argument("--target", type=str, required=True, help="Target ISO language code")
    parser.add_argument("--private", action="store_true", help="Enforce local-only private translation")
    args = parser.parse_args()

    print(f"\n[INFO] Translating '{args.text}' [{args.source} -> {args.target}] (private={args.private})...")
    req = TranslationRequestSchema(
        text=args.text,
        source_lang=args.source,
        target_lang=args.target,
        tenant_private_only=args.private,
    )
    res = await translation_engine.translate_single(req)

    print("\n" + "=" * 60)
    print("TRANSLATION RESULT")
    print("=" * 60)
    print(f"Source Text : {args.text}")
    print(f"Translation : {res.text}")
    print(f"Provider    : {res.provider} (Model: {res.model})")
    print(f"Latency     : {res.latency_ms} ms")
    print(f"Flags       : {res.quality_flags}")
    print(f"Pivoted     : {res.pivoted}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

