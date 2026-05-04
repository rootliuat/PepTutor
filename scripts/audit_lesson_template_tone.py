#!/usr/bin/env python3
"""Audit template-like teacher phrasing in a captured lesson smoke report."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_KIND = "lesson_template_tone_audit"
DEFAULT_ARTIFACT_DIR = Path("temp/lesson-smoke-artifacts")


@dataclass(frozen=True)
class TonePattern:
    id: str
    label: str
    family: str
    verdict: str
    pattern: re.Pattern[str]
    rationale: str


TONE_PATTERNS: tuple[TonePattern, ...] = (
    TonePattern(
        id="now_step_practice",
        label="现在这一步先练 / 这一步先抓住",
        family="teacher_move",
        verdict="tone_watch",
        pattern=re.compile(r"现在这一步先练|这一步先练|这一步先抓住"),
        rationale="Valid repair move, but repeated wording can sound operational.",
    ),
    TonePattern(
        id="textbook_goal_pullback",
        label="先回到课本目标",
        family="guardrail",
        verdict="necessary_guardrail",
        pattern=re.compile(r"先回到课本目标|回到课本目标|回到刚才的小任务|回到课本"),
        rationale="Keeps vocabulary interruptions from drifting away from the current lesson.",
    ),
    TonePattern(
        id="read_sentence_prompt",
        label="把这句读出来",
        family="teacher_move",
        verdict="tone_watch",
        pattern=re.compile(r"把这句读出来|读出这句|你读这一句|读这一句"),
        rationale="Valid oral-classroom move; high repetition should be varied, not removed.",
    ),
    TonePattern(
        id="repeat_after_me",
        label="跟我读",
        family="teacher_move",
        verdict="tone_watch",
        pattern=re.compile(r"跟我读|跟(?:米粒|老师)一起说|跟我一起说|慢慢说"),
        rationale="Valid reading support; repeated use can make turns feel mechanical.",
    ),
    TonePattern(
        id="small_task_choice",
        label="这页先选一个小任务",
        family="guardrail",
        verdict="necessary_guardrail",
        pattern=re.compile(r"这页先选一个小任务|先选一个小任务"),
        rationale="Needed on multi-block pages so the learner chooses a route before content starts.",
    ),
    TonePattern(
        id="learning_entry_choice",
        label="先定学习入口 / 先定一个入口",
        family="guardrail",
        verdict="tone_watch",
        pattern=re.compile(r"先定学习入口|先定一个入口"),
        rationale="Module-choice guardrail; keep watching for operational phrasing.",
    ),
    TonePattern(
        id="learner_echo",
        label="你刚才说的是",
        family="guardrail",
        verdict="necessary_guardrail",
        pattern=re.compile(r"你刚才说的是|你说的是"),
        rationale="Clarifies what the learner said before a correction or pullback.",
    ),
    TonePattern(
        id="module_choice_entry",
        label="先选入口 / 你想先学哪一块",
        family="guardrail",
        verdict="necessary_guardrail",
        pattern=re.compile(r"先选入口|你想先学哪一块|可以说 第一块|先学哪一块"),
        rationale="Prevents multi-block pages from silently forcing the first block.",
    ),
)


def latest_smoke_report(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    reports = sorted(
        artifact_dir.glob("lesson_smoke_matrix_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise FileNotFoundError(f"No lesson_smoke_matrix_*.json found in {artifact_dir}")
    return reports[0]


def _as_text(value: Any) -> str:
    return str(value or "")


def _shorten(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


def _hit_record(
    *,
    pattern: TonePattern,
    match: re.Match[str],
    turn: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pattern_id": pattern.id,
        "label": pattern.label,
        "family": pattern.family,
        "verdict": pattern.verdict,
        "matched_text": match.group(0),
        "page_uid": _as_text(turn.get("page_uid")),
        "page_label": _as_text(turn.get("page_label")),
        "step": _as_text(turn.get("step")),
        "learner_input": turn.get("learner_input"),
        "teacherresponsesource": turn.get("teacherresponsesource"),
        "repair_reason": turn.get("repair_reason"),
        "route": turn.get("route"),
        "turn_label": turn.get("turn_label"),
        "teacher_response": _shorten(_as_text(turn.get("teacher_response"))),
    }


def find_hits(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for turn in turns:
        response = _as_text(turn.get("teacher_response"))
        if not response:
            continue
        for pattern in TONE_PATTERNS:
            match = pattern.pattern.search(response)
            if match:
                hits.append(_hit_record(pattern=pattern, match=match, turn=turn))
    return hits


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = _as_text(item.get(key)) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _pattern_summaries(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pattern: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        by_pattern.setdefault(str(hit["pattern_id"]), []).append(hit)

    summaries: list[dict[str, Any]] = []
    pattern_lookup = {pattern.id: pattern for pattern in TONE_PATTERNS}
    for pattern_id, pattern_hits in by_pattern.items():
        pattern = pattern_lookup[pattern_id]
        summaries.append(
            {
                "pattern_id": pattern.id,
                "label": pattern.label,
                "family": pattern.family,
                "verdict": pattern.verdict,
                "count": len(pattern_hits),
                "page_count": len({hit["page_uid"] for hit in pattern_hits}),
                "source_counts": _count_by(pattern_hits, "teacherresponsesource"),
                "repair_reason_counts": _count_by(pattern_hits, "repair_reason"),
                "rationale": pattern.rationale,
            }
        )
    return sorted(summaries, key=lambda item: (-int(item["count"]), str(item["pattern_id"])))


def _opening_summary(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for turn in turns:
        response = _as_text(turn.get("teacher_response")).strip()
        if not response:
            continue
        first_clause = re.split(r"[。！？\n]", response, maxsplit=1)[0].strip()
        first_clause = _shorten(first_clause, limit=80)
        if len(first_clause) < 6:
            continue
        record = counts.setdefault(
            first_clause,
            {
                "opening": first_clause,
                "count": 0,
                "pages": set(),
                "examples": [],
            },
        )
        record["count"] += 1
        record["pages"].add(_as_text(turn.get("page_uid")))
        if len(record["examples"]) < 3:
            record["examples"].append(
                {
                    "page_uid": turn.get("page_uid"),
                    "step": turn.get("step"),
                    "learner_input": turn.get("learner_input"),
                }
            )

    repeated = [
        {
            "opening": item["opening"],
            "count": item["count"],
            "page_count": len(item["pages"]),
            "examples": item["examples"],
        }
        for item in counts.values()
        if item["count"] > 1
    ]
    return sorted(repeated, key=lambda item: (-int(item["count"]), str(item["opening"])))


def _interpretation(pattern_summaries: list[dict[str, Any]]) -> list[str]:
    counts = {str(item["pattern_id"]): int(item["count"]) for item in pattern_summaries}
    notes: list[str] = []
    if counts.get("module_choice_entry", 0) or counts.get("small_task_choice", 0):
        notes.append(
            "模块选择文案属于必要护栏：它解决多 block 页强行进入第一块的问题，后续只需要压缩和变体化。"
        )
    if counts.get("learner_echo", 0) >= 10:
        notes.append(
            "“你刚才说的是”是纠偏锚点，但出现频率较高；下一刀可让修复层在 echo、确认、短回拉之间轮换。"
        )
    if counts.get("now_step_practice", 0) or counts.get("learning_entry_choice", 0):
        notes.append(
            "“现在这一步先练 / 这一步先抓住 / 先定一个入口”属于 tone_watch：不是功能 bug，但需要避免变成操作台口吻。"
        )
    if counts.get("repeat_after_me", 0) or counts.get("read_sentence_prompt", 0):
        notes.append(
            "“跟我读 / 把这句读出来”是合理课堂动作；问题不在动作本身，而在同一表达重复。"
        )
    if not notes:
        notes.append("未发现目标模板短语；保留当前课堂回复策略。")
    return notes


def audit_template_tone(
    *,
    smoke_report_path: Path,
    max_examples_per_pattern: int = 5,
) -> dict[str, Any]:
    payload = json.loads(smoke_report_path.read_text(encoding="utf-8"))
    turns = payload.get("turns") if isinstance(payload, dict) else None
    if not isinstance(turns, list):
        raise ValueError(f"{smoke_report_path} does not contain a turn list")

    hits = find_hits(turns)
    pattern_summaries = _pattern_summaries(hits)
    examples_by_pattern: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        examples = examples_by_pattern.setdefault(str(hit["pattern_id"]), [])
        if len(examples) < max_examples_per_pattern:
            examples.append(hit)

    summary = {
        "smoke_report_path": str(smoke_report_path),
        "page_count": len({_as_text(turn.get("page_uid")) for turn in turns}),
        "turn_count": len(turns),
        "hit_count": len(hits),
        "hit_count_definition": (
            "pattern-turn hits; one matched pattern contributes at most one hit per turn, "
            "not raw phrase occurrences"
        ),
        "turn_with_hits_count": len(
            {
                f"{hit['page_uid']}::{hit['step']}::{hit.get('learner_input')}"
                for hit in hits
            }
        ),
        "verdict_counts": _count_by(hits, "verdict"),
        "family_counts": _count_by(hits, "family"),
        "page_counts": _count_by(hits, "page_uid"),
    }
    return {
        "kind": REPORT_KIND,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "smoke_regression_set_id": payload.get("regression_set_id"),
        "smoke_summary": payload.get("summary", {}),
        "summary": summary,
        "pattern_summaries": pattern_summaries,
        "examples_by_pattern": dict(sorted(examples_by_pattern.items())),
        "repeated_openings": _opening_summary(turns)[:20],
        "interpretation": _interpretation(pattern_summaries),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Lesson Template Tone Audit",
        "",
        f"Generated: {report['generated_at']}",
        f"Smoke report: `{summary['smoke_report_path']}`",
        f"Regression set: `{report.get('smoke_regression_set_id')}`",
        "",
        "## Summary",
        "",
        f"- page_count: `{summary['page_count']}`",
        f"- turn_count: `{summary['turn_count']}`",
        f"- hit_count: `{summary['hit_count']}`",
        f"- hit_count_definition: {summary['hit_count_definition']}",
        f"- turn_with_hits_count: `{summary['turn_with_hits_count']}`",
        f"- verdict_counts: `{summary['verdict_counts']}`",
        f"- family_counts: `{summary['family_counts']}`",
        "",
        "## Interpretation",
        "",
    ]
    for note in report["interpretation"]:
        lines.append(f"- {note}")

    lines.extend(["", "## Pattern Counts", ""])
    if not report["pattern_summaries"]:
        lines.append("- none")
    else:
        lines.append("| pattern | count | pages | verdict | notes |")
        lines.append("|---|---:|---:|---|---|")
        for item in report["pattern_summaries"]:
            lines.append(
                "| "
                f"`{item['pattern_id']}` {item['label']} | "
                f"{item['count']} | {item['page_count']} | "
                f"{item['verdict']} | {item['rationale']} |"
            )

    lines.extend(["", "## Page Hotspots", ""])
    page_counts = summary["page_counts"]
    if not page_counts:
        lines.append("- none")
    else:
        for page_uid, count in list(page_counts.items())[:20]:
            lines.append(f"- `{page_uid}`: {count}")

    lines.extend(["", "## Examples", ""])
    examples_by_pattern = report["examples_by_pattern"]
    if not examples_by_pattern:
        lines.append("- none")
    else:
        for pattern_id, examples in examples_by_pattern.items():
            lines.append(f"### `{pattern_id}`")
            for example in examples:
                lines.append(
                    "- "
                    f"`{example['page_uid']}` {example['step']} "
                    f"input={example['learner_input']!r} "
                    f"source={example['teacherresponsesource']} "
                    f"repair={example['repair_reason']}: "
                    f"{example['teacher_response']}"
                )
            lines.append("")

    lines.extend(["## Repeated Openings", ""])
    if not report["repeated_openings"]:
        lines.append("- none")
    else:
        for item in report["repeated_openings"]:
            lines.append(
                f"- `{item['opening']}`: count={item['count']} pages={item['page_count']}"
            )
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"lesson_template_tone_audit_{stamp}.json"
    md_path = out_dir / f"lesson_template_tone_audit_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke-report",
        type=Path,
        default=None,
        help="Path to lesson_smoke_matrix_*.json. Defaults to the newest report.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--max-examples-per-pattern", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke_report_path = args.smoke_report or latest_smoke_report(args.out_dir)
    report = audit_template_tone(
        smoke_report_path=smoke_report_path,
        max_examples_per_pattern=args.max_examples_per_pattern,
    )
    json_path, md_path = write_report(report, args.out_dir)
    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "summary": report["summary"],
                "interpretation": report["interpretation"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
