#!/usr/bin/env python3
"""Run an offline agentic CLI harness for PepTutor curriculum evidence review."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_QUERY_SET = Path("docs/curriculum-agentic-query-set-20260505.json")
DEFAULT_OUT_DIR = Path("temp/lesson-smoke-artifacts")
SUPPORTED_PROVIDERS = {"none", "kimi", "deepagents", "bub", "generic"}
PROVIDER_COMMAND_ENV = {
    "kimi": "PEPTUTOR_AGENTIC_KIMI_COMMAND",
    "deepagents": "PEPTUTOR_AGENTIC_DEEPAGENTS_COMMAND",
    "bub": "PEPTUTOR_AGENTIC_BUB_COMMAND",
    "generic": "PEPTUTOR_AGENTIC_GENERIC_COMMAND",
}


CommandRunner = Callable[[str, float | None], subprocess.CompletedProcess[str]]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def latest_artifact(pattern: str) -> Path | None:
    artifact_dir = repo_root() / "temp/lesson-smoke-artifacts"
    matches = sorted(artifact_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def load_evidence_index(path: Path | None = None) -> dict[str, Any]:
    candidate = path or latest_artifact("curriculum_evidence_index_*.json")
    if candidate and resolve_path(candidate).is_file():
        return load_json(candidate)
    return {"entries": [], "summary": {"entry_count": 0}}


def _words(text: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {word for word in normalized.split() if len(word) >= 2}


def score_entry(query: dict[str, Any], entry: dict[str, Any]) -> int:
    query_words = _words(f"{query.get('text', '')} {query.get('page_uid', '')} {query.get('review_focus', '')}")
    entry_text = " ".join(
        str(entry.get(key, ""))
        for key in ("page_uid", "block_uid", "evidence_type", "source_ref", "text", "source")
    )
    score = len(query_words & _words(entry_text))
    if query.get("page_uid") and query.get("page_uid") == entry.get("page_uid"):
        score += 8
    if entry.get("source") == "structured":
        score += 2
    return score


def top_evidence(query: dict[str, Any], entries: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(
        ((score_entry(query, entry), entry) for entry in entries),
        key=lambda item: (item[0], item[1].get("source", ""), item[1].get("source_ref", "")),
        reverse=True,
    )
    result = []
    for score, entry in ranked:
        if score <= 0:
            continue
        result.append(
            {
                "score": score,
                "source": entry.get("source", ""),
                "source_ref": entry.get("source_ref", ""),
                "page_uid": entry.get("page_uid", ""),
                "block_uid": entry.get("block_uid", ""),
                "evidence_type": entry.get("evidence_type", ""),
                "text": str(entry.get("text", ""))[:800],
            }
        )
        if len(result) >= limit:
            break
    return result


def build_prompt(query: dict[str, Any], evidence_hits: list[dict[str, Any]]) -> str:
    evidence_lines = []
    for index, hit in enumerate(evidence_hits, start=1):
        evidence_lines.append(
            "\n".join(
                [
                    f"[{index}] source={hit.get('source')} ref={hit.get('source_ref')}",
                    f"page_uid={hit.get('page_uid')} block_uid={hit.get('block_uid')}",
                    f"type={hit.get('evidence_type')}",
                    f"text={hit.get('text')}",
                ]
            )
        )
    evidence_text = "\n\n".join(evidence_lines) or "No local evidence hits were found."
    return f"""You are reviewing PepTutor curriculum evidence offline.

Rules:
- Use evidence only for review; do not edit files.
- app/knowledge/structured remains canonical.
- Do not propose runtime, prompt, TeachingMove, redirect policy, S4, persona, or smoke matrix changes.
- Return concise review notes with evidence references.

Query:
id={query.get('query_id')}
text={query.get('text')}
page_uid={query.get('page_uid', '')}
review_focus={query.get('review_focus', '')}

Local evidence:
{evidence_text}

