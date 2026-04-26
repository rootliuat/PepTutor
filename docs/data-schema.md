# Data Schema

## Goal
Define a stable data contract for the teaching agent system. This schema separates:
- textbook knowledge for `LightRAG`
- short-term lesson state for `LangGraph`
- long-term learner memory for `SimpleMem`

The main rule is simple: do not mix curriculum structure, runtime lesson state, and learner profile data in one record type.

## 1. CurriculumMap
`CurriculumMap` is an offline four-book index used to prepare lessons and constrain retrieval. It is not a live prompt payload and should not contain fixed teacher wording.

### Required fields
| Field | Type | Notes |
| --- | --- | --- |
| `map_id` | string | Versioned map ID, e.g. `peptutor-curriculum-map-v1` |
| `generated_at` | string | ISO 8601 |
| `books` | object[] | One entry per grade/semester book |

### Book entry fields
| Field | Type | Notes |
| --- | --- | --- |
| `grade` | string | `G5`, `G6` |
| `semester` | string | `S1`, `S2` |
| `source_refs` | string[] | Raw textbook, wordlist, Useful expressions, and structured files used |
| `units` | object[] | Unit-level summaries and indexes |

### Unit entry fields
| Field | Type | Notes |
| --- | --- | --- |
| `unit` | string | `U1`, `U2`, `Recycle1`, etc. |
| `pages` | integer[] | Textbook pages in the unit/scope |
| `unit_theme` | string or null | Generated from source evidence, not from memory |
| `core_vocabulary` | object[] | Words with source refs when available |
| `core_patterns` | string[] | Useful expressions or sentence patterns from source |
| `page_types` | object[] | `{ page_uid, page, page_type, confidence }` |
| `block_uids` | string[] | Teaching blocks in this unit/scope |
| `learning_targets` | object[] | Target summaries linked to source/block UIDs |
| `confidence` | string | `high`, `medium`, or `low` |
| `review_notes` | string[] | Human-review notes for uncertain extraction |

### Runtime rule
Use `CurriculumMap` to find and prepare scoped lesson context. Do not pass the full map, full book, or full unit into `/lesson/turn`.

## 2. LessonBrief
`LessonBrief` is the compact private preparation artifact generated for the current page/block. It is used by the planner and responder but must not be read aloud as a fixed script.

| Field | Type | Notes |
| --- | --- | --- |
| `brief_id` | string | Versioned brief ID |
| `page_uid` | string | Current page |
| `block_uid` | string or null | Current block when known |
| `source_block_uids` | string[] | Evidence blocks used |
| `source_refs` | string[] | Original source traceability |
| `teaching_focus` | string | What this page/block is actually trying to teach |
| `materials` | string[] | Dialogue lines, task instructions, vocab, or examples needed now |
| `answer_scope` | string[] | Acceptable learner answer forms or concepts |
| `support_vocabulary` | string[] | Nearby words useful for scaffolding |
| `likely_misconceptions` | string[] | Content-derived likely errors |
| `progression` | string[] | Suggested order of teaching moves, not fixed teacher wording |
| `learner_stage_profile` | object | Grade-band speech/cognitive-load constraints |
| `confidence` | string | `high`, `medium`, or `low` |

`TurnBrief` should be derived from `LessonBrief` for each response and contain only the current learner signal, selected teaching move, memory hints, and scoped evidence needed for one turn.

## 3. TeachingBlock
`TeachingBlock` is the main curriculum unit used for retrieval, answer evaluation, and teaching strategy.

### Required fields
| Field | Type | Notes |
| --- | --- | --- |
| `block_uid` | string | Stable unique ID, e.g. `TB-G5S2U4-P36-D1` |
| `grade` | string | `G5`, `G6` |
| `semester` | string | `S1`, `S2` |
| `unit` | string | `U1`, `U2`, `Recycle1` |
| `page` | integer | Textbook page number |
| `page_type` | string | `unit_intro`, `dialogue`, `vocabulary`, `phonics`, `listening`, `reading`, `exercise`, `review`, `story` |
| `block_type` | string | `dialogue_core`, `vocabulary_core`, `exercise_block`, `story_block`, `summary_block` |
| `scene_summary` | string | Short description of the scene or task |
| `teaching_goal` | string | What the learner should understand or perform |
| `teaching_summary` | string | Compact embedding text used for vector retrieval |

### Recommended fields
| Field | Type | Notes |
| --- | --- | --- |
| `section_title` | string or null | Original textbook section title |
| `core_patterns` | string[] | Key sentence patterns |
| `focus_vocabulary` | object[] | `{ word, chinese }` |
| `key_points` | object[] | `{ english, chinese }` |
| `example_sentences` | string[] | Clean examples for explanation |
| `common_mistakes` | string[] | Expected learner mistakes |
| `allowed_answer_scope` | string[] | Acceptable answer forms or concepts |
| `follow_up_strategies` | string[] | Suggested prompts, hints, drills |
| `entry_probe_questions` | string[] | One or two short questions used for page-entry diagnosis |
| `page_intro_cn` | string | Short Chinese page overview used before probing |
| `prerequisites` | string[] | Prior knowledge needed |
| `suggested_repair_modes` | string[] | `word_drill`, `sentence_drill`, `slow_read`, `asr_clarify` |
| `source_refs` | object[] | Original source traceability |

### Storage guidance
- Graph fields: `grade`, `semester`, `unit`, `page`, `page_type`, `block_type`, `core_patterns`, `focus_vocabulary`, `prerequisites`
- Embedding field: `teaching_summary`
- Non-embedded support fields: `allowed_answer_scope`, `follow_up_strategies`, `entry_probe_questions`, `page_intro_cn`, `suggested_repair_modes`, `source_refs`

