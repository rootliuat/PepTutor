# Lesson Teacher Mind Roundtable Consensus

## Purpose
This document records the accepted architecture conclusions from the repeated roundtable discussions about making PepTutor feel like a real prepared teacher rather than a robotic RAG answer system.

The goal is not to preserve every debate transcript. The goal is to convert the accepted conclusions into implementation constraints.

## Core Shift
PepTutor should not run as:

```text
student input -> RAG -> answer
```

It should run as:

```text
prepared teacher mind
-> current lesson state
-> learner signal
-> teaching move
-> natural teacher response
-> AIRI visible performance
```

RAG remains necessary, but it is an evidence and preparation tool. It is not the main teacher mind for every turn.

## Authority Order
Runtime decisions must follow this order:

```text
system_contract
> curriculum facts / LessonBrief
> lesson state and answer rubric
> scoped retrieval evidence
> learner memory
> teacher soul / persona
> AIRI presentation layer
```

This prevents personality, memory, or visual performance from changing textbook facts, target answers, routing, or progression.

## Layer Responsibilities
- `CurriculumMap`: offline four-book index for grade, semester, unit, pages, vocabulary, patterns, page types, block UIDs, targets, source refs, and confidence.
- `LessonEvidence`: exact page/block evidence found by UID and metadata first, with scoped retrieval only as support.
- `LessonBrief`: private teacher preparation for the active page/block. It describes goals, materials, answer scope, likely mistakes, support vocabulary, and progression.
- `TeachingMovePlanner`: chooses the classroom move from learner signal plus current brief.
- `LessonResponder`: uses LLM to speak naturally as the teacher, using the move, brief, soul, and memory boundaries.
- `SimpleMem`: stores and recalls learner facts, episodes, and procedures for personalization only.
- `LightRAG`: retrieves textbook/support evidence inside the current scope.
- `AIRI`: presents the teacher through voice, timing, mouth movement, expression, motion, interruption, and classroom-state reactions.

## Non-Negotiable Boundaries
- No page-specific fixed teacher scripts.
- No fixed Q&A templates per textbook page.
- No hand-authored unit goals based on memory or broad impressions.
- No whole-book, whole-unit, or full `CurriculumMap` dump into live `/lesson/turn`.
- No unbounded Agentic RAG loops in a live class turn.
- No persona override of target answer, correctness, page progression, retrieval scope, or required teaching action.
- No memory override of current textbook facts.

## Curriculum Design Decision
The four PEP books should be organized, but only as an offline `CurriculumMap`.

Minimum map fields:

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

The current corpus is sufficient for a first generator: raw textbook files, word lists, Useful expressions, `structured/general/*`, and page-level pilot assets.

If a generated field is uncertain, keep the field but mark `confidence` and `source_refs`. Do not silently turn guesses into authoritative curriculum facts.

## LessonBrief Decision
`LessonBrief` is the teacher's preparation, not what the teacher reads aloud.

It should answer:

- what this page/block is actually teaching
- what materials matter now
- what answers are acceptable
- what support vocabulary or patterns are nearby
- what mistakes are likely
- what the next teaching move can be
- what should not be changed by persona or memory

The LLM may use the brief to produce natural classroom language. The brief itself must not become fixed wording.

## Teaching Strategy Decision
PepTutor needs a reusable strategy layer. The strategy is not page-specific. It should handle common learner signals:

- learner refuses or says they do not want to answer
- learner repeats the task instruction instead of producing an answer
- learner gives a word or incomplete phrase
- learner makes a small grammar or word-choice error
- learner asks a knowledge question
- learner asks for help
- learner goes off-topic
- learner answers well enough to move forward

Each selected move should be auditable:

- detected learner signal
- selected teaching move
- evidence or brief fields used
- short rationale
- expected next learner action

## Grade And Learning Stage Decision
G5/G6 students should not be treated like adults or high-school learners.

Use two separate dimensions:

- `learner_stage_profile`: grade-band constraints for tone, cognitive load, correction style, and amount of Chinese support.
- `turn_learning_phase`: what is happening this turn, such as `input`, `imitate`, `produce`, `repair`, or `extend`.

