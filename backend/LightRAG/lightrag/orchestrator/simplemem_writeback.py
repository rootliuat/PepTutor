"""Best-effort SimpleMem-Cross writeback for lesson traces."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.simplemem_semantic_memory import (
    LessonSemanticMemoryEntry,
    SimpleMemLanceVectorStore,
    build_semantic_tenant_namespace,
)
from lightrag.pedagogy.evaluation import normalize_text
from lightrag.utils import logger

if TYPE_CHECKING:
    from lightrag.orchestrator.lesson_runtime import (
        LessonTurnResult,
        PageLessonRecord,
        TeachingBlockRecord,
    )


_PREFERENCE_CHINESE_TOKENS = ("中文", "汉语", "讲中文", "中文解释")
_PREFERENCE_SLOW_TOKENS = (
    "again",
    "repeat",
    "slow",
    "slowly",
    "one by one",
    "step by step",
    "再来",
    "慢一点",
    "慢点",
    "拆开",
    "一步一步",
)
_PREFERENCE_TEXT_BY_KEY = {
    "chinese_explanation": "Learner prefers Chinese explanation before retry.",
    "slow_split_practice": "Learner prefers slower split practice when stuck.",
}


class LessonMemoryCandidate(BaseModel):
    """A distilled learner-memory item ready for SimpleMem persistence."""

    model_config = ConfigDict(extra="forbid")

    candidate_kind: Literal["mistake", "preference", "mastery"]
    memory_layer: Literal["fact", "episode", "procedure"]
    observation_type: Literal["decision", "discovery", "change"]
    title: str = Field(min_length=1)
    subtitle: str | None = None
    narrative: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    concepts: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class SimpleMemSQLiteLessonMemoryWriter:
    """Write distilled lesson traces into SimpleMem-Cross SQLite."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        project: str,
        semantic_store: SimpleMemLanceVectorStore | None = None,
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.project = project
        self.semantic_store = semantic_store
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._run_migrations()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            logger.exception("Failed to close SimpleMem writeback SQLite connection")

    def ensure_session(
        self,
        *,
        student_id: str,
        content_session_id: str,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
    ) -> str:
        scoped_content_session_id = self._scope_content_session_id(
            student_id=student_id,
            content_session_id=content_session_id,
        )
        row = self.conn.execute(
            """
            SELECT memory_session_id FROM sessions
            WHERE tenant_id = ? AND project = ? AND content_session_id IN (?, ?)
            ORDER BY CASE WHEN content_session_id = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (
                student_id,
                self.project,
                scoped_content_session_id,
                content_session_id,
                scoped_content_session_id,
            ),
        ).fetchone()
        if row is not None:
            return str(row["memory_session_id"])

        memory_session_id = str(uuid4())
        metadata = {
            "page_uid": page.page_uid,
            "page_type": page.page_type,
            "block_uid": block.block_uid,
            "block_type": block.block_type,
        }
        try:
            self.conn.execute(
                """
                INSERT INTO sessions (
                    tenant_id, content_session_id, memory_session_id, project,
                    user_prompt, started_at, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?)
                """,
                (
                    student_id,
                    scoped_content_session_id,
                    memory_session_id,
                    self.project,
                    f"Practice lesson page {page.page_uid}",
                    "active",
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO session_events (
                    memory_session_id, timestamp, kind, title, payload_json, redaction_level
                ) VALUES (?, datetime('now'), ?, ?, ?, ?)
                """,
                (
                    memory_session_id,
                    "system",
                    "page_start",
                    json.dumps(metadata, ensure_ascii=False),
                    "none",
                ),
            )
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            logger.exception("Failed to create SimpleMem lesson session")
            raise
        return memory_session_id

    def record_turn(
        self,
        *,
        student_id: str,
        content_session_id: str,
        memory_session_id: str,
        learner_input: str,
        prior_state: LessonRuntimeState,
        result: LessonTurnResult,
        page: PageLessonRecord,
        block: TeachingBlockRecord,
    ) -> list[LessonMemoryCandidate]:
        self._ensure_session_exists(
            student_id=student_id,
            content_session_id=content_session_id,
            memory_session_id=memory_session_id,
        )
        payload = {
            "page_uid": result.page_uid,
            "block_uid": result.block_uid,
            "turn_label": result.turn_label,
            "teaching_action": result.teaching_action,
            "retrieval_mode": result.retrieval_mode,
            "evaluation": result.evaluation,
            "learner_input": learner_input,
            "teacher_response": result.teacher_response,
        }
        try:
            self.conn.execute(
                """
                INSERT INTO session_events (
                    memory_session_id, timestamp, kind, title, payload_json, redaction_level
                ) VALUES (?, datetime('now'), ?, ?, ?, ?)
                """,
                (
                    memory_session_id,
                    "note",
                    f"lesson_turn:{result.turn_label}",
                    json.dumps(payload, ensure_ascii=False),
                    "none",
                ),
            )
            candidates = distill_lesson_memory_candidates(
                learner_input=learner_input,
                prior_state=prior_state,
                result=result,
                page=page,
                block=block,
            )
            for candidate in candidates:
                if self._observation_exists(
                    memory_session_id=memory_session_id,
                    title=candidate.title,
                ):
                    continue
                cursor = self.conn.execute(
                    """
                    INSERT INTO observations (
                        memory_session_id, timestamp, type, title, subtitle, facts_json,
                        narrative, concepts_json, files_json, vector_ref
                    ) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory_session_id,
                        candidate.observation_type,
                        candidate.title,
                        candidate.subtitle,
                        json.dumps(
                            self._storage_facts(candidate),
                            ensure_ascii=False,
                        ),
                        candidate.narrative,
                        json.dumps(candidate.concepts, ensure_ascii=False),
                        json.dumps(candidate.files, ensure_ascii=False),
                        None,
                    ),
                )
                obs_id = int(cursor.lastrowid or 0)
                self._store_semantic_entry(
                    candidate=candidate,
                    student_id=student_id,
                    memory_session_id=memory_session_id,
                    observation_id=obs_id,
                    page=page,
                    block=block,
                )
            self.conn.commit()
            return candidates
        except sqlite3.Error:
            self.conn.rollback()
            logger.exception("Failed to write lesson trace into SimpleMem-Cross")
            raise

    def summarize_session(
        self,
        *,
        memory_session_id: str,
        page: PageLessonRecord,
        state: LessonRuntimeState,
    ) -> bool:
        if self._summary_exists(memory_session_id):
            return False
        observations = self.conn.execute(
            """
            SELECT title, facts_json FROM observations
            WHERE memory_session_id = ?
            ORDER BY timestamp ASC
            """,
            (memory_session_id,),
        ).fetchall()
        if not observations:
            return False

        latest_by_kind: dict[str, str] = {}
        for row in observations:
            facts = self._parse_json(row["facts_json"])
            kind = str(facts.get("candidate_kind", "")).strip()
            title = str(row["title"]).strip()
            if kind and title:
                latest_by_kind[kind] = _render_summary_title_from_facts(
                    kind=kind,
                    title=title,
                    facts=facts,
                )

        learned = latest_by_kind.get("mistake")
        completed = latest_by_kind.get("mastery")
        next_steps = latest_by_kind.get("preference")
        if not (learned or completed or next_steps):
            return False

        investigated = (
            f"Practiced {page.page_uid} ({page.page_type}) with recent turns: "
            + ", ".join(state.recent_turn_labels[-3:])
        )
        try:
            self.conn.execute(
                """
                INSERT INTO session_summaries (
                    memory_session_id, timestamp, request, investigated,
                    learned, completed, next_steps, vector_ref
                ) VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_session_id,
                    f"Practice lesson page {page.page_uid}",
                    investigated,
                    learned,
                    completed,
                    next_steps,
                    None,
                ),
            )
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            logger.exception("Failed to store lesson summary in SimpleMem-Cross")
            raise
        return True

    def finalize_session(self, *, memory_session_id: str) -> None:
        try:
            self.conn.execute(
                """
                UPDATE sessions
                SET status = ?, ended_at = datetime('now')
                WHERE memory_session_id = ?
                """,
                ("completed", memory_session_id),
            )
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            logger.exception("Failed to finalize SimpleMem lesson session")
            raise

    def _configure_connection(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=NORMAL")

    def _run_migrations(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                content_session_id TEXT UNIQUE NOT NULL,
                memory_session_id TEXT UNIQUE NOT NULL,
                project TEXT NOT NULL,
                user_prompt TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT CHECK(status IN ('active', 'completed', 'failed')) DEFAULT 'active',
                metadata_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS session_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                kind TEXT CHECK(kind IN ('message', 'tool_use', 'file_change', 'note', 'system')) NOT NULL,
                title TEXT,
                payload_json TEXT,
                redaction_level TEXT DEFAULT 'none',
                FOREIGN KEY(memory_session_id) REFERENCES sessions(memory_session_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS observations (
                obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT CHECK(type IN ('decision', 'bugfix', 'feature', 'refactor', 'discovery', 'change')) NOT NULL,
                title TEXT NOT NULL,
                subtitle TEXT,
                facts_json TEXT,
                narrative TEXT,
                concepts_json TEXT,
                files_json TEXT,
                vector_ref TEXT,
                FOREIGN KEY(memory_session_id) REFERENCES sessions(memory_session_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS session_summaries (
                summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                request TEXT,
                investigated TEXT,
                learned TEXT,
                completed TEXT,
                next_steps TEXT,
                vector_ref TEXT,
                FOREIGN KEY(memory_session_id) REFERENCES sessions(memory_session_id) ON DELETE CASCADE
            )
            """,
        ]
        index_statements = [
            "CREATE INDEX IF NOT EXISTS idx_sessions_content_id ON sessions(content_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_memory_id ON sessions(memory_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(memory_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_summaries_session ON session_summaries(memory_session_id)",
        ]
        cursor = self.conn.cursor()
        for statement in statements:
            cursor.execute(statement)
        for statement in index_statements:
            cursor.execute(statement)
        self.conn.commit()

    def _ensure_session_exists(
        self,
        *,
        student_id: str,
        content_session_id: str,
        memory_session_id: str,
    ) -> None:
        scoped_content_session_id = self._scope_content_session_id(
            student_id=student_id,
            content_session_id=content_session_id,
        )
        row = self.conn.execute(
            """
            SELECT 1 FROM sessions
            WHERE memory_session_id = ? AND tenant_id = ? AND project = ?
              AND content_session_id IN (?, ?)
            LIMIT 1
            """,
            (
                memory_session_id,
                student_id,
                self.project,
                scoped_content_session_id,
                content_session_id,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                "SimpleMem lesson session is missing. start_page should bind a session first."
            )

    def _observation_exists(self, *, memory_session_id: str, title: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM observations
            WHERE memory_session_id = ? AND title = ?
            LIMIT 1
            """,
            (memory_session_id, title),
        ).fetchone()
        return row is not None

    def _summary_exists(self, memory_session_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM session_summaries
            WHERE memory_session_id = ?
            LIMIT 1
            """,
            (memory_session_id,),
        ).fetchone()
        return row is not None

    def _parse_json(self, value: Any) -> dict[str, Any]:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _storage_facts(self, candidate: LessonMemoryCandidate) -> dict[str, Any]:
        return {
            **candidate.facts,
            "candidate_kind": candidate.candidate_kind,
            "memory_layer": candidate.memory_layer,
            "promotion_policy": (
                "episode_to_fact_after_repeated_supported_progress"
                if candidate.memory_layer == "episode"
                else "procedure_reused_when_repeated_or_current_scope_matches"
            ),
        }

    def _store_semantic_entry(
        self,
        *,
        candidate: LessonMemoryCandidate,
        student_id: str,
        memory_session_id: str,
        observation_id: int,
        page: "PageLessonRecord",
        block: "TeachingBlockRecord",
    ) -> None:
        if self.semantic_store is None or observation_id <= 0:
            return
        importance = {
            "mistake": 0.85,
            "preference": 0.8,
            "mastery": 0.72,
        }[candidate.candidate_kind]
        entry = LessonSemanticMemoryEntry(
            entry_id=f"lesson-{memory_session_id}-{candidate.candidate_kind}-{observation_id}",
            lossless_restatement=candidate.title,
            keywords=self._build_keywords(candidate, page, block),
            timestamp="",
            location=page.page_uid,
            persons=[],
            entities=list(dict.fromkeys(candidate.concepts)),
            topic=candidate.candidate_kind,
            tenant_id=build_semantic_tenant_namespace(
                project=self.project,
                student_id=student_id,
            ),
            memory_session_id=memory_session_id,
            source_kind="lesson_trace",
            source_id=observation_id,
            importance=importance,
        )
        try:
            self.semantic_store.add_entries([entry])
        except Exception as exc:
            logger.warning("SimpleMem semantic writeback failed: %s", exc)

    def _build_keywords(
        self,
        candidate: LessonMemoryCandidate,
        page: "PageLessonRecord",
        block: "TeachingBlockRecord",
    ) -> list[str]:
        keywords = [
            candidate.candidate_kind,
            page.page_uid,
            block.block_uid,
            block.block_type,
            *candidate.concepts,
        ]
        return list(dict.fromkeys(value for value in keywords if value))

    def _scope_content_session_id(
        self,
        *,
        student_id: str,
        content_session_id: str,
    ) -> str:
        return f"{self.project}::{student_id}::{content_session_id}"


def distill_lesson_memory_candidates(
    *,
    learner_input: str,
    prior_state: LessonRuntimeState,
    result: LessonTurnResult,
    page: PageLessonRecord,
    block: TeachingBlockRecord,
) -> list[LessonMemoryCandidate]:
    """Deterministically convert one lesson turn into small memory candidates."""

    model_answer = _best_model_answer(block)
    shared_facts = {
        "page_uid": page.page_uid,
        "block_uid": block.block_uid,
        "block_type": block.block_type,
        "turn_label": result.turn_label,
        "teaching_action": result.teaching_action,
        "evaluation": result.evaluation,
        "model_answer": model_answer,
        "same_goal_attempt_count": prior_state.same_goal_attempt_count,
    }
    shared_concepts = list(dict.fromkeys([*block.focus_vocabulary[:2], *block.core_patterns[:1]]))
    candidates: list[LessonMemoryCandidate] = []

    if result.turn_label == "answer_question" and result.evaluation in {
        "partially_correct",
        "incorrect",
        "off_topic",
        "unclear",
    }:
        reason = {
            "partially_correct": "only gives part of the target answer",
            "incorrect": "still struggles to use the full target answer",
            "off_topic": "goes off-topic instead of using the target answer",
            "unclear": "cannot produce a clear target answer yet",
        }[result.evaluation]
        candidates.append(
            LessonMemoryCandidate(
                candidate_kind="mistake",
                memory_layer="episode",
                observation_type="discovery",
                title=f"Learner struggles to answer with '{model_answer}' independently.",
                subtitle=f"{page.page_uid} / {block.block_type}",
                narrative=(
                    f"During {page.page_uid}, the learner answered '{learner_input}' and {reason}."
                ),
                facts={
                    **shared_facts,
                    "candidate_kind": "mistake",
                    "mistake_focus": _infer_mistake_focus(
                        learner_input=learner_input,
                        model_answer=model_answer,
                        evaluation=result.evaluation,
                    ),
                },
                concepts=shared_concepts,
                files=[page.page_uid],
            )
        )

    preference_key = _infer_preference_key(learner_input)
    preference = _render_preference_title(preference_key)
    if preference is not None:
        candidates.append(
            LessonMemoryCandidate(
                candidate_kind="preference",
                memory_layer="procedure",
                observation_type="decision",
                title=preference,
                subtitle=f"{page.page_uid} / {result.turn_label}",
                narrative=(
                    f"The learner asked '{learner_input}' while working on {page.page_uid}."
                ),
                facts={
                    **shared_facts,
                    "candidate_kind": "preference",
                    "preference_key": preference_key,
                },
                concepts=shared_concepts,
                files=[page.page_uid],
            )
        )

    if (
        result.turn_label == "answer_question"
        and result.teaching_action == "confirm"
        and result.evaluation in {"correct", "acceptable"}
        and (prior_state.same_goal_attempt_count > 0 or not block.next_block_uids)
    ):
        candidates.append(
            LessonMemoryCandidate(
                candidate_kind="mastery",
                memory_layer="episode",
                observation_type="change",
                title=f"Learner can now answer '{model_answer}' correctly.",
                subtitle=f"{page.page_uid} / {block.block_type}",
                narrative=(
                    f"After practice on {page.page_uid}, the learner completed the target answer '{model_answer}'."
                ),
                facts={**shared_facts, "candidate_kind": "mastery"},
                concepts=shared_concepts,
                files=[page.page_uid],
            )
        )

    return candidates


def _render_summary_title_from_facts(
    *,
    kind: str,
    title: str,
    facts: dict[str, Any],
) -> str:
    model_answer = str(facts.get("model_answer", "")).strip()
    if kind == "mistake" and model_answer:
        mistake_focus = str(facts.get("mistake_focus", "")).strip().casefold()
        if mistake_focus == "missing_full_pattern":
            return f'Learner still needs the full sentence "{model_answer}"'
        if mistake_focus == "off_topic_answer":
            return f'Learner needs to stay on the target sentence "{model_answer}"'
        if mistake_focus == "unclear_answer":
            return f'Learner still cannot produce "{model_answer}" clearly'
        return f'Learner still needs the target sentence "{model_answer}"'
    if kind == "preference":
        preference_key = str(facts.get("preference_key", "")).strip()
        canonical_preference = _render_preference_title(preference_key)
        if canonical_preference:
            return canonical_preference
    if kind == "mastery" and model_answer:
        return f'Learner can now answer "{model_answer}" correctly'
    return title


def build_simplemem_writeback_adapter_from_env(
    *,
    semantic_store: SimpleMemLanceVectorStore | None = None,
) -> SimpleMemSQLiteLessonMemoryWriter | None:
    """Create the writeback adapter from env settings."""

    enabled = os.getenv("PEPTUTOR_SIMPLEMEM_WRITEBACK")
    if enabled is None or enabled.strip().casefold() not in {"1", "true", "yes", "on"}:
        return None

    db_path = os.getenv("PEPTUTOR_SIMPLEMEM_CROSS_DB_PATH")
    if not db_path:
        db_path = str(Path.home() / ".simplemem-cross" / "cross_memory.db")

    project = os.getenv("PEPTUTOR_SIMPLEMEM_PROJECT", "peptutor-lesson")
    return SimpleMemSQLiteLessonMemoryWriter(
        db_path=db_path,
        project=project,
        semantic_store=semantic_store,
    )


def _infer_preference_key(learner_input: str) -> str | None:
    lowered = learner_input.casefold()
    if any(token in learner_input for token in _PREFERENCE_CHINESE_TOKENS):
        return "chinese_explanation"
    if any(token in lowered for token in _PREFERENCE_SLOW_TOKENS):
        return "slow_split_practice"
    return None


def _render_preference_title(preference_key: str | None) -> str | None:
    if preference_key is None:
        return None
    return _PREFERENCE_TEXT_BY_KEY.get(preference_key)


def _infer_mistake_focus(
    *,
    learner_input: str,
    model_answer: str,
    evaluation: str | None,
) -> str:
    if evaluation == "off_topic":
        return "off_topic_answer"
    if evaluation == "unclear":
        return "unclear_answer"
    learner_tokens = _tokenize(learner_input)
    model_tokens = _tokenize(model_answer)
    if learner_tokens and model_tokens and set(learner_tokens).issubset(set(model_tokens)):
        return "missing_full_pattern"
    return "wrong_target_pattern"


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", normalize_text(value))


def _best_model_answer(block: TeachingBlockRecord) -> str:
    if block.allowed_answer_scope:
        return block.allowed_answer_scope[0]
    if block.core_patterns:
        return block.core_patterns[0]
    return block.teaching_goal
