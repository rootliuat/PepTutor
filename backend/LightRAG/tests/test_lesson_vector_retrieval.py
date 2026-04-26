import json
from pathlib import Path

from lightrag.orchestrator.lesson_runtime import PilotLessonCatalog
from lightrag.orchestrator.lesson_vector_retrieval import QdrantLessonRetriever


class _FakeStore:
    def __init__(self):
        self.records = []
        self.embeddings = []

    def upsert_records(self, records, embeddings):
        self.records = records
        self.embeddings = embeddings


def _write_test_pilot(tmp_path, block_count=12):
    pilot_file = tmp_path / "pilot.json"
    manifest_file = tmp_path / "manifest.json"

    block_uids = [f"TB-G5S1U3-P24-D{i}" for i in range(1, block_count + 1)]
    pilot_payload = {
        "pilot_id": "g5s1u3-vector-test",
        "scope": {"grade": "G5", "semester": "S1", "unit": "U3", "pages": [24]},
        "page_lessons": [
            {
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "page_intro_cn": "这一页练习点餐和饮料表达。",
                "entry_probe_questions": ["Can you say: What would you like to drink?"],
                "priority_blocks": block_uids,
            }
        ],
        "teaching_blocks": [
            {
                "block_uid": block_uid,
                "page_uid": "TB-G5S1U3-P24",
                "page_type": "dialogue",
                "block_type": "dialogue_core",
                "teaching_goal": f"goal {index}",
                "teaching_summary": f"summary {index}",
                "focus_vocabulary": [f"word-{index}"],
                "core_patterns": [f"pattern {index}"],
                "allowed_answer_scope": [f"answer {index}"],
                "entry_probe_questions": [],
                "repair_modes": ["repeat"],
                "next_block_uids": [],
                "learning_target_uids": [f"LT-{index}"],
                "branchable_topics": [f"topic-{index}"],
                "return_anchors": [f"anchor-{index}"],
            }
            for index, block_uid in enumerate(block_uids, start=1)
        ],
    }
    manifest_payload = {"files": [str(pilot_file)]}

    pilot_file.write_text(json.dumps(pilot_payload), encoding="utf-8")
    manifest_file.write_text(json.dumps(manifest_payload), encoding="utf-8")
    return manifest_file


def test_lesson_vector_retriever_batches_index_embeddings(tmp_path):
    manifest_path = _write_test_pilot(tmp_path, block_count=12)
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    store = _FakeStore()
    batch_sizes = []

    def _embed_texts(texts):
        batch_sizes.append(len(texts))
        return [[float(len(text))] for text in texts]

    retriever = QdrantLessonRetriever(
        catalog=catalog,
        store=store,
        embed_texts=_embed_texts,
        embedding_batch_size=5,
    )

    retriever.ensure_indexed()

    assert batch_sizes == [5, 5, 2]
    assert len(store.records) == 12
    assert len(store.embeddings) == 12


def test_lesson_vector_retriever_extracts_first_page_from_spread_uid():
    manifest_path = (
        Path(__file__).resolve().parents[3]
        / "app/knowledge/structured/general/general-manifest.json"
    )
    catalog = PilotLessonCatalog(manifest_path=manifest_path)
    retriever = QdrantLessonRetriever(
        catalog=catalog,
        store=_FakeStore(),
        embed_texts=lambda texts: [[1.0] for _ in texts],
    )

    state = retriever._build_state(
        current_page_uid="TB-G5S1Recycle2-P68-69",
        current_block_uid="TB-G5S1Recycle2-P68-69-D1",
    )

    assert retriever._extract_page_number("TB-G5S1Recycle2-P68-69") == 68
    assert state.current_page == 68
