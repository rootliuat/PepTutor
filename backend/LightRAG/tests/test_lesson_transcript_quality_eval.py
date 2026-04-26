from lightrag.orchestrator.lesson_transcript_quality_eval import (
    render_transcript_quality_report,
    score_lesson_transcript,
)


def _debug_signals(*, memory_buckets=None, speech_style="normal", motion="Explain"):
    return {
        "live_prompts": {"enabled": True},
        "prompt_memory": {
            "enabled": bool(memory_buckets),
            "injected_buckets": memory_buckets or [],
        },
        "persona": {
            "profile_id": "peptutor-teacher-v1",
            "airi_performance": {
                "speech_style": speech_style,
                "mouth_intensity": 0.7,
                "interrupt_policy": "barge_in_allowed",
                "content_source": "lesson_runtime_teacher_response",
                "fallback_allowed": True,
                "motion": motion,
            },
        },
    }


def _turn(
    *,
    name="turn",
    teacher_response="salad 是“沙拉”。我们回到刚才这句。",
    turn_label="ask_knowledge",
    teaching_action="explain",
    retrieval_mode="unit",
    retrieved_block_uids=None,
    elapsed_ms=1200,
    debug_signals=None,
    state=None,
):
    return {
        "name": name,
        "elapsed_ms": elapsed_ms,
        "payload": {
            "turn_label": turn_label,
            "teaching_action": teaching_action,
            "retrieval_mode": retrieval_mode,
            "teacher_response": teacher_response,
            "retrieved_block_uids": (
                ["TB-G5S1U3-P25-D1"]
                if retrieved_block_uids is None
                else retrieved_block_uids
            ),
            "state": state or {},
            "debug_signals": debug_signals if debug_signals is not None else _debug_signals(),
        },
    }


def test_transcript_quality_scores_live_route_turn_contracts():
    report = score_lesson_transcript(
        [
            _turn(name="knowledge"),
            _turn(
                name="help",
                teacher_response="没关系，我们先慢慢读 hungry。",
                turn_label="ask_help",
                retrieval_mode="none",
                retrieved_block_uids=[],
                debug_signals=_debug_signals(
                    memory_buckets=["common_mistakes"],
                    speech_style="slow_split",
                    motion="Encourage",
                ),
            ),
        ]
    )

    assert report.summary.turn_count == 2
    assert report.summary.strict_pass_count == 2
    assert report.summary.response_quality_rate == 1.0
    assert report.summary.retrieval_grounding_rate == 1.0
    assert report.summary.persona_signal_rate == 1.0
    assert report.summary.airi_performance_rate == 1.0
    assert report.summary.live_prompt_signal_rate == 1.0
    assert report.summary.prompt_memory_enabled_turn_count == 1
    assert report.summary.prompt_memory_bucket_turn_count == 1
    assert not report.failed_outcomes
    rendered = render_transcript_quality_report(report)
    assert "PASS" in rendered
    assert "not a pedagogical dialogue-quality score" in rendered


def test_transcript_quality_flags_robotic_or_ungrounded_turns():
    report = score_lesson_transcript(
        [
            _turn(
                name="bad knowledge",
                teacher_response="Key patterns: What would you like to eat?",
                retrieved_block_uids=[],
                debug_signals={"live_prompts": {"enabled": False}},
            ),
        ],
        max_latency_ms=100,
    )

    assert report.summary.strict_pass_count == 0
    assert report.failed_outcomes
    failure = report.failed_outcomes[0]
    assert "response has no Chinese scaffold" in failure.failure_reasons
    assert any("forbidden response phrases" in reason for reason in failure.failure_reasons)
    assert "ask_knowledge turn has no grounded retrieval hit" in failure.failure_reasons
    assert "persona/AIRI performance signal missing" in failure.failure_reasons
    assert "live prompt signal missing" in failure.failure_reasons
    assert "latency exceeded 100ms" in failure.failure_reasons


def test_transcript_quality_flags_incomplete_airi_performance_contract():
    report = score_lesson_transcript(
        [
            _turn(
                name="missing visible layer fields",
                debug_signals={
                    "live_prompts": {"enabled": True},
                    "persona": {
                        "profile_id": "peptutor-teacher-v1",
                        "airi_performance": {
                            "speech_style": "normal",
                            "motion": "Explain",
                        },
                    },
                },
            ),
        ]
    )

    assert report.summary.strict_pass_count == 0
    assert report.summary.persona_signal_rate == 1.0
    assert report.summary.airi_performance_rate == 0.0
    assert (
        "AIRI performance contract incomplete"
        in report.failed_outcomes[0].failure_reasons
    )


def test_transcript_quality_flags_non_adaptive_airi_speech_style():
    report = score_lesson_transcript(
        [
            _turn(
                name="incorrect correction performance plan",
                turn_label="answer_question",
                teaching_action="hint",
                retrieval_mode="none",
                retrieved_block_uids=[],
                debug_signals=_debug_signals(),
            ),
        ]
    )

    assert report.summary.strict_pass_count == 0
    assert report.summary.airi_performance_rate == 0.0
    assert (
        "AIRI performance plan does not match turn state"
        in report.failed_outcomes[0].failure_reasons
    )


def test_transcript_quality_uses_state_evaluation_for_help_performance_plan():
    report = score_lesson_transcript(
        [
            _turn(
                name="help after incorrect answer",
                turn_label="ask_help",
                teaching_action="hint",
                retrieval_mode="none",
                retrieved_block_uids=[],
                debug_signals=_debug_signals(
                    speech_style="gentle_correction",
                    motion="Explain",
                ),
                state={"last_eval_result": "incorrect"},
            ),
        ]
    )

    assert report.summary.strict_pass_count == 1
    assert report.summary.airi_performance_rate == 1.0
