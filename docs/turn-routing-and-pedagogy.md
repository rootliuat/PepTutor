# Turn Routing and Pedagogy

## Goal
Define how each learner turn is classified and what teaching behavior should follow. This document is the bridge between `LangGraph` routing and the teaching strategy layer.

## Page Type First, Retrieval Second
Teaching should be organized by textbook page type first, not by free-form chat alone. Every input must be interpreted inside the current page context before retrieval.

Routing order:
1. inspect current `LessonState`
2. inspect `current_page_type` and whether this is a fresh page entry
3. if needed, run page overview plus a lightweight probe
4. classify the learner turn
5. select the teaching action
6. decide whether retrieval is needed
7. generate response and optional AIRI actions

## Page Types
Use stable `page_type` values to decide the default teaching flow:

- `unit_intro`
- `dialogue`
- `vocabulary`
- `phonics`
- `listening`
- `reading`
- `exercise`
- `review`
- `story`

These page types do not replace turn labels. They define the lesson template that turn labels operate inside.

## Page Entry Diagnostic
When the learner opens a new page, the system should not start with a full lecture. It should do a lightweight diagnostic:

1. give a short Chinese overview of the page
2. ask one or two short probe questions
3. estimate whether the learner is `mastered`, `shaky`, or `not_mastered`
4. choose a fast, light, or full teaching path

This diagnostic should be driven by `assumed_prior_knowledge`, which is a hypothesis from prerequisites, recent turns, or learner memory. It must be verified before it affects pacing.

## Turn Labels
Use these stable labels across runtime, traces, and analytics.

### `answer_question`
The learner is answering the teacher's active question.

Typical signals:
- `awaiting_answer = true`
- short answer or partial sentence
- lexical overlap with the current block

Behavior:
- evaluate against `current_block_uid`
- do not run global retrieval by default
- choose one of: `confirm`, `correct`, `hint`, `follow_up`

### `ask_knowledge`
The learner is asking about meaning, usage, grammar, vocabulary, or page content.

Behavior:
- retrieve in this order: `block -> page -> unit -> global`
- answer from textbook knowledge
- optionally add one short example or contrast

### `ask_help`
The learner indicates confusion or inability.

Typical signals:
- “I don't know”
- “What does this mean?”
- “Can you explain again?”

Behavior:
- prefer scaffolding over direct full answers
- reduce difficulty
- use simpler wording, examples, or stepwise hints

### `navigation`
The learner wants to switch task, page, unit, or mode.

Behavior:
- update `LessonState`
- confirm the transition
- reset `awaiting_answer` if needed

### `social`
The learner is chatting, reacting emotionally, or making small talk.

Behavior:
- keep response short and warm
- do not trigger curriculum retrieval unless the learner shifts back

### `meta_learning`
The learner asks about progress, review, or study method.

Behavior:
- use `SimpleMem`
- summarize strengths, weak points, and next steps

## Teaching Actions
The pedagogy layer should choose one primary action per turn.

### `page_intro`
Use when the learner first enters a page. Keep it short, usually in Chinese, and focus on page theme, task, and target.

### `probe`
Use for one or two very short diagnostic questions before deciding how deeply to teach.

### `explain`
Use when the learner asks for meaning or concept clarification.

### `hint`
Use when the learner is close but incomplete. Hints should escalate by `hint_level`.

Hint ladder:
- level 0: point to the relevant word or pattern
- level 1: give a partial sentence frame
- level 2: give a contrastive example
- level 3: provide the answer, then explain why

### `correct`
Use when the learner answer is clearly wrong but still relevant.

Correction pattern:
1. acknowledge the attempt
2. state the corrected form
3. explain the key difference briefly

### `confirm`
Use when the learner answer is acceptable within `allowed_answer_scope`.

### `follow_up`
Use when the learner answer is correct enough and the system wants to deepen practice.

Examples:
- ask for another example
- ask for a full sentence
- ask for a role-play variation

### `review_prerequisite`
Use when the learner fails because prerequisite knowledge is missing.

## Readiness States
Use three stable readiness states for page goals and topic goals:

- `mastered`: the learner can answer or use the target independently
- `shaky`: the learner understands it roughly but uses it unstably or inaccurately
- `not_mastered`: the learner needs full explanation, modeling, guided practice, and correction

These states should be attached to concrete page goals, blocks, or topics rather than to the learner as a whole.

## Repair Mode
When the learner asks to split the task, says the sentence is too long, or wants to focus on one word, the system should switch into a lighter repair mode instead of continuing the original script.

Suggested `repair_mode` values:
- `none`
- `word_drill`
- `sentence_drill`
- `slow_read`
- `asr_clarify`

Examples:
- learner says "Can we split this?" -> `sentence_drill`
- learner says "I want to practice breakfast." -> `word_drill`
- learner output is probably an ASR confusion -> `asr_clarify`

## Evaluation Rules for `answer_question`
When `awaiting_answer = true`, evaluate in this order:
1. current block exact scope
2. current page related scope
3. current unit fallback scope

Do not jump to global retrieval unless the learner explicitly changes topic.

Evaluation result labels:
- `correct`
- `acceptable`
- `partially_correct`
- `incorrect`
- `off_topic`
- `unclear`

## Retrieval Policy
### Allowed
- `ask_knowledge`
- `meta_learning`
- `answer_question` only when local lesson context is insufficient

### Blocked by default
- `social`
- `navigation`
- `answer_question` during active local evaluation

## AIRI Output Mapping
The response planner may attach output cues for AIRI.

Suggested mapping:
- `confirm` -> positive expression, light nod
- `hint` -> thinking expression
- `correct` -> gentle serious expression
- `follow_up` -> encouraging expression
- `review_prerequisite` -> calm teaching expression

## Non-Goals
- multi-agent debate for each turn
- unrestricted retrieval during answer evaluation
- storing every response decision as long-term memory
- replacing pedagogy rules with prompt-only behavior