Grade controls how the teacher speaks. Current learning phase controls what the teacher does.

Practical constraints:

- one teaching focus per turn
- short concrete teacher sentences
- low-pressure correction
- limited grammar terminology
- more modeling and sentence frames for weaker answers
- extension only after the learner has enough control

## RAG Decision
RAG is still used, but it must be scoped and content-derived.

When `page_uid` or `block_uid` is known:

1. exact UID and metadata lookup first
2. page/block evidence second
3. same-page or same-unit support third
4. vector retrieval only as scoped supplement

For example:

- `TB-G5S1U3-P31` should retrieve the actual Story time content before deciding how to teach it.
- `TB-G6S2Recycle2-P49-D4` should retrieve the D4 task and nearby party-item support such as D1 vocabulary.

Do not decide that P31 is "story follow-reading" or P49 is "open expression" before inspecting actual content.

## Memory Decision
SimpleMem remains useful, but memory has a strict role.

Memory should be layered:

- `fact`: stable learner information after repeated evidence
- `episode`: recent lesson event or mistake
- `procedure`: teaching preference or support style

Memory can suggest pacing, scaffolding, encouragement style, or likely weak points. It cannot change the current page target, acceptable answer scope, or correctness judgment.

## Persona And Soul Decision
The teacher soul should define personality, not curriculum authority.

`soul.md` should shape:

- warmth
- rhythm
- patience
- humor level
- challenge level
- correction style
- relationship with learner

It should not contain hard lesson facts, page-specific scripts, answer rubrics, or retrieval rules.

The durable split should be:

- `system_contract`: authority, safety, boundaries, content rules
- `teacher_soul`: stable teacher personality
- `LessonBrief`: current page/block preparation
- `memory`: learner personalization hints

## AIRI Decision
AIRI is important because it creates the "real presence" feeling. It is a presentation and interaction layer, not the curriculum brain.

AIRI should reflect:

- listening
- learner speaking
- thinking
- teacher speaking
- interrupted
- encouragement
- repair/correction
- successful answer

The target is not just TTS playback. The target is a synchronized loop:

```text
teacher intent -> voice pacing -> mouth intensity -> expression -> motion -> interruption policy
```

The visual layer should make the teacher feel alive while staying subordinate to the lesson contract.

## Sample Lesson Decision
Sample pages are for evaluation, not templates.

`G6 S2 Recycle2 P49` is useful as a gold page because the current UI, Theme wording issue, party-list task, AIRI display, and naturalness concerns all surfaced there.

But P49 must not become a hardcoded teaching script. It should only validate whether the reusable architecture handles:

- reluctant learner
- task-instruction echo
- incomplete answer
- small grammar error
- off-topic turn
- good answer and progression

Any future P31 or P49 test must be generated from actual recalled content and brief fields.

## Quality Evaluation Decision
Do not judge teacher quality by whether it says a fixed phrase.

Evaluate:

- retrieval scope correctness
- source grounding
- no cross-grade or cross-unit leakage
- answer correctness
- natural teacher response
- no curriculum metadata leakage
- persona consistency
- memory use without override
- teaching move rationale
- state progression
- AIRI performance-plan completeness

## Implementation Order
The roundtable consensus implies this build order:

1. Generate `CurriculumMap` from existing four-book assets.
2. Add exact `LessonEvidence` lookup by page/block UID and metadata.
3. Build `LessonBriefBuilder`.
4. Add `TeachingMovePlanner` with auditable moves.
5. Feed `LessonBrief + teaching_move + memory + soul` into `LessonResponder`.
6. Update evals to check source grounding, brief quality, move rationale, and naturalness.
7. Keep AIRI visible-layer validation after backend turn intent is reliable.

## Acceptance Standard
PepTutor reaches the intended direction when a reviewer can inspect a live turn and see:

```text
which page/block evidence was used
what the brief says this lesson is about
what learner signal was detected
why this teaching move was selected
how memory/persona shaped delivery without changing facts
how AIRI expressed the turn
why the response is natural but still grounded
```

If those fields are visible and testable, the system is moving toward a real teacher feeling. If the response only shows a retrieved paragraph or a fixed phrase, it has drifted back into chatbot/RAG mode.
