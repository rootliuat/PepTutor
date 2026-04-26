import importlib
import sys

_PYTEST_ARGV = sys.argv[:]
sys.argv = [sys.argv[0]]
semantic_module = importlib.import_module("lightrag.orchestrator.simplemem_semantic_memory")
sys.argv = _PYTEST_ARGV

SemanticMemoryHit = semantic_module.SemanticMemoryHit
SimpleMemSemanticRecallProvider = semantic_module.SimpleMemSemanticRecallProvider
build_semantic_tenant_namespace = semantic_module.build_semantic_tenant_namespace


class _FakeSemanticStore:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def semantic_search(self, **kwargs):
        self.calls.append(kwargs)
        return list(self.hits)


def test_semantic_recall_provider_builds_query_and_trims_hits():
    store = _FakeSemanticStore(
        [
            SemanticMemoryHit(
                entry_id="m1",
                lossless_restatement="Learner struggles to answer with 'I'd like some water.' independently.",
                tenant_id="student-1",
                memory_session_id="old-1",
                source_kind="lesson_trace",
            ),
            SemanticMemoryHit(
                entry_id="m2",
                lossless_restatement="Learner prefers slower split practice when stuck.",
                tenant_id="student-1",
                memory_session_id="old-2",
                source_kind="lesson_trace",
            ),
            SemanticMemoryHit(
                entry_id="m3",
                lossless_restatement="Learner prefers slower split practice when stuck.",
                tenant_id="student-1",
                memory_session_id="old-3",
                source_kind="lesson_trace",
            ),
        ]
    )
    provider = SimpleMemSemanticRecallProvider(
        store,
        project="peptutor-lesson",
        top_k=3,
        max_items=2,
    )

    recalled = provider.recall(
        student_id="student-1",
        learner_input="help me with water",
        state_snapshot={"current_page_uid": "TB-G5S1U3-P24"},
        block_snapshot={
            "teaching_goal": "Use the target drink question and answer.",
            "teaching_summary": "Restaurant ordering with the drink question.",
            "focus_vocabulary": ["water", "juice"],
            "core_patterns": ["I'd like some water."],
        },
        exclude_memory_session_id="active-1",
    )

    assert recalled == [
        "Learner struggles to answer with 'I'd like some water.' independently.",
        "Learner prefers slower split practice when stuck.",
    ]
    search_call = store.calls[0]
    assert search_call["tenant_id"] == build_semantic_tenant_namespace(
        project="peptutor-lesson",
        student_id="student-1",
    )
    assert search_call["exclude_memory_session_ids"] == ["active-1"]
    assert search_call["source_kinds"] == ["lesson_trace"]
    assert "TB-G5S1U3-P24" in search_call["query"]
    assert "water" in search_call["query"]