Review output:
1. Relevant evidence:
2. Possible curriculum data issue:
3. Suggested human-review action:
4. Risk:
"""


def default_runner(command: str, timeout_seconds: float | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def command_template_for_provider(provider: str, provider_command: str | None) -> str | None:
    if provider == "none":
        return None
    if provider_command:
        return provider_command
    return os.getenv(PROVIDER_COMMAND_ENV.get(provider, ""))


def render_provider_command(template: str, *, prompt_file: Path, query_id: str, provider: str) -> str:
    return template.format(
        prompt_file=shlex.quote(str(prompt_file)),
        query_id=shlex.quote(query_id),
        provider=shlex.quote(provider),
    )


def call_provider(
    *,
    provider: str,
    provider_command: str | None,
    prompt: str,
    query_id: str,
    timeout_seconds: float | None,
    runner: CommandRunner = default_runner,
) -> dict[str, Any]:
    if provider == "none":
        return {
            "provider": provider,
            "called": False,
            "command": "",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "duration": 0.0,
            "duration_seconds": 0.0,
        }

    template = command_template_for_provider(provider, provider_command)
    if not template:
        return {
            "provider": provider,
            "called": False,
            "command": "",
            "exit_code": 127,
            "stdout": "",
            "stderr": f"No command configured for provider={provider}",
            "duration": 0.0,
            "duration_seconds": 0.0,
        }

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".prompt.txt", delete=False) as prompt_file:
        prompt_file.write(prompt)
        prompt_path = Path(prompt_file.name)

    command = render_provider_command(template, prompt_file=prompt_path, query_id=query_id, provider=provider)
    start = time.monotonic()
    try:
        completed = runner(command, timeout_seconds)
        duration = time.monotonic() - start
        return {
            "provider": provider,
            "called": True,
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration": round(duration, 3),
            "duration_seconds": round(duration, 3),
        }
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        return {
            "provider": provider,
            "called": True,
            "command": command,
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": f"Timed out after {timeout_seconds} seconds",
            "duration": round(duration, 3),
            "duration_seconds": round(duration, 3),
        }


def run_harness(
    *,
    query_set: dict[str, Any],
    evidence_index: dict[str, Any],
    provider: str = "none",
    provider_command: str | None = None,
    timeout_seconds: float | None = 60.0,
    runner: CommandRunner = default_runner,
) -> dict[str, Any]:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")

    entries = evidence_index.get("entries", [])
    results = []
    for query in query_set.get("queries", []):
        hits = top_evidence(query, entries)
        prompt = build_prompt(query, hits)
        provider_log = call_provider(
            provider=provider,
            provider_command=provider_command,
            prompt=prompt,
            query_id=query.get("query_id", ""),
            timeout_seconds=timeout_seconds,
            runner=runner,
        )
        results.append(
            {
                "query_id": query.get("query_id", ""),
                "query_text": query.get("text", ""),
                "page_uid": query.get("page_uid", ""),
                "review_focus": query.get("review_focus", ""),
                "prompt": prompt,
                "evidence_hits": hits,
                "provider_log": provider_log,
            }
        )

    return {
        "schema_version": "agentic_curriculum_harness_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "provider_command_configured": bool(provider_command or command_template_for_provider(provider, None)),
        "canonical_source": "app/knowledge/structured",
        "runtime_connected": False,
        "agent_outputs_are_review_only": True,
        "summary": {
            "query_count": len(results),
            "provider_call_count": sum(1 for result in results if result["provider_log"].get("called")),
            "provider_failure_count": sum(
                1
                for result in results
                if result["provider_log"].get("exit_code") not in {None, 0}
            ),
        },
        "results": results,
    }


def write_harness_result(result: dict[str, Any], out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    resolved = resolve_path(out_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    path = resolved / f"agentic_curriculum_harness_{timestamp()}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-set", type=Path, default=DEFAULT_QUERY_SET)
    parser.add_argument("--evidence-index", type=Path)
    parser.add_argument("--provider", choices=sorted(SUPPORTED_PROVIDERS), default="none")
    parser.add_argument("--provider-command")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_harness(
        query_set=load_json(args.query_set),
        evidence_index=load_evidence_index(args.evidence_index),
        provider=args.provider,
        provider_command=args.provider_command,
        timeout_seconds=args.timeout_seconds,
    )
    print(write_harness_result(result, args.out_dir))


if __name__ == "__main__":
    main()
