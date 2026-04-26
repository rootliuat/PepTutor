from pathlib import Path

from lightrag.orchestrator.curriculum_map_builder import build_curriculum_map
from lightrag.orchestrator.curriculum_overview_builder import (
    build_curriculum_overview,
    default_curriculum_overview_output_path,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _manifest_path() -> Path:
    return _repo_root() / "app/knowledge/structured/general/general-manifest.json"


def _raw_root() -> Path:
    return _repo_root() / "app/knowledge/raw"


def _curriculum_map():
    return build_curriculum_map(
        manifest_path=_manifest_path(),
        raw_root=_raw_root(),
        repo_root=_repo_root(),
        generated_at="2026-04-25T00:00:00+00:00",
    )


def test_curriculum_overview_renders_chinese_book_and_unit_sections():
    overview = build_curriculum_overview(
        _curriculum_map(),
        max_vocabulary=8,
        max_patterns=6,
        max_targets=3,
    )

    assert "# PepTutor 教材中文总览" in overview
    assert "## 五年级上册（G5S1）" in overview
    assert "## 六年级下册（G6S2）" in overview
    assert "### U5：Describing a room or place" in overview
    assert "- 教学目标：" in overview
    assert "词汇学习：above（在（或向）……上面）" in overview
    assert "There is a big bed." in overview
    assert "页面类型：" in overview
    assert "来源与置信度：high" in overview


def test_curriculum_overview_stays_derived_from_real_map_not_handwritten_examples():
    overview = build_curriculum_overview(
        _curriculum_map(),
        max_vocabulary=12,
        max_patterns=8,
        max_targets=3,
    )

    assert "### U1：What's he like?" in overview
    g5s1u1_section = overview.split("### U2：", 1)[0].split("### U1：", 1)[1]
    assert "old（老的；年纪大的）" in g5s1u1_section
    assert "What's she like?" in g5s1u1_section
    assert "pen（" not in g5s1u1_section
    assert "desk（" not in g5s1u1_section
    assert '"books"' not in overview
    assert '"units"' not in overview


def test_curriculum_overview_default_output_path():
    assert default_curriculum_overview_output_path(_repo_root()) == (
        _repo_root() / "app/knowledge/structured/curriculum-overview.zh.md"
    )
