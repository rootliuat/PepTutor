#!/usr/bin/env python3
"""Ingest PepTutor general Grade 5-6 textbook drafts into LightRAG documents."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT_DIR / "app" / "knowledge" / "structured" / "general" / "general-manifest.json"
)
DEFAULT_BASE_URL = "http://127.0.0.1:9625"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit structured PepTutor general textbook data to LightRAG /documents/texts.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    docs = build_documents(args.manifest)
    total_chars = sum(len(doc["text"]) for doc in docs)

    print(f"manifest={args.manifest}")
    print(f"documents={len(docs)}")
    print(f"total_chars={total_chars}")
    print(f"base_url={base_url}")

    if args.dry_run:
        for doc in docs[:3]:
            print("---")
            print(doc["file_source"])
            print(doc["text"][:800])
        return 0

    before = get_json(f"{base_url}/documents/status_counts")
    print(f"before_status_counts={json.dumps(before, ensure_ascii=False)}")

    response = post_json(
        f"{base_url}/documents/texts",
        {
            "texts": [doc["text"] for doc in docs],
            "file_sources": [doc["file_source"] for doc in docs],
        },
    )
    print(f"insert_response={json.dumps(response, ensure_ascii=False)}")

    status = str(response.get("status") or "")
    if status not in {"success", "duplicated", "partial_success"}:
        print("insert did not return a successful status", file=sys.stderr)
        return 1

    if status == "duplicated":
        print("documents already existed; skipping wait")
        return 0

    wait_for_pipeline(
        base_url=base_url,
        expected_docs=len(docs),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    return 0


def build_documents(manifest_path: Path) -> list[dict[str, str]]:
    manifest_path = manifest_path.resolve()
    base_dir = manifest_path.parent
    manifest = load_json(manifest_path)
    result: list[dict[str, str]] = []

    for file_name in manifest["files"]:
        source_path = base_dir / file_name
        payload = load_json(source_path)
        text = build_scope_text(payload, source_path.relative_to(ROOT_DIR).as_posix())
        scope = payload["scope"]
        file_source = (
            "peptutor-general/"
            f"{scope['grade'].lower()}{scope['semester'].lower()}{scope['unit'].lower()}.txt"
        )
        result.append({"file_source": file_source, "text": text})

    return result


def build_scope_text(payload: dict[str, Any], source_path: str) -> str:
    scope = payload["scope"]
    scope_label = f"{scope['grade']} {scope['semester']} {scope['unit']}"
    page_by_uid = {page["page_uid"]: page for page in payload.get("page_lessons", [])}
    blocks_by_page: dict[str, list[dict[str, Any]]] = {}
    for block in payload.get("teaching_blocks", []):
        blocks_by_page.setdefault(block["page_uid"], []).append(block)

    lines: list[str] = [
        f"PepTutor PEP English textbook scope: {scope_label}",
        f"Source structured draft: {source_path}",
        f"Pages: {', '.join(str(page) for page in scope.get('pages', []))}",
        "",
        "This document is generated from PepTutor general_draft_builder output.",
        "It contains page introductions, teaching blocks, vocabulary, sentence patterns, answer scopes, and knowledge atoms.",
        "",
    ]

    wordlist_entries = payload.get("wordlist_entries", [])
    if wordlist_entries:
        lines.append("Unit word list:")
        for entry in wordlist_entries:
            phonetic = f" {entry['phonetic']}" if entry.get("phonetic") else ""
            emphasized = " key" if entry.get("emphasized") else ""
            linked = ", ".join(entry.get("linked_block_uids", []))
            lines.append(
                f"- {entry['word']}{phonetic}: {entry.get('chinese', '')}{emphasized}; linked_blocks={linked}"
            )
        lines.append("")

    for page_uid in sorted(page_by_uid, key=page_sort_key):
        page = page_by_uid[page_uid]
        lines.extend(
            [
                f"Page {page_uid}",
                f"Page type: {page.get('page_type', '')}",
                f"Page intro: {page.get('page_intro_cn', '')}",
            ]
        )
        if page.get("entry_probe_questions"):
            lines.append("Page entry probes:")
            lines.extend(f"- {item}" for item in page["entry_probe_questions"])

        for block in blocks_by_page.get(page_uid, []):
            lines.extend(
                [
                    "",
                    f"Teaching block {block['block_uid']}",
                    f"Block type: {block.get('block_type', '')}",
                    f"Teaching goal: {block.get('teaching_goal', '')}",
                    f"Teaching summary: {block.get('teaching_summary', '')}",
                ]
            )
            append_list(lines, "Focus vocabulary", block.get("focus_vocabulary", []))
            append_list(lines, "Core patterns", block.get("core_patterns", []))
            append_list(lines, "Allowed answer scope", block.get("allowed_answer_scope", []))
            append_list(lines, "Block entry probes", block.get("entry_probe_questions", []))
            append_list(lines, "Branchable topics", block.get("branchable_topics", []))
            append_list(lines, "Return anchors", block.get("return_anchors", []))

        linked_atoms = [
            atom
            for atom in payload.get("knowledge_atoms", [])
            if any(block_uid.startswith(page_uid) for block_uid in atom.get("linked_blocks", []))
        ]
        if linked_atoms:
            lines.append("")
            lines.append(f"Knowledge atoms linked to {page_uid}:")
            for atom in linked_atoms:
                linked = ", ".join(atom.get("linked_blocks", []))
                gloss = atom.get("gloss") or ""
                lines.append(
                    f"- {atom.get('text', '')}: {gloss}; type={atom.get('atom_type', '')}; linked_blocks={linked}"
                )

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def append_list(lines: list[str], label: str, values: list[str]) -> None:
    if not values:
        return
    lines.append(f"{label}:")
    lines.extend(f"- {value}" for value in values)


def page_sort_key(page_uid: str) -> tuple[int, str]:
    marker = "-P"
    if marker not in page_uid:
        return (10**9, page_uid)
    raw = page_uid.split(marker, 1)[1].split("-", 1)[0]
    try:
        return (int(raw), page_uid)
    except ValueError:
        return (10**9, page_uid)


def wait_for_pipeline(
    *,
    base_url: str,
    expected_docs: int,
    timeout_seconds: float,
    poll_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        counts_payload = get_json(f"{base_url}/documents/status_counts")
        pipeline_payload = get_json(f"{base_url}/documents/pipeline_status")
        counts = counts_payload.get("status_counts", {})
        processed = int(counts.get("processed") or 0)
        failed = int(counts.get("failed") or 0)
        active = sum(int(counts.get(key) or 0) for key in ("pending", "processing", "preprocessed"))
        busy = bool(pipeline_payload.get("busy"))
        latest = pipeline_payload.get("latest_message") or ""
        print(
            "pipeline "
            f"processed={processed} failed={failed} active={active} busy={busy} "
            f"message={latest}"
        )

        if failed:
            raise RuntimeError(f"LightRAG document pipeline failed for {failed} document(s)")
        if processed >= expected_docs and active == 0 and not busy:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for LightRAG document pipeline")
        time.sleep(max(1.0, poll_seconds))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    return request_json(request)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return request_json(request)


def request_json(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{request.full_url} returned HTTP {exc.code}: {raw}") from exc
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {request.full_url}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
