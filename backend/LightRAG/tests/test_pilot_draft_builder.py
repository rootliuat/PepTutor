from pathlib import Path

import pytest

from lightrag.orchestrator.pilot_draft_builder import (
    build_pilot_draft,
    default_pilot_draft_output_path,
)
from lightrag.orchestrator.raw_curriculum import normalize_textbook_source


def _raw_root() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "app" / "knowledge" / "raw"
    ).resolve()


def test_build_pilot_draft_from_real_g5_s1_u3_pages():
    normalized_pages = normalize_textbook_source(_raw_root() / "01.五年级上册语料.js")
    selected_pages = [
        page
        for page in normalized_pages
        if page.grade == "G5"
        and page.semester == "S1"
        and page.unit == "U3"
        and page.page in {24, 25}
    ]

    draft = build_pilot_draft(selected_pages, pilot_id="g5s1u3-draft")

    assert draft.pilot_id == "g5s1u3-draft"
    assert draft.scope.grade == "G5"
    assert draft.scope.semester == "S1"
    assert draft.scope.unit == "U3"
    assert draft.scope.pages == [24, 25]
    assert draft.source_files == [
        "raw_textbook_g5s1_unit3",
        "raw_wordlist_g5s1",
        "raw_useful_expressions_g5s1",
    ]
    target_uids = [item["target_uid"] for item in draft.learning_targets]
    atom_uids = [item["atom_uid"] for item in draft.knowledge_atoms]
    assert target_uids == [
        "LT-G5S1U3-P24-pattern-what-would-you-like-to-eat",
        "LT-G5S1U3-P24-pattern-what-would-you-like-to-drink",
        "LT-G5S1U3-P24-word-hungry",
        "LT-G5S1U3-P24-answer-id-like",
        "LT-G5S1U3-P24-dialogue-food-drink-roleplay",
        "LT-G5S1U3-P24-listening-food-keywords",
        "LT-G5S1U3-P25-word-sandwich",
        "LT-G5S1U3-P25-word-salad",
        "LT-G5S1U3-P25-word-hamburger",
        "LT-G5S1U3-P25-word-tea",
        "LT-G5S1U3-P25-pattern-id-like",
        "LT-G5S1U3-P25-roleplay-ordering",
    ]
    assert atom_uids == [
        "KA-G5S1U3-word-hungry",
        "KA-G5S1U3-word-sandwich",
        "KA-G5S1U3-word-salad",
        "KA-G5S1U3-word-hamburger",
        "KA-G5S1U3-word-tea",
        "KA-G5S1U3-pattern-order-eat",
        "KA-G5S1U3-pattern-order-drink",
        "KA-G5S1U3-pattern-id-like",
    ]
    listening_target = next(
        item
        for item in draft.learning_targets
        if item["target_uid"] == "LT-G5S1U3-P24-listening-food-keywords"
    )
    roleplay_target = next(
        item
        for item in draft.learning_targets
        if item["target_uid"] == "LT-G5S1U3-P25-roleplay-ordering"
    )
    sandwich_atom = next(
        item for item in draft.knowledge_atoms if item["atom_uid"] == "KA-G5S1U3-word-sandwich"
    )
    eat_pattern_atom = next(
        item for item in draft.knowledge_atoms if item["atom_uid"] == "KA-G5S1U3-pattern-order-eat"
    )
    assert listening_target["mastery_signal_examples"] == {
        "mastered": "Learner catches both target words from the word bank.",
        "shaky": "Learner catches one target word only.",
        "not_mastered": "Learner cannot identify the food words.",
    }
    assert roleplay_target["mastery_signal_examples"] == {
        "mastered": "Learner completes a basic waiter-customer exchange.",
        "shaky": "Learner completes one turn but not the whole exchange.",
        "not_mastered": "Learner cannot role-play without full imitation.",
    }
    assert sandwich_atom == {
        "atom_uid": "KA-G5S1U3-word-sandwich",
        "atom_type": "word",
        "text": "sandwich",
        "gloss": "a sandwich item",
        "linked_blocks": [
            "TB-G5S1U3-P24-D2",
            "TB-G5S1U3-P25-D1",
            "TB-G5S1U3-P25-D2",
        ],
    }
    assert eat_pattern_atom == {
        "atom_uid": "KA-G5S1U3-pattern-order-eat",
        "atom_type": "sentence_pattern",
        "text": "What would you like to eat?",
        "linked_blocks": [
            "TB-G5S1U3-P24-D2",
            "TB-G5S1U3-P24-D3",
            "TB-G5S1U3-P25-D2",
            "TB-G5S1U3-P25-D3",
        ],
    }

    page24 = next(page for page in draft.page_lessons if page.page_uid == "TB-G5S1U3-P24")
    page25 = next(page for page in draft.page_lessons if page.page_uid == "TB-G5S1U3-P25")
    assert page24.page_type == "dialogue"
    assert page24.entry_probe_questions == [
        "What does hungry mean?",
        "Can you say: What would you like to eat?",
    ]
    assert page24.assumed_prior_knowledge == [
        {
            "topic": "basic food words and need-state language from earlier grades",
            "source": "grade_level_default",
            "confidence": "low",
            "verification_status": "unverified",
            "verify_by_block_uid": "TB-G5S1U3-P24-D2",
            "learning_target_uids": [
                "LT-G5S1U3-P24-pattern-what-would-you-like-to-eat",
                "LT-G5S1U3-P24-pattern-what-would-you-like-to-drink",
                "LT-G5S1U3-P24-word-hungry",
            ],
        }
    ]
    assert page24.priority_blocks == [
        "TB-G5S1U3-P24-D2",
        "TB-G5S1U3-P24-D3",
        "TB-G5S1U3-P24-D4",
        "TB-G5S1U3-P24-D1",
    ]
    assert (
        page24.page_intro_cn
        == "This page teaches ordering food and drinks. The teacher should first check whether the learner understands hungry and the two core questions."
    )
    assert page25.page_type == "vocabulary"
    assert (
        page25.page_intro_cn
        == "This page teaches food and drink words, then uses I'd like ... for ordering."
    )
    assert page25.entry_probe_questions == [
        "Do you know the word sandwich?",
        "Can you say: I'd like a sandwich, please?",
    ]
    assert page25.assumed_prior_knowledge == [
        {
            "topic": "page 24 ordering frame with I'd like answers",
            "source": "unit_progression",
            "confidence": "medium",
            "verification_status": "unverified",
            "verify_by_block_uid": "TB-G5S1U3-P25-D2",
            "learning_target_uids": [
                "LT-G5S1U3-P25-pattern-id-like",
                "LT-G5S1U3-P25-word-sandwich",
            ],
        }
    ]

    block_d1 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P24-D1"
    )
    block_d2 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P24-D2"
    )
    block_p25_d1 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P25-D1"
    )
    block_p25_d2 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P25-D2"
    )
    block_p24_d3 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P24-D3"
    )
    block_p24_d4 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P24-D4"
    )
    block_d3 = next(
        block for block in draft.teaching_blocks if block.block_uid == "TB-G5S1U3-P25-D3"
    )

    assert block_d1.block_type == "listening_probe"
    assert block_d1.focus_vocabulary == ["bread", "noodles", "chicken"]
    assert block_d1.core_patterns == ["She would like some ... and ..."]
    assert block_d1.allowed_answer_scope == [
        "bread and noodles",
        "She would like some bread and noodles.",
    ]
    assert block_d1.entry_probe_questions == ["Can you hear bread and noodles clearly?"]
    assert block_d1.next_block_uids == []
    assert block_d1.source_refs == ["TB-G5S1U3-P24-D1"]
    assert block_d1.learning_target_uids == ["LT-G5S1U3-P24-listening-food-keywords"]
    assert block_d1.repair_modes == ["repeat", "choice_probe", "asr_clarify"]
    assert block_d1.teaching_goal == "Catch key food words from a short listening task."
    assert (
        block_d1.teaching_summary
        == "Listen for what Sarah would like to eat and fill the blank from a small word bank."
    )
    assert block_d2.focus_vocabulary == ["hungry", "drink", "water", "thirsty", "sandwich"]
    assert block_d2.core_patterns == [
        "What would you like to eat?",
        "What would you like to drink?",
        "I'd like some water.",
    ]
    assert block_d2.allowed_answer_scope == [
        "A sandwich, please.",
        "I'd like some water.",
        "I am hungry.",
        "I'm hungry.",
    ]
    assert block_d2.entry_probe_questions == [
        "What does hungry mean?",
        "Can you repeat: What would you like to eat?",
    ]
    assert block_d2.learning_target_uids == [
        "LT-G5S1U3-P24-pattern-what-would-you-like-to-eat",
        "LT-G5S1U3-P24-pattern-what-would-you-like-to-drink",
        "LT-G5S1U3-P24-word-hungry",
    ]
    assert block_d2.return_anchors == [
        "What would you like to eat?",
        "What would you like to drink?",
        "I'd like some water.",
    ]
    assert block_d2.next_block_uids == [
        "TB-G5S1U3-P24-D3",
        "TB-G5S1U3-P24-D4",
        "TB-G5S1U3-P24-D1",
    ]
    assert block_d2.branchable_topics == ["food", "drink", "restaurant", "hungry", "thirsty"]
    assert (
        block_d2.teaching_goal
        == "Understand and say the core ordering questions for food and drink."
    )
    assert (
        block_d2.teaching_summary
        == "Family ordering dialogue with hungry and thirsty cues, plus two target questions about food and drink."
    )
    assert block_p24_d3.core_patterns == [
        "What would you like to eat?",
        "I'd like ...",
    ]
    assert block_p24_d3.focus_vocabulary == [
        "chicken and bread",
        "rice and vegetables",
    ]
    assert block_p24_d3.allowed_answer_scope == [
        "I'd like chicken and bread.",
        "I'd like rice and vegetables.",
    ]
    assert block_p24_d3.entry_probe_questions == [
        "If I ask What would you like to eat, how do you answer?"
    ]
    assert block_p24_d3.next_block_uids == ["TB-G5S1U3-P24-D4", "TB-G5S1U3-P24-D1"]
    assert block_p24_d3.branchable_topics == ["restaurant", "food choice"]
    assert block_p24_d3.learning_target_uids == [
        "LT-G5S1U3-P24-answer-id-like",
    ]
    assert (
        block_p24_d3.teaching_goal
        == "Answer the food question with a short ordering sentence."
    )
    assert (
        block_p24_d3.teaching_summary
        == "Continue the ordering exchange with food choices and answer the eat question with I'd like ...."
    )
    assert block_p24_d4.core_patterns == [
        "What would you like to drink?",
        "I'd like ...",
    ]
    assert block_p24_d4.focus_vocabulary == [
        "water",
        "tea",
    ]
    assert block_p24_d4.allowed_answer_scope == [
        "I'd like water.",
        "I'd like some tea.",
    ]
    assert block_p24_d4.entry_probe_questions == [
        "If I ask What would you like to drink, how do you answer?"
    ]
    assert block_p24_d4.next_block_uids == ["TB-G5S1U3-P24-D1"]
    assert block_p24_d4.branchable_topics == ["restaurant", "drink choice"]
    assert block_p24_d4.learning_target_uids == [
        "LT-G5S1U3-P24-dialogue-food-drink-roleplay",
    ]
    assert (
        block_p24_d4.teaching_goal
        == "Answer the drink question with a short ordering sentence."
    )
    assert (
        block_p24_d4.teaching_summary
        == "Practice drink choices with a small word bank and answer the drink question with I'd like ...."
    )
    assert block_p25_d1.branchable_topics == [
        "sandwich",
        "hamburger",
        "salad",
        "tea",
    ]
    assert block_p25_d1.focus_vocabulary == [
        "tea",
        "ice cream",
        "sandwich",
        "hamburger",
        "salad",
    ]
    assert block_p25_d1.allowed_answer_scope == [
        "sandwich",
        "hamburger",
        "salad",
        "ice cream",
        "tea",
    ]
    assert block_p25_d1.entry_probe_questions == ["Do you know salad?", "Can you read sandwich?"]
    assert block_p25_d1.learning_target_uids == [
        "LT-G5S1U3-P25-word-sandwich",
        "LT-G5S1U3-P25-word-salad",
        "LT-G5S1U3-P25-word-hamburger",
        "LT-G5S1U3-P25-word-tea",
    ]
    assert block_p25_d1.teaching_goal == "Recognize and say the core food and drink words on the page."
    assert (
        block_p25_d1.teaching_summary
        == "A restaurant scene introduces tea, ice cream, sandwich, hamburger, and salad."
    )
    assert block_p25_d2.block_type == "sentence_pattern_practice"
    assert block_p25_d2.repair_modes == ["slow_read", "word_drill", "sentence_drill"]
    assert block_p25_d2.focus_vocabulary == ["I'd like", "sandwich", "please"]
    assert block_p25_d2.allowed_answer_scope == [
        "I'd like a sandwich, please.",
        "I'd like a hamburger, please.",
        "I'd like some tea, please.",
    ]
    assert block_p25_d2.entry_probe_questions == ["Can you say: I'd like a sandwich, please?"]
    assert block_p25_d2.branchable_topics == ["polite order", "restaurant"]
    assert block_p25_d2.return_anchors == ["I'd like a sandwich, please.", "I'd like ..."]
    assert block_p25_d2.teaching_goal == "Use I'd like ... to order one food item politely."
    assert block_p25_d2.teaching_summary == "Short model dialogue for ordering a sandwich with please."
    assert block_d3.block_type == "roleplay_task"
    assert block_d3.repair_modes == ["choice_probe", "word_drill", "sentence_drill"]
    assert block_d3.focus_vocabulary == ["waiter", "customer", "tea", "sandwich", "hamburger"]
    assert block_d3.core_patterns == [
        "What would you like to eat?",
        "What would you like to drink?",
        "I'd like ...",
    ]
    assert block_d3.allowed_answer_scope == [
        "I'd like a sandwich and some tea.",
        "I'd like a hamburger and some tea.",
    ]
    assert block_d3.entry_probe_questions == ["If you are the customer, what would you order?"]
    assert block_d3.learning_target_uids == ["LT-G5S1U3-P25-roleplay-ordering"]
    assert (
        block_d3.teaching_goal
        == "Role-play waiter and customer with one food item and one drink item."
    )
    assert (
        block_d3.teaching_summary
        == "Restaurant role-play with a small order form and food-plus-drink output."
    )


def test_build_pilot_draft_rejects_mixed_scope_pages():
    normalized_pages = normalize_textbook_source(_raw_root() / "01.五年级上册语料.js")
    mixed_pages = [
        page
        for page in normalized_pages
        if (page.unit == "U3" and page.page == 24) or (page.unit == "U4" and page.page == 36)
    ]

    with pytest.raises(ValueError, match="share one grade/semester/unit scope"):
        build_pilot_draft(mixed_pages, pilot_id="mixed")


def test_default_pilot_draft_output_path_uses_structured_drafts_dir(tmp_path):
    output_path = default_pilot_draft_output_path(
        "g5s1u3 p24/p25 draft",
        repo_root=tmp_path,
    )

    assert output_path == (
        tmp_path / "app/knowledge/structured/drafts/g5s1u3-p24-p25-draft.json"
    ).resolve()


def test_default_pilot_draft_output_path_resolves_real_repo_root():
    output_path = default_pilot_draft_output_path("repo-check")

    assert output_path == (
        Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/drafts/repo-check.json"
    ).resolve()
