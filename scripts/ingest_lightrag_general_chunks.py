#!/usr/bin/env python3
"""Fast chunk-only ingest for PepTutor general textbook data into LightRAG.

This uses LightRAG's custom KG insertion path with chunks only. It populates the
chunk KV/vector stores used by /query/data without running entity/relation
extraction over every document.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend" / "LightRAG"
DEFAULT_MANIFEST = (
    ROOT_DIR / "app" / "knowledge" / "structured" / "general" / "general-manifest.json"
)
DEFAULT_WORKING_DIR = BACKEND_DIR / "rag_storage"
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert PEP Grade 5-6 textbook chunks into LightRAG storage.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--backend-dir", type=Path, default=BACKEND_DIR)
    parser.add_argument("--working-dir", type=Path, default=DEFAULT_WORKING_DIR)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Move the current working dir aside before ingesting.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    scopes = build_scope_records(args.manifest)
    chunk_count = sum(len(scope["chunks"]) for scope in scopes)
    total_chars = sum(
        len(chunk["content"]) for scope in scopes for chunk in scope["chunks"]
    )

    print(f"manifest={args.manifest.resolve()}")
    print(f"scopes={len(scopes)}")
    print(f"chunks={chunk_count}")
    print(f"chunk_chars={total_chars}")
    print(f"working_dir={args.working_dir.resolve()}")

    if args.dry_run:
        first_scope = scopes[0]
        print(f"sample_doc={first_scope['file_source']}")
        print(f"sample_chunk_source={first_scope['chunks'][0]['source_id']}")
        print(first_scope["chunks"][0]["content"][:1200])
        return 0

    load_env_file(args.env_file)
    if args.reset:
        backup = rotate_working_dir(args.working_dir)
        if backup:
            print(f"backup={backup}")

    asyncio.run(ingest(scopes=scopes, backend_dir=args.backend_dir, working_dir=args.working_dir))
    print("ingest=complete")
    return 0


def build_scope_records(manifest_path: Path) -> list[dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    base_dir = manifest_path.parent
    manifest = load_json(manifest_path)
    records: list[dict[str, Any]] = []

    for file_name in manifest["files"]:
        source_path = base_dir / file_name
        payload = load_json(source_path)
        scope = payload["scope"]
        scope_key = (
            f"{scope['grade'].lower()}{scope['semester'].lower()}{scope['unit'].lower()}"
        )
        source_rel = source_path.relative_to(ROOT_DIR).as_posix()
        file_source = f"peptutor-general/{scope_key}.txt"
        chunks = build_scope_chunks(payload, source_rel, scope_key)
        full_text = "\n\n".join(chunk["content"] for chunk in chunks)
        records.append(
            {
                "scope_key": scope_key,
                "file_source": file_source,
                "source_rel": source_rel,
                "full_text": full_text,
                "chunks": chunks,
            }
        )

    return records


def build_scope_chunks(
    payload: dict[str, Any], source_rel: str, scope_key: str
) -> list[dict[str, str | int]]:
    scope = payload["scope"]
    scope_label = f"{scope['grade']} {scope['semester']} {scope['unit']}"
    page_by_uid = {page["page_uid"]: page for page in payload.get("page_lessons", [])}
    atoms_by_block: dict[str, list[dict[str, Any]]] = {}
    for atom in payload.get("knowledge_atoms", []):
        for block_uid in atom.get("linked_blocks", []):
            atoms_by_block.setdefault(block_uid, []).append(atom)
    targets_by_block: dict[str, list[dict[str, Any]]] = {}
    for target in payload.get("learning_targets", []):
        targets_by_block.setdefault(target.get("block_uid", ""), []).append(target)

    chunks: list[dict[str, str | int]] = []

    wordlist = payload.get("wordlist_entries", [])
    if wordlist:
        lines = [
            "PepTutor PEP English textbook word list",
            f"Scope: {scope_label}",
            f"Source structured draft: {source_rel}",
            f"Pages: {', '.join(str(page) for page in scope.get('pages', []))}",
            "",
            "Unit word list:",
        ]
        for entry in wordlist:
            phonetic = f" {entry['phonetic']}" if entry.get("phonetic") else ""
            emphasized = " key" if entry.get("emphasized") else ""
            linked = ", ".join(entry.get("linked_block_uids", []))
            lines.append(
                f"- {entry.get('word', '')}{phonetic}: {entry.get('chinese', '')}{emphasized}; linked_blocks={linked}"
            )
        chunks.append(
            {
                "source_id": f"{scope_key}-wordlist",
                "file_path": f"peptutor-general-chunks/{scope_key}/wordlist.txt",
                "chunk_order_index": len(chunks),
                "content": "\n".join(lines).strip() + "\n",
            }
        )

    for block in payload.get("teaching_blocks", []):
        page = page_by_uid.get(block.get("page_uid", ""), {})
        block_uid = block["block_uid"]
        lines = [
            "PepTutor PEP English textbook teaching block",
            f"Scope: {scope_label}",
            f"Source structured draft: {source_rel}",
            f"Page: {block.get('page_uid', '')}",
            f"Page type: {page.get('page_type') or block.get('page_type', '')}",
            f"Page intro: {page.get('page_intro_cn', '')}",
        ]
        append_list(lines, "Page entry probes", page.get("entry_probe_questions", []))
        lines.extend(
            [
                "",
                f"Teaching block: {block_uid}",
                f"Block type: {block.get('block_type', '')}",
                f"Source refs: {', '.join(block.get('source_refs', []))}",
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

        targets = targets_by_block.get(block_uid, [])
        if targets:
            lines.append("Learning targets:")
            for target in targets:
                lines.append(
                    f"- {target.get('target_uid', '')}: {target.get('text', '')}; category={target.get('category', '')}"
                )

        atoms = atoms_by_block.get(block_uid, [])
        if atoms:
            lines.append("Knowledge atoms:")
            for atom in atoms:
                gloss = atom.get("gloss") or ""
                lines.append(
                    f"- {atom.get('text', '')}: {gloss}; type={atom.get('atom_type', '')}; atom_uid={atom.get('atom_uid', '')}"
                )

        chunks.append(
            {
                "source_id": block_uid,
                "file_path": f"peptutor-general-chunks/{scope_key}/{block_uid}.txt",
                "chunk_order_index": len(chunks),
                "content": "\n".join(lines).strip() + "\n",
            }
        )

    return chunks


async def ingest(
    *, scopes: list[dict[str, Any]], backend_dir: Path, working_dir: Path
) -> None:
    sys.path.insert(0, str(backend_dir.resolve()))

    from lightrag import LightRAG
    from lightrag.base import DocStatus
    from lightrag.llm.openai import openai_embed
    from lightrag.utils import EmbeddingFunc, compute_mdhash_id, sanitize_text_for_encoding

    embedding_model = require_env("EMBEDDING_MODEL")
    embedding_dim = int(require_env("EMBEDDING_DIM"))
    embedding_host = require_env("EMBEDDING_BINDING_HOST")
    embedding_api_key = require_env("EMBEDDING_BINDING_API_KEY")

    actual_embed = openai_embed.func if isinstance(openai_embed, EmbeddingFunc) else openai_embed
    embedding_func = EmbeddingFunc(
        embedding_dim=embedding_dim,
        func=partial(
            actual_embed,
            model=embedding_model,
            base_url=embedding_host,
            api_key=embedding_api_key,
        ),
        max_token_size=8192,
        send_dimensions=False,
        model_name=embedding_model,
    )

    async def noop_llm(*_: Any, **__: Any) -> str:
        return ""

    rag = LightRAG(
        working_dir=str(working_dir.resolve()),
        llm_model_func=noop_llm,
        llm_model_name="noop",
        embedding_func=embedding_func,
        kv_storage="JsonKVStorage",
        doc_status_storage="JsonDocStatusStorage",
        graph_storage="NetworkXStorage",
        vector_storage="NanoVectorDBStorage",
        vector_db_storage_cls_kwargs={"cosine_better_than_threshold": 0.2},
        enable_llm_cache=False,
        enable_llm_cache_for_entity_extract=False,
    )
    await rag.initialize_storages()

    now = datetime.now(timezone.utc).isoformat()
    track_id = "custom_chunks_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    try:
        for index, scope in enumerate(scopes, start=1):
            full_text = sanitize_text_for_encoding(scope["full_text"])
            doc_id = compute_mdhash_id(full_text, prefix="doc-")
            custom_kg = {
                "chunks": [
                    {
                        "content": chunk["content"],
                        "source_id": chunk["source_id"],
                        "file_path": chunk["file_path"],
                        "chunk_order_index": chunk["chunk_order_index"],
                    }
                    for chunk in scope["chunks"]
                ],
                "entities": [],
                "relationships": [],
            }
            await rag.ainsert_custom_kg(custom_kg, full_doc_id=doc_id)

            chunk_ids = [
                compute_mdhash_id(
                    sanitize_text_for_encoding(str(chunk["content"])), prefix="chunk-"
                )
                for chunk in scope["chunks"]
            ]
            await rag.full_docs.upsert(
                {doc_id: {"content": full_text, "file_path": scope["file_source"]}}
            )
            await rag.doc_status.upsert(
                {
                    doc_id: {
                        "status": DocStatus.PROCESSED.value,
                        "chunks_count": len(chunk_ids),
                        "chunks_list": chunk_ids,
                        "content_summary": full_text[:240],
                        "content_length": len(full_text),
                        "created_at": now,
                        "updated_at": now,
                        "file_path": scope["file_source"],
                        "track_id": track_id,
                        "metadata": {
                            "ingest_method": "custom_kg_chunks",
                            "scope_key": scope["scope_key"],
                            "source": scope["source_rel"],
                        },
                    }
                }
            )
            await rag._insert_done()
            print(
                f"scope {index}/{len(scopes)} {scope['scope_key']} chunks={len(chunk_ids)} doc_id={doc_id}"
            )
    finally:
        await rag.finalize_storages()


def rotate_working_dir(working_dir: Path) -> Path | None:
    working_dir = working_dir.resolve()
    if not working_dir.exists():
        working_dir.mkdir(parents=True, exist_ok=True)
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = working_dir.with_name(f"{working_dir.name}.bak-{stamp}")
    shutil.move(str(working_dir), str(backup))
    working_dir.mkdir(parents=True, exist_ok=True)
    return backup


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


def append_list(lines: list[str], label: str, values: list[str]) -> None:
    if not values:
        return
    lines.append(f"{label}:")
    lines.extend(f"- {value}" for value in values)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
