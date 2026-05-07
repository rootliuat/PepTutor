from lightrag.orchestrator.lesson_runtime import LessonRuntime, PilotLessonCatalog


def _assert_no_internal_labels(text: str) -> None:
    banned = [
        "英文目标",
        "动作：",
        "target_role",
        "expected_student_action",
        "answer_scope",
        "TeachingMove",
        "route",
        "debug",
        "statepatch",
    ]
    for phrase in banned:
        assert phrase not in text


def test_runtime_initializes_strategy_state_for_p26_and_exposes_debug():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        debug_signals_enabled=True,
        strategy_runtime_enabled=True,
    )

    result = runtime.start_page("TB-G5S1U3-P26", "student-1")

    assert result.block_uid == "TB-G5S1U3-P26-D1"
    assert "ow" in result.teacher_response
    assert "哪一块" not in result.teacher_response
    assert result.state.strategy_state is not None
    assert result.state.strategy_state["step_id"] == "p26_s1_notice_ow"
    assert result.debug_signals is not None
    assert result.debug_signals.strategy.enabled is True
    assert result.debug_signals.strategy.priority[0] == "Strategy State"


def test_runtime_falls_back_for_page_without_reviewed_strategy():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        debug_signals_enabled=True,
        strategy_runtime_enabled=True,
    )

    result = runtime.start_page("TB-G5S1U3-P31", "student-1")

    assert result.state.strategy_state is None
    assert result.debug_signals is not None
    assert result.debug_signals.strategy.enabled is False


def test_runtime_p26_bad_dialogue_regression_stays_oral_and_strategy_locked():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        debug_signals_enabled=True,
        strategy_runtime_enabled=True,
    )
    state = runtime.start_page("TB-G5S1U3-P26", "student-1").state
    replies = []

    for learner_input in [
        "我想学第二块",
        "cow",
        "Snow",
        "我听到了，Flower",
        "这是什么意思呢",
        "I see a yellow flower",
        "已经抄写了",
        "已经写了",
    ]:
        result = runtime.handle_turn(state, learner_input)
        replies.append(result.teacher_response)
        assert result.retrieval_mode == "none"
        assert result.debug_signals is not None
        assert result.debug_signals.response_audit is not None
        assert result.debug_signals.response_audit.route == "strategy_runtime"
        assert result.state.strategy_state is not None
        assert result.state.strategy_state["page_uid"] == "TB-G5S1U3-P26"
        state = result.state

    joined = "\n".join(replies)
    assert "flower 的意思是“花”" in joined
    assert "I see a yellow flower." in joined
    assert "with a capital letter and a" not in joined
    assert "capital letter" not in joined
    assert "punctuation" not in joined.casefold()
    assert "phonics/listening-to-copy" not in joined
    assert "copy" not in joined.casefold()
    _assert_no_internal_labels(joined)


def test_runtime_p26_first_block_then_cow_does_not_return_to_module_choice():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        debug_signals_enabled=True,
        strategy_runtime_enabled=True,
    )
    state = runtime.start_page("TB-G5S1U3-P26", "student-1").state

    first_block = runtime.handle_turn(state, "吃第一块")
    cow = runtime.handle_turn(first_block.state, "cow")
    repeat_choice = runtime.handle_turn(cow.state, "第一块")
    joined = "\n".join(
        [
            first_block.teacher_response,
            cow.teacher_response,
            repeat_choice.teacher_response,
        ]
    )

    assert "cow 属于 /aʊ/" in joined
    assert "先选入口" not in joined
    assert "你想先学哪一块" not in joined
    assert "可以说“第一块”" not in joined
    assert repeat_choice.state.strategy_state is not None
    assert repeat_choice.state.strategy_state["step_id"] == "p26_s2_au_group"
    assert repeat_choice.debug_signals is not None
    assert repeat_choice.debug_signals.response_audit is not None
    assert repeat_choice.debug_signals.response_audit.route == "strategy_runtime"


def test_runtime_p24_strategy_opens_with_food_scene_not_generic_block_choice():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        debug_signals_enabled=True,
        strategy_runtime_enabled=True,
    )

    start = runtime.start_page("TB-G5S1U3-P24", "student-1")

    assert "Sarah is hungry" in start.teacher_response
    assert "哪一块" not in start.teacher_response
    assert start.state.strategy_state is not None
    assert start.state.strategy_state["page_uid"] == "TB-G5S1U3-P24"


def test_runtime_p24_strategy_keeps_role_play_food_drink_scoped():
    runtime = LessonRuntime(
        PilotLessonCatalog(),
        debug_signals_enabled=True,
        strategy_runtime_enabled=True,
    )
    state = runtime.start_page("TB-G5S1U3-P24", "student-1").state

    chicken = runtime.handle_turn(state, "chicken")
    bread = runtime.handle_turn(chicken.state, "bread")
    role = runtime.handle_turn(bread.state, "第二块")
    water = runtime.handle_turn(role.state, "water")
    joined = "\n".join(
        [
            chicken.teacher_response,
            bread.teacher_response,
            role.teacher_response,
            water.teacher_response,
        ]
    )

    assert "chicken" in joined
    assert "bread" in joined
    assert "餐厅" in joined
    assert "角色扮演" in joined
    assert "I'd like some water." in joined
    assert "What would you like to eat/drink" not in joined
    assert water.state.current_block_uid == "TB-G5S1U3-P24-D2"
    assert water.state.strategy_state is not None
    assert water.state.strategy_state["priority"][0] == "Strategy State"
