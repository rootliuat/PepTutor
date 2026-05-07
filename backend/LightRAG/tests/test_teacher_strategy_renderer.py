from lightrag.pedagogy.page_teaching_strategy import PageTeachingStrategyRepository
from lightrag.pedagogy.teacher_strategy_renderer import (
    next_strategy_state,
    render_strategy_page_entry,
    render_strategy_turn,
)


def _repo() -> PageTeachingStrategyRepository:
    return PageTeachingStrategyRepository.default()


def test_p26_renderer_handles_bad_oral_dialogue_without_copy_drift():
    strategy = _repo().get("TB-G5S1U3-P26")
    assert strategy is not None
    entry = render_strategy_page_entry(strategy)
    state = next_strategy_state(strategy=strategy, result=entry)
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
        result = render_strategy_turn(
            strategy=strategy,
            strategy_state=state,
            learner_input=learner_input,
        )
        replies.append(result.teacher_reply)
        state = next_strategy_state(strategy=strategy, result=result)

    joined = "\n".join(replies)
    assert "flower 的意思是“花”" in joined
    assert "I see a yellow flower." in joined
    assert "大小写" in joined
    assert "with a capital letter and a" not in joined
    assert "英文目标" not in joined
    assert "动作：" not in joined
    assert "TeachingMove" not in joined
    assert "copy" not in joined.casefold()
    assert state["page_uid"] == "TB-G5S1U3-P26"
    assert state["priority"][0] == "Strategy State"


def test_p26_renderer_does_not_reset_to_module_choice_after_first_phonics_answer():
    strategy = _repo().get("TB-G5S1U3-P26")
    assert strategy is not None
    entry = render_strategy_page_entry(strategy)
    state = next_strategy_state(strategy=strategy, result=entry)

    first_block = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="吃第一块",
    )
    state = next_strategy_state(strategy=strategy, result=first_block)
    cow = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="cow",
    )
    state = next_strategy_state(strategy=strategy, result=cow)
    repeat_choice = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="第一块",
    )

    joined = "\n".join([first_block.teacher_reply, cow.teacher_reply, repeat_choice.teacher_reply])
    assert "cow 属于 /aʊ/" in joined
    assert "先选入口" not in joined
    assert "你想先学哪一块" not in joined
    assert "可以说“第一块”" not in joined
    assert repeat_choice.step_id == "p26_s2_au_group"


def test_p24_renderer_keeps_food_and_drink_inside_role_scene():
    strategy = _repo().get("TB-G5S1U3-P24")
    assert strategy is not None
    entry = render_strategy_page_entry(strategy)
    state = next_strategy_state(strategy=strategy, result=entry)

    chicken = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="chicken",
    )
    state = next_strategy_state(strategy=strategy, result=chicken)
    bread = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="bread",
    )
    state = next_strategy_state(strategy=strategy, result=bread)
    role = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="第二块",
    )
    state = next_strategy_state(strategy=strategy, result=role)
    water = render_strategy_turn(
        strategy=strategy,
        strategy_state=state,
        learner_input="water",
    )

    joined = "\n".join(
        [entry.teacher_reply, chicken.teacher_reply, bread.teacher_reply, role.teacher_reply, water.teacher_reply]
    )
    assert "Sarah is hungry" in joined
    assert "chicken" in joined
    assert "bread" in joined
    assert "餐厅" in joined
    assert "角色扮演" in joined
    assert "I'd like some water." in joined
    assert "What would you like to eat/drink" not in joined