## 4. LessonState
`LessonState` is runtime-only data stored in LangGraph checkpoints.

| Field | Type | Notes |
| --- | --- | --- |
| `thread_id` | string | Conversation or lesson thread |
| `student_id` | string | Learner identifier |
| `current_grade` | string | Current lesson grade |
| `current_unit` | string | Current unit |
| `current_page` | integer | Current page |
| `current_page_type` | string | Current page teaching category; it can guide strategy but must not imply fixed wording |
| `current_block_uid` | string or null | Active teaching block |
| `current_activity_type` | string | `teaching`, `practice`, `review`, `free_talk` |
| `awaiting_answer` | boolean | Whether the teacher expects an answer |
| `last_teacher_question` | string or null | Current question under evaluation |
| `hint_level` | integer | 0-based hint depth |
| `page_entry_probe_done` | boolean | Whether the current page already had its overview and quick probe |
| `repair_mode` | string | `none`, `word_drill`, `sentence_drill`, `slow_read`, `asr_clarify` |
| `recent_turn_labels` | string[] | Recent routing labels |

This schema is not for long-term storage.

## 5. AssumedPriorKnowledge
`AssumedPriorKnowledge` stores a hypothesis about what the learner probably already knows before the system teaches a page in depth.

| Field | Type | Notes |
| --- | --- | --- |
| `assumption_id` | string | Unique hypothesis ID |
| `student_id` | string | Learner identifier |
| `topic` | string | Topic or page goal, e.g. `hungry`, `daily-routine`, `salad-dialogue` |
| `source` | string | `curriculum_prerequisite`, `recent_lesson`, `learner_memory` |
| `confidence` | number | 0.0 to 1.0 |
| `verification_status` | string | `unverified`, `confirmed`, `rejected` |
| `related_page` | string or null | Optional page reference |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |

This record should guide pacing only after lightweight verification. It is not the same as confirmed mastery.

## 6. LessonTrace
`LessonTrace` captures raw events for replay and distillation.

| Field | Type | Notes |
| --- | --- | --- |
| `trace_id` | string | Unique event ID |
| `thread_id` | string | Lesson thread |
| `student_id` | string | Learner identifier |
| `turn_index` | integer | Turn order |
| `speaker` | string | `student`, `teacher`, `system`, `tool` |
| `content` | string | Raw text |
| `turn_label` | string | Routed turn type |
| `block_uid` | string or null | Related teaching block |
| `timestamp` | string | ISO 8601 |
| `tool_payload` | object or null | Optional tool metadata |

Traces should be retained for audit and memory distillation, not used directly as permanent learner memory.

## 7. TeachingUnit
`TeachingUnit` is the atomic long-term learner memory item written into `SimpleMem`.

| Field | Type | Notes |
| --- | --- | --- |
| `unit_memory_id` | string | Unique memory ID |
| `student_id` | string | Learner identifier |
| `topic` | string | Knowledge topic, e.g. `dates`, `directions` |
| `memory_type` | string | `mastery`, `mistake`, `preference`, `strategy`, `engagement` |
| `mastery_level` | string | `mastered`, `shaky`, `not_mastered` |
| `statement` | string | Distilled learner fact |
| `observed_skills` | string[] | `listening`, `speaking`, `reading`, `vocabulary`, `grammar`, `phonics` |
| `evidence_trace_ids` | string[] | Source traces |
| `related_block_uids` | string[] | Curriculum linkage |
| `confidence` | number | 0.0 to 1.0 |
| `created_at` | string | ISO 8601 |
| `last_observed_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |

Example:
`Student often answers date questions with month only and omits the ordinal day.`

## 8. LearningCrystal
`LearningCrystal` is a synthesized learner-level conclusion built from multiple `TeachingUnit` records.

| Field | Type | Notes |
| --- | --- | --- |
| `crystal_id` | string | Unique ID |
| `student_id` | string | Learner identifier |
| `theme` | string | High-level learning theme |
| `summary` | string | Synthesized learner understanding |
| `mastery_level` | string | `mastered`, `shaky`, `not_mastered` |
| `supporting_unit_ids` | string[] | Supporting teaching units |
| `coverage_scope` | string[] | Related units or topics |
| `status` | string | `active`, `stale`, `challenged` |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |

## 9. EVOLVES Relation
Use `EVOLVES` to link new learner knowledge to prior learner knowledge.

| Field | Type | Notes |
| --- | --- | --- |
| `from_id` | string | Older `TeachingUnit` or `LearningCrystal` |
| `to_id` | string | Newer `TeachingUnit` or `LearningCrystal` |
| `relation_type` | string | `replaces`, `enriches`, `confirms`, `challenges` |
| `reason` | string | Why this evolution was assigned |
| `created_at` | string | ISO 8601 |

## 10. Intent Labels
These values should stay stable across routing, traces, and analytics.

- `answer_question`
- `ask_knowledge`
- `ask_help`
- `navigation`
- `social`
- `meta_learning`

## 11. Constraints
- Never embed full textbook pages as the primary retrieval unit.
- Never inject a whole `CurriculumMap`, whole book, or whole unit into live `/lesson/turn` prompts.
- Never treat generated curriculum summaries as authoritative unless source refs and confidence support them.
- Never turn `LessonBrief` progression into fixed teacher wording.
- Never write raw turn text directly into long-term learner memory without distillation.
- Never use `LessonState` as a substitute for learner memory.
- Never treat `assumed_prior_knowledge` as confirmed mastery before probe-based verification.
- Keep all IDs stable and traceable back to textbook source or trace evidence.
