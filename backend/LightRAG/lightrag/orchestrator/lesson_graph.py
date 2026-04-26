"""LangGraph orchestration for PepTutor lesson turns."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from lightrag.orchestrator.lesson_state import LessonRuntimeState


class LessonTurnGraphState(TypedDict, total=False):
    """Internal graph state for one /lesson/turn request."""

    page_uid: str
    student_id: str
    learner_input: str
    requested_page_uid: str | None
    state: LessonRuntimeState | None
    prior_state: LessonRuntimeState | None
    result: Any


def build_lesson_turn_graph(runtime: Any):
    """Compile the lesson turn graph around a LessonRuntime instance."""

    def route_entry(
        graph_state: LessonTurnGraphState,
    ) -> Literal["start_page", "switch_page", "normalize_turn"]:
        state = graph_state.get("state")
        if state is None:
            return "start_page"
        requested_page_uid = graph_state.get("requested_page_uid")
        if requested_page_uid and requested_page_uid != state.current_page_uid:
            return "switch_page"
        return "normalize_turn"

    def route_turn_kind(
        graph_state: LessonTurnGraphState,
    ) -> Literal["answer_turn", "open_turn"]:
        state = graph_state.get("state")
        if state is not None and state.awaiting_answer and state.current_block_uid:
            return "answer_turn"
        return "open_turn"

    def start_page_node(graph_state: LessonTurnGraphState) -> dict[str, Any]:
        return {
            "result": runtime._start_page_impl(
                graph_state["page_uid"],
                graph_state["student_id"],
            )
        }

    def switch_page_node(graph_state: LessonTurnGraphState) -> dict[str, Any]:
        state = graph_state["state"]
        if state is None:
            raise ValueError("state is required for page switching")
        requested_page_uid = graph_state.get("requested_page_uid")
        if not requested_page_uid:
            raise ValueError("requested_page_uid is required for page switching")

        runtime._persist_page_summary_and_finalize(state)
        return {
            "result": runtime._start_page_impl(
                requested_page_uid,
                state.student_id,
            )
        }

    def normalize_turn_node(graph_state: LessonTurnGraphState) -> dict[str, Any]:
        learner_input = (graph_state.get("learner_input") or "").strip()
        if not learner_input:
            raise ValueError("learner_input cannot be empty")
        state = graph_state.get("state")
        if state is None:
            raise ValueError("state is required after initialization")
        return {
            "learner_input": learner_input,
            "prior_state": state.model_copy(deep=True),
        }

    def answer_turn_node(graph_state: LessonTurnGraphState) -> dict[str, Any]:
        return {
            "result": runtime._handle_answer_turn(
                graph_state["state"],
                graph_state["learner_input"],
            )
        }

    def open_turn_node(graph_state: LessonTurnGraphState) -> dict[str, Any]:
        return {
            "result": runtime._handle_open_turn(
                graph_state["state"],
                graph_state["learner_input"],
            )
        }

    def after_turn_node(graph_state: LessonTurnGraphState) -> dict[str, Any]:
        prior_state = graph_state.get("prior_state")
        result = graph_state.get("result")
        if prior_state is None or result is None:
            return {}

        runtime._write_memory_trace(
            prior_state=prior_state,
            learner_input=graph_state["learner_input"],
            result=result,
        )
        if runtime._should_summarize_page_session(
            prior_state=prior_state,
            result=result,
        ):
            runtime._persist_page_summary(result.state)
        return {}

    graph = StateGraph(LessonTurnGraphState)
    graph.add_node("start_page", start_page_node)
    graph.add_node("switch_page", switch_page_node)
    graph.add_node("normalize_turn", normalize_turn_node)
    graph.add_node("answer_turn", answer_turn_node)
    graph.add_node("open_turn", open_turn_node)
    graph.add_node("after_turn", after_turn_node)

    graph.add_conditional_edges(
        START,
        route_entry,
        {
            "start_page": "start_page",
            "switch_page": "switch_page",
            "normalize_turn": "normalize_turn",
        },
    )
    graph.add_edge("start_page", END)
    graph.add_edge("switch_page", END)
    graph.add_conditional_edges(
        "normalize_turn",
        route_turn_kind,
        {
            "answer_turn": "answer_turn",
            "open_turn": "open_turn",
        },
    )
    graph.add_edge("answer_turn", "after_turn")
    graph.add_edge("open_turn", "after_turn")
    graph.add_edge("after_turn", END)
    return graph.compile()
