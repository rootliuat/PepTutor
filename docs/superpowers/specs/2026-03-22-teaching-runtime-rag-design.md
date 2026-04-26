# Teaching Runtime and RAG Design

## Status
This document captures the design decisions validated in the current discussion. It records approved architecture and data-flow choices, plus a short list of still-open items.

## Goal
Build a curriculum-aware teaching agent that feels like a lively guided teacher, not a textbook search bot. The first priority is stable lesson behavior. Retrieval remains a support tool.

## Teacher Style
- lively and guided
- prefer half-answer hints before full answers
- if the learner gets stuck repeatedly, give one model sentence, then do repeat and drill
- allow short temporary branches
- return to the lesson naturally by bridging from a branch topic back to the current page goal

## Architecture
The runtime is divided into four layers:

1. `AIRI`
Handles input and output only: ASR, text input, TTS, avatar actions, and streaming UI.

2. `Lesson Runtime`
Owns lesson state, current page, current block, branch state, and whether the system is waiting for an answer.

3. `Pedagogy Engine`
Chooses the teaching action for the turn, such as hint, model, drill, explain, or return to main.

4. `Knowledge and Memory Tools`
`LightRAG` provides textbook knowledge. `SimpleMem` provides learner memory. Neither layer controls the lesson flow directly.

## Prompt Strategy
Use two prompts instead of one giant prompt:

- `Planner Prompt`
Produces structured decisions such as `teaching_action`, `retrieval_mode`, `target_block_uid`, `return_anchor`, and `branch_turn_budget`.

- `Responder Prompt`
Turns the chosen action into teacher-like language. It receives the selected action, a compact knowledge payload, and a compact learner-memory summary.

Stable policy belongs in the prompt. Dynamic page state, retrieval evidence, and learner-memory summaries should be injected per turn.

## Learner Memory Priority
Long-term memory priority is:

1. common mistakes
2. learning preferences
3. mastery progress

## Knowledge Asset Pipeline
Raw assets should not be embedded directly. Normalize them into three asset families:

1. `PageLesson + TeachingBlock`
This is the main classroom data path.

2. `LexiconEntry`
Used for word meaning, useful expressions, and short example support.

3. `PronunciationRule`
Used for phonics and speaking support.

`PageLesson` is runtime-facing page metadata. `TeachingBlock` is the main retrieval unit.

## Curriculum Map And LessonBrief Boundary
PepTutor needs a prepared-teacher layer before per-turn response generation. The system should not run as `student input -> broad RAG -> answer`; it should run as `prepared lesson context -> learner signal -> teaching move -> teacher response`.

Add an offline `CurriculumMap` for the four PEP books. The map indexes:

- `grade`
- `semester`
- `unit`
- `pages`
- `unit_theme`
- `core_vocabulary`
- `core_patterns`
- `page_types`
- `block_uids`
- `learning_targets`
- `source_refs`
- `confidence`

The map should be generated from current raw textbook files, word lists, Useful expressions, and structured general artifacts. Do not hand-author unit targets from memory or broad textbook impressions. If an extracted theme, grammar point, or unit goal is uncertain, keep the field but mark confidence and source so it can be reviewed.

Runtime must not inject the full map, full unit, or full textbook into the LLM. Use the map as an index:

1. exact `page_uid` / `block_uid` / metadata lookup finds the current evidence
2. scoped retrieval may supplement missing nearby support inside the active page or unit
3. `LessonBriefBuilder` distills page/block goals, materials, answer scope, likely misconceptions, progression, and support vocabulary
4. `TeachingMovePlanner` chooses the move from learner signal plus the current brief
5. `Responder` turns the move into natural teacher language using the teacher soul and memory hints

`CurriculumMap` is the map. `LessonBrief` is private preparation. `TurnBrief` is the compact per-turn slice. None of these may become fixed teacher wording or a per-page script.

## TeachingBlock Policy
Do not chunk by token length. Split by teaching purpose.

Good block examples:
- `dialogue_core`
- `dialogue_practice`
- `vocabulary_core`
- `sentence_pattern_practice`
- `roleplay_task`
- `listening_probe`

Each block should carry one main teaching purpose, not a whole page.

The current pilot structure is already close to the target format and should be treated as the V1 base schema. Keep the existing fields such as:

- `page_uid`
- `page_type`
- `page_intro_cn`
- `entry_probe_questions`
- `priority_blocks`
- `block_uid`
- `block_type`
- `teaching_goal`
- `teaching_summary`
- `focus_vocabulary`
- `core_patterns`
- `allowed_answer_scope`
- `repair_modes`
- `next_block_uids`

Add two fields for branch-aware teaching:

- `branchable_topics`
- `return_anchors`

## Qdrant Storage Policy
Use `Qdrant` as the knowledge vector store.

- development: local Qdrant in WSL
- production: cloud or self-hosted Qdrant with the same interface
- do not replace this with a vendor-specific black-box knowledge-base API

The main collection should store `TeachingBlock` only. `PageLesson` should remain runtime metadata. `LexiconEntry` and `PronunciationRule` can be added later as separate collections if needed.

Recommended payload fields:

