"""Render a human-readable Chinese overview from the PepTutor curriculum map."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from lightrag.orchestrator.curriculum_map_builder import (
    CurriculumBookEntry,
    CurriculumMapFile,
    CurriculumUnitEntry,
)

_BOOK_LABELS = {
    ("G5", "S1"): "五年级上册",
    ("G5", "S2"): "五年级下册",
    ("G6", "S1"): "六年级上册",
    ("G6", "S2"): "六年级下册",
}

_PAGE_TYPE_LABELS = {
    "dialogue": "对话",
    "assessment": "检测",
    "grammar": "语法",
    "listening": "听力",
    "phonics": "语音",
    "picture": "看图表达",
    "practice": "练习",
    "reading": "阅读",
    "review": "复习",
    "story": "故事",
    "task": "任务",
    "vocabulary": "词汇",
    "writing": "写作",
    "picture_scene": "看图表达",
    "wrap_up": "复习总结",
    "unknown": "未分类",
}


def build_curriculum_overview(
    curriculum_map: CurriculumMapFile,
    *,
    max_vocabulary: int = 12,
    max_patterns: int = 8,
    max_targets: int = 4,
    max_sources: int = 4,
) -> str:
    """Build a compact Chinese Markdown overview from a curriculum map."""
    lines = [
        "# PepTutor 教材中文总览",
        "",
        "> 本文档由 `app/knowledge/structured/curriculum-map.json` 自动导出，",
        "> 用于人工查看教材结构；运行时仍使用结构化 map 和逐页 evidence。",
        "",
        f"- 地图版本：`{curriculum_map.map_id}`",
        f"- 生成时间：`{curriculum_map.generated_at}`",
        f"- 覆盖范围：{curriculum_map.book_count} 本书，"
        f"{curriculum_map.scope_count} 个单元/复习单元，"
        f"{curriculum_map.page_count} 页，"
        f"{curriculum_map.block_count} 个 teaching block",
        f"- 数据来源：`{curriculum_map.source_manifest}`",
        "",
    ]

    for book in curriculum_map.books:
        lines.extend(
            _render_book(
                book,
                max_vocabulary=max_vocabulary,
                max_patterns=max_patterns,
                max_targets=max_targets,
                max_sources=max_sources,
            )
        )

    return "\n".join(lines).rstrip() + "\n"


def default_curriculum_overview_output_path(repo_root: Path | None = None) -> Path:
    """Return the checked human-readable overview output path."""
    root = repo_root.resolve() if repo_root is not None else _find_repo_root(Path(__file__))
    return (root / "app" / "knowledge" / "structured" / "curriculum-overview.zh.md").resolve()


def _render_book(
    book: CurriculumBookEntry,
    *,
    max_vocabulary: int,
    max_patterns: int,
    max_targets: int,
    max_sources: int,
) -> list[str]:
    book_label = _BOOK_LABELS.get((book.grade, book.semester), book.book_id)
    lines = [
        f"## {book_label}（{book.book_id}）",
        "",
        f"- 单元数量：{len(book.units)}",
        f"- 来源：{_format_refs(book.source_refs, max_sources=max_sources)}",
        "",
    ]
    for unit in book.units:
        lines.extend(
            _render_unit(
                unit,
                max_vocabulary=max_vocabulary,
                max_patterns=max_patterns,
                max_targets=max_targets,
                max_sources=max_sources,
            )
        )
    return lines


def _render_unit(
    unit: CurriculumUnitEntry,
    *,
    max_vocabulary: int,
    max_patterns: int,
    max_targets: int,
    max_sources: int,
) -> list[str]:
    theme = unit.unit_theme or "未提取到明确主题"
    lines = [
        f"### {unit.unit}：{theme}",
        "",
        f"- 页码：{_format_pages(unit.pages)}",
        f"- 单元主题：{theme}",
        "- 教学目标：",
        f"  - 围绕“{theme}”开展听、说、读、写练习。",
        f"  - 掌握并复现核心词汇：{_format_vocabulary(unit, max_items=max_vocabulary)}",
        f"  - 理解并运用核心句型/语法结构：{_format_items(unit.core_patterns, max_items=max_patterns)}",
        f"  - 完成页面任务：{_format_page_types(unit)}",
    ]

    targets = _format_targets(unit, max_items=max_targets)
    if targets:
        lines.extend(["- 结构化学习目标：", *[f"  - {target}" for target in targets]])

    lines.extend(
        [
            "- 知识点与语言材料：",
            f"  - 词汇学习：{_format_vocabulary(unit, max_items=max_vocabulary)}",
            f"  - 语法/句型：{_format_items(unit.core_patterns, max_items=max_patterns)}",
            f"  - 页面类型：{_format_page_types(unit)}",
            f"- 来源与置信度：{unit.confidence}；{_format_refs(unit.source_refs, max_sources=max_sources)}",
            "",
        ]
    )
    return lines


def _format_pages(pages: list[int]) -> str:
    if not pages:
        return "未标注"
    if len(pages) == 1:
        return f"P{pages[0]}"
    return f"P{min(pages)}-P{max(pages)}（共 {len(pages)} 页）"


def _format_vocabulary(unit: CurriculumUnitEntry, *, max_items: int) -> str:
    entries: list[str] = []
    for entry in unit.core_vocabulary[:max_items]:
        if entry.chinese:
            entries.append(f"{entry.word}（{entry.chinese}）")
        else:
            entries.append(entry.word)
    return _format_items(entries, max_items=max_items, total=len(unit.core_vocabulary))


def _format_items(
    items: list[str],
    *,
    max_items: int,
    total: int | None = None,
) -> str:
    clean_items = [item.strip() for item in items if item and item.strip()]
    if not clean_items:
        return "未提取到明确条目"
    shown = clean_items[:max_items]
    suffix = ""
    total_count = total if total is not None else len(clean_items)
    if total_count > len(shown):
        suffix = f" 等（共 {total_count} 项）"
    return "；".join(shown) + suffix


def _format_targets(unit: CurriculumUnitEntry, *, max_items: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for target in unit.learning_targets:
        text = target.text.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= max_items:
            break
    if len(unit.learning_targets) > len(result):
        result.append(f"其余 {len(unit.learning_targets) - len(result)} 条目标见结构化 map。")
    return result


def _format_page_types(unit: CurriculumUnitEntry) -> str:
    if not unit.page_types:
        return "未提取到页面类型"
    counts = Counter(page.page_type for page in unit.page_types)
    parts = []
    for page_type, count in sorted(counts.items()):
        label = _PAGE_TYPE_LABELS.get(page_type, page_type)
        parts.append(f"{label} × {count}")
    return "；".join(parts)


def _format_refs(source_refs: list[str], *, max_sources: int) -> str:
    if not source_refs:
        return "无来源引用"
    shown = [f"`{ref}`" for ref in source_refs[:max_sources]]
    suffix = ""
    if len(source_refs) > len(shown):
        suffix = f" 等（共 {len(source_refs)} 项）"
    return "；".join(shown) + suffix


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for ancestor in [current, *current.parents]:
        if (ancestor / "app" / "knowledge").exists():
            return ancestor
    raise FileNotFoundError("Unable to locate repository root containing app/knowledge")
