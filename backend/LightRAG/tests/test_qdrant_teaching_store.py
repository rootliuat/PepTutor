import pytest

from lightrag.orchestrator.lesson_retrieval import RetrievalSelection
from lightrag.orchestrator.lesson_state import LessonRuntimeState
from lightrag.orchestrator.qdrant_teaching_store import QdrantTeachingStore
from lightrag.orchestrator.teaching_block_index import IndexedTeachingBlock


def _make_state() -> LessonRuntimeState:
    return LessonRuntimeState(
        student_id="student-1",
        current_grade="G5",
        current_semester="S1",
        current_unit="U3",
        current_page=24,
        current_page_uid="TB-G5S1U3-P24",
        current_page_type="dialogue",
        current_block_uid="TB-G5S1U3-P24-D1",
    )


def _make_records() -> list[IndexedTeachingBlock]:
    return [
        IndexedTeachingBlock(
            point_id="TB-G5S1U3-P24-D1",
            embedding_text="drink water",
            payload={
                "block_uid": "TB-G5S1U3-P24-D1",
                "page_uid": "TB-G5S1U3-P24",
                "grade": "G5",
                "semester": "S1",
                "unit": "U3",
                "page": 24,
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": "drink core",
                "teaching_summary": "water sentence",
                "focus_vocabulary": ["water"],
                "core_patterns": ["I'd like some water."],
                "allowed_answer_scope": ["I'd like some water."],
                "repair_modes": ["repeat"],
                "learning_target_uids": ["LT-1"],
                "next_block_uids": ["TB-G5S1U3-P24-D2"],
                "branchable_topics": ["drink"],
                "return_anchors": ["What would you like to drink?"],
            },
        ),
        IndexedTeachingBlock(
            point_id="TB-G5S1U3-P24-D2",
            embedding_text="role play drink",
            payload={
                "block_uid": "TB-G5S1U3-P24-D2",
                "page_uid": "TB-G5S1U3-P24",
                "grade": "G5",
                "semester": "S1",
                "unit": "U3",
                "page": 24,
                "page_type": "dialogue",
                "block_type": "roleplay_task",
                "teaching_goal": "drink roleplay",
                "teaching_summary": "role play sentence",
                "focus_vocabulary": ["juice"],
                "core_patterns": ["I'd like some juice."],
                "allowed_answer_scope": ["I'd like some juice."],
                "repair_modes": ["repeat"],
                "learning_target_uids": ["LT-2"],
                "next_block_uids": [],
                "branchable_topics": ["roleplay"],
                "return_anchors": ["What would you like to drink?"],
            },
        ),
        IndexedTeachingBlock(
            point_id="TB-G5S1U3-P26-D1",
            embedding_text="breakfast noodles",
            payload={
                "block_uid": "TB-G5S1U3-P26-D1",
                "page_uid": "TB-G5S1U3-P26",
                "grade": "G5",
                "semester": "S1",
                "unit": "U3",
                "page": 26,
                "page_type": "dialogue",
                "block_type": "extension_task",
                "teaching_goal": "breakfast extension",
                "teaching_summary": "breakfast with noodles",
                "focus_vocabulary": ["breakfast", "noodles"],
                "core_patterns": ["I'd like noodles for breakfast."],
                "allowed_answer_scope": ["I'd like noodles for breakfast."],
                "repair_modes": ["repeat"],
                "learning_target_uids": ["LT-3"],
                "next_block_uids": [],
                "branchable_topics": ["breakfast", "noodles"],
                "return_anchors": ["What would you like to eat?"],
            },
        ),
    ]


def test_qdrant_teaching_store_upsert_and_scope_filters():
    qdrant_client = pytest.importorskip("qdrant_client")
    client = qdrant_client.QdrantClient(location=":memory:")
    store = QdrantTeachingStore(client=client, collection_name="teaching_test")
    state = _make_state()
    records = _make_records()
    embeddings = [
        [1.0, 0.0],
        [0.8, 0.0],
        [0.0, 1.0],
    ]

    store.upsert_records(records, embeddings)

    assert client.collection_exists("teaching_test")

    block_results = store.search(
        query_vector=[1.0, 0.0],
        selection=RetrievalSelection(mode="block", block_uids=["TB-G5S1U3-P24-D1"]),
        state=state,
        limit=5,
    )
    assert [item["block_uid"] for item in block_results] == ["TB-G5S1U3-P24-D1"]

    page_results = store.search(
        query_vector=[1.0, 0.0],
        selection=RetrievalSelection(mode="page"),
        state=state,
        limit=5,
    )
    assert {item["block_uid"] for item in page_results} == {
        "TB-G5S1U3-P24-D1",
        "TB-G5S1U3-P24-D2",
    }

    unit_results = store.search(
        query_vector=[0.0, 1.0],
        selection=RetrievalSelection(mode="unit"),
        state=state,
        limit=5,
    )
    assert unit_results[0]["block_uid"] == "TB-G5S1U3-P26-D1"

    branch_results = store.search(
        query_vector=[0.0, 1.0],
        selection=RetrievalSelection(
            mode="branch",
            block_uids=["TB-G5S1U3-P26-D1"],
            return_anchor="What would you like to eat?",
            branch_reason="topic_extension",
        ),
        state=state,
        limit=5,
    )
    assert [item["block_uid"] for item in branch_results] == ["TB-G5S1U3-P26-D1"]


def test_qdrant_teaching_store_reset_collection_removes_existing_points():
    qdrant_client = pytest.importorskip("qdrant_client")
    client = qdrant_client.QdrantClient(location=":memory:")
    store = QdrantTeachingStore(client=client, collection_name="teaching_test_reset")
    records = _make_records()
    embeddings = [
        [1.0, 0.0],
        [0.8, 0.0],
        [0.0, 1.0],
    ]

    store.upsert_records(records, embeddings)
    assert client.collection_exists("teaching_test_reset")

    store.reset_collection()

    assert not client.collection_exists("teaching_test_reset")