- `block_uid`
- `page_uid`
- `grade`
- `semester`
- `unit`
- `page`
- `page_type`
- `block_type`
- `teaching_goal`
- `teaching_summary`
- `focus_vocabulary`
- `core_patterns`
- `allowed_answer_scope`
- `repair_modes`
- `learning_target_uids`
- `next_block_uids`
- `branchable_topics`
- `return_anchors`

The embedding text should be compact and teaching-oriented. Build it from:

- `teaching_goal`
- `teaching_summary`
- `core_patterns`
- `focus_vocabulary`
- `allowed_answer_scope`

Do not embed full textbook pages as the primary retrieval unit.

## Embedding Recommendation
For a China-first deployment path:

- first choice: Alibaba or Qwen embedding APIs
- second choice: `bge-m3` through a domestic stack such as Tencent VectorDB
- `text-embedding-3-large` remains a quality benchmark, not the default deployment choice

## Retrieval Modes
Planner should not invent arbitrary retrieval scope. It should output one of five fixed modes:

### `none`
Default mode. Use local lesson state, the current block, and local evaluation only.

Typical use:
- answer evaluation
- half-answer hint
- repeat or drill
- model sentence after repeated failure
- praise or short encouragement
- normal mainline progression

### `block`
Retrieve only the current `TeachingBlock`.

Typical use:
- explain the current sentence or phrase
- provide one closely aligned example
- double-check current answer scope

### `page`
Expand to current page `priority_blocks` and sibling blocks.

Typical use:
- the learner asks about another point on the same page
- page-entry probing
- a page-local review or transition to another block on the same page

### `unit`
Expand to the current unit only.

Typical use:
- the learner asks something beyond the page but still inside the unit theme
- the system needs a nearby prerequisite or a same-unit bridge example

### `branch`
Short, controlled branch retrieval for temporary topic extension.

Typical use:
- short vocabulary extension
- short scenario extension
- pronunciation support
- interest-led side topic that can still bridge back

## Retrieval Hard Rules
- if `awaiting_answer = true`, prefer `none`
- do not jump directly from local answer evaluation to `unit`
- do not turn a normal answer turn into `branch`
- move scope gradually: `none -> block -> page -> unit`
- `branch` must return to `block` or `page`
- retrieval is a support tool, not the default response path

## Branch Design
`branch` is a controlled teaching branch, not free chat.

Open a branch only when:
- the learner asks a relevant extension question
- the branch can help the current page make more sense
- the branch can be bridged back to the current page goal

Do not open a branch when:
- the system is still waiting for a direct answer
- the learner is repeatedly stuck and needs correction closure first
- the topic is unrelated to the current lesson or unit

Allowed branch actions:
- `short_explain`
- `mini_example`
- `micro_drill`
- `bridge_back`

Not allowed inside a branch:
- starting a new teaching goal
- a long grammar lecture
- wide global knowledge search
- opening a full new lesson

## Branch Runtime Fields
Minimal branch state in runtime:

- `branch_active`
- `branch_reason`
- `branch_origin_block_uid`
- `branch_turn_budget`
- `return_anchor`
- `return_target`

Default branch budget should be `2`, with `3` as the upper bound.

## Return-to-Main Strategy
Do not default to hard transitions like "now let's go back to the textbook."

Use `return_anchor` instead. A return anchor may be:

- a vocabulary anchor
- a sentence-pattern anchor
- a scene anchor

Example:

If the branch topic is `breakfast`, the system can return with:

`In our page's ordering scene, what would you like to eat? You can answer with I'd like ...`

This keeps the branch natural while preserving the lesson goal.

## Difficulty Escalation Ladder
When the learner gets stuck, the system should follow a fixed escalation ladder instead of improvising.

The goal is:

`help the learner say it independently without leaving them stuck too long`

Recommended runtime signals:

- `same_goal_attempt_count`
- `last_eval_result`
- `repair_mode`
- `model_already_given`

### Level 0: Light Hint
Use when the learner is close and only misses a word, phrase, or part of the sentence.

Actions:
- point to the key word or pattern
- give a half-sentence frame
- do not provide the full answer

### Level 1: Stronger Half-Hint
Use when the learner is still incomplete after the first hint.

Actions:
- give a clearer sentence frame
- optionally provide a small word choice
- allow `word_drill` or `sentence_drill`

### Level 2: Model Sentence
Use when the learner is stuck for two or three attempts, or cannot organize the sentence.

Actions:
- provide one correct model sentence
- keep it short
- mark `model_already_given = true`

### Level 3: Repeat and Drill
Use after the model sentence has been given.

Actions:
- guide one repeat
- run one light substitution or short drill
- optionally use `slow_read` or `sentence_drill`

### Level 4: Independent Retry
Use after repeat and drill to confirm the learner can produce the target independently.

Actions:
- return to the original question or an equivalent prompt
- ask the learner to say the answer independently
- if successful, return to the normal lesson flow

## Difficulty Escalation Rules
- first difficulty: `Level 0`
- second difficulty: `Level 1`
- repeated difficulty after two or three attempts: `Level 2`
- after modeling: `Level 3`
- then require an independent retry at `Level 4`

If the learner is still unstable after `Level 4`, do not loop forever. Either:

- reduce the target to a smaller goal
- move on and recycle the point later

This ladder is primarily pedagogy logic, not retrieval logic. It should usually stay in `retrieval_mode = none`.
