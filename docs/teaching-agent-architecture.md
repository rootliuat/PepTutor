# Teaching Agent Architecture

## Goal
Build an English teaching agent that is curriculum-aware, context-stable, and personalized. The system should not behave like a generic chat bot with retrieval. It should behave like a teacher: understand the current lesson, judge student answers in context, decide when to explain or ask follow-up questions, and adapt over time.

## Design Principles
- Separate lesson state, textbook knowledge, and student memory.
- Let `page_type` drive the default teaching flow before turn-level intent routing.
- Treat retrieval as a tool, not the default entry for every turn.
- Distill long-term memory from interaction traces instead of storing raw dialogue blindly.
- Prefer explicit teaching structures over page-level full-text chunks.

## System Layers
```text
AIRI
-> LangGraph Orchestrator
-> Pedagogy Layer
-> Knowledge and Memory Layer
-> Model Layer
```

### AIRI
Handles input and output only: text, voice, TTS, streaming response, and Live2D actions.

### LangGraph Orchestrator
Owns turn routing and short-term state. Core responsibilities:
- maintain lesson thread state
- detect page entry and run lightweight diagnosis before full teaching
- route each turn by intent
- call tools in the correct order
- write back useful memory after each turn

### Pedagogy Layer
Controls teaching behavior:
- explain
- ask
- hint
- correct
- encourage
- review prerequisite knowledge

This layer is the difference between a tutor and a search assistant.

### Knowledge and Memory Layer
- `LightRAG`: textbook knowledge, page structure, concept relations, teaching blocks
- `SimpleMem`: long-term student profile, recurring mistakes, mastery trends, preferred hint styles

### Model Layer
Provides LLM, embedding, and optional reranker services.

## Three Memory Types
### 1. Short-term State
Thread-scoped lesson state managed by LangGraph:
- `current_grade`
- `current_unit`
- `current_page`
- `current_page_type`
- `current_block_uid`
- `awaiting_answer`
- `last_teacher_question`
- `hint_level`
- `page_entry_probe_done`
- `repair_mode`

### 2. Knowledge Memory
Curriculum knowledge managed by LightRAG.

### 3. Student Memory
Cross-session learner memory managed by SimpleMem.

## Knowledge Model
Textbook data should be normalized into `TeachingBlock` records instead of embedding full pages.

Suggested fields:
- `block_uid`
- `grade`, `semester`, `unit`, `page`
- `page_type`
- `block_type`
- `scene_summary`
- `teaching_goal`
- `core_patterns`
- `focus_vocabulary`
- `common_mistakes`
- `allowed_answer_scope`
- `follow_up_strategies`
- `entry_probe_questions`
- `suggested_repair_modes`

Only a compact `teaching_summary` should be embedded. Raw textbook text remains traceable but should not be the main retrieval unit.

## Page-Type Teaching Flow
The system should choose a default teaching template from `page_type` before interpreting a learner reply as generic chat.

Recommended page types:
- `unit_intro`: theme, scene, goal, quick activation
- `dialogue`: scene setup, key lines, role practice, transfer
- `vocabulary`: meaning, pronunciation, contrast, collocation, sentence use
- `phonics`: sound introduction, discrimination, blending, read-aloud
- `listening`: task setup, listen-and-identify, answer check, replay or read-aloud fallback
- `reading`: gist, key words, detail questions, retell
- `exercise`: item solving, feedback, error repair
- `review`: quick recall, weak-point check, targeted reinforcement
- `story`: characters, plot, theme, retell or role-play

When the learner opens a page such as "Grade 5 Semester 1 Page 31", the system should:
1. give a short Chinese overview of what the page is about
2. ask one or two very short probe questions
3. estimate whether the learner is `mastered`, `shaky`, or `not_mastered`
4. choose whether to move fast, teach lightly, or teach fully

This page-entry step should happen before long explanations.

## Learning Memory Model
Adapt the `Trace -> Unit -> Crystal` pattern into a teaching version:

- `LessonTrace`: raw turn history, teacher prompts, student answers, tool outputs
- `TeachingUnit`: atomic learning facts, such as "student confuses ordinal and cardinal numbers"
- `LearningCrystal`: synthesized stage-level understanding of the learner

New knowledge should be linked with `EVOLVES` relations:
- `replaces`
- `enriches`
- `confirms`
- `challenges`

The system should also store `assumed_prior_knowledge` separately from confirmed learner memory. This is a hypothesis layer used to guide pacing, and it must be verified or rejected through lightweight probes.

## Student Readiness Model
For page-level and topic-level teaching decisions, use three stable readiness states:
- `mastered`: the learner can answer or use the target with little or no support
- `shaky`: the learner roughly understands it but produces unstable, incomplete, or error-prone output
- `not_mastered`: the learner needs full explanation, modeling, guided practice, and correction

In elementary English, `shaky` is expected and should be treated as the default middle state rather than a failure.

## Turn Routing
Each user turn should be classified before any retrieval, but page type and page-entry state come first:
- if the learner has just entered a page, run page overview plus probe first
- if `awaiting_answer = true`, evaluate against the current teaching block first
- if the learner asks to split the task, slow down, or focus on one word, switch into a lighter repair mode instead of continuing the long script

Stable turn labels remain:
- `answer_question`
- `ask_knowledge`
- `ask_help`
- `navigation`
- `social`
- `meta_learning`

Routing rules:
- only expand retrieval scope from `block -> page -> unit -> global` when needed
- use student memory only for personalization, not as a replacement for lesson state

## MVP Build Order
1. Define `TeachingBlock` schema, `page_type`, and page-entry probes for a small set of core textbook pages.
2. Implement LangGraph lesson state, page-entry diagnosis, and turn router.
3. Connect LightRAG for textbook retrieval with scoped expansion.
4. Connect SimpleMem for learner profile write-back, assumed prior knowledge, and recall.
5. Add Pedagogy Planner rules for hints, correction, repair mode, and follow-up questions.
6. Add voice and Live2D action mapping in AIRI.

## Non-Goals for V1
- fully autonomous multi-agent team
- whole-book blind embedding
- storing every raw turn as permanent long-term memory
- free-form global retrieval during active answer evaluation
