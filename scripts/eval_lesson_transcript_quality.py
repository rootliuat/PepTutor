#!/usr/bin/env python3
"""Run or score a captured lesson transcript quality evaluation."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

import aiohttp

import smoke_lesson_turn as smoke
from lightrag.orchestrator.lesson_transcript_quality_eval import (
    render_transcript_quality_report,
    score_lesson_transcript,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="Score an existing transcript JSON instead of running a live route smoke.",
    )
    parser.add_argument(
        "--write-transcript",
        type=Path,
        help="Write the captured live transcript JSON to this path.",
    )
    parser.add_argument(
        "--max-response-chars",
        type=int,
        default=320,
        help="Maximum accepted teacher response length per turn.",
    )
    parser.add_argument(
        "--max-latency-ms",
        type=int,
        default=15_000,
        help="Maximum accepted request latency per turn.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the score report as JSON.",
    )
    return parser.parse_args()


def _load_transcript(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("turns"), list):
        return payload["turns"]
    if isinstance(payload, list):
        return payload
    raise ValueError("Transcript JSON must be a list or an object with a turns list.")


def _write_transcript(path: Path, turns: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"turns": turns}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _turns_from_smoke_results(
    results: list[smoke.LessonTurnResult],
) -> list[dict[str, Any]]:
    return [
        {
            "name": result.name,
            "elapsed_ms": result.elapsed_ms,
            "payload": result.payload,
        }
        for result in results
    ]


async def _capture_live_transcript() -> list[dict[str, Any]]:
    host = smoke._resolve_host()
    port = smoke._resolve_port()
    full_stack = smoke._resolve_full_stack_mode()
    keep_server = smoke._resolve_keep_server()
    startup_timeout_seconds = smoke._resolve_startup_timeout_seconds()
    request_timeout_seconds = smoke._resolve_request_timeout_seconds()
    session_timeout = aiohttp.ClientTimeout(total=smoke._resolve_timeout_seconds())

    print(f"[INFO] Lesson transcript eval host: {host}")
    print(f"[INFO] Lesson transcript eval port: {port}")
    print(f"[INFO] Route-focused mode: {'off' if full_stack else 'on'}")

    async with aiohttp.ClientSession(timeout=session_timeout, trust_env=False) as session:
        backend: smoke.StartedBackend | None = None
        try:
            backend = await smoke.start_backend(
                session,
                host=host,
                port=port,
                startup_timeout_seconds=startup_timeout_seconds,
                full_stack=full_stack,
            )
            print(
                f"[PASS] Temporary lesson backend ready at {backend.base_url} "
                f"(log={backend.log_path})"
            )
            results = await smoke.run_lesson_turn_smoke(
                session,
                base_url=backend.base_url,
                timeout_seconds=request_timeout_seconds,
            )
            return _turns_from_smoke_results(results)
        finally:
            if backend is not None:
                await smoke.stop_backend(backend, keep_server=keep_server)
                if keep_server:
                    print(
                        f"[INFO] Temporary lesson backend left running at {backend.base_url} "
                        f"(log={backend.log_path})"
                    )


async def async_main() -> int:
    args = _parse_args()
    try:
        if args.input:
            turns = _load_transcript(args.input)
        else:
            turns = await _capture_live_transcript()

        if args.write_transcript:
            _write_transcript(args.write_transcript, turns)
            print(f"[PASS] Transcript written to {args.write_transcript}")

        report = score_lesson_transcript(
            turns,
            max_response_chars=args.max_response_chars,
            max_latency_ms=args.max_latency_ms,
        )
        if args.json:
            print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        else:
            print(render_transcript_quality_report(report))
        return 0 if not report.failed_outcomes else 1
    except Exception as exc:
        print(f"[FAIL] Lesson transcript quality eval failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(async_main())
    return 130


if __name__ == "__main__":
    raise SystemExit(main())
