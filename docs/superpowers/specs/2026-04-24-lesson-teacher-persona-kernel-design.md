# Lesson Teacher Persona Kernel Design

Date: 2026-04-24

## Status

This document defines the next `/lesson` architecture direction: keep the deterministic PepTutor lesson runtime as the teaching brain, add an Alma-inspired persona and memory kernel for teacher consistency, and let AIRI remain the visible body, voice, lip-sync, expression, and motion layer.

This is a design document only. It does not claim the implementation is complete.

## Goal

Make `/lesson` feel like a stable teacher with a recognizable independent presence, not a stateless lesson answer generator.

The target experience is:

- the teacher remembers the learner's habits, anxiety, preferences, recurring mistakes, and progress
- the teacher has stable style, boundaries, warmth, pacing, and classroom habits across turns
- the teacher reacts emotionally in a continuous way instead of resetting each turn
- AIRI speech, mouth movement, face, and body reflect the teacher state
- textbook correctness, page state, retrieval, and answer evaluation remain deterministic and auditable

## Alma Lessons To Borrow

Alma is not a character runtime to copy directly. The useful ideas are architectural:

- memory is extracted during conversation, stored with embeddings, retrieved before response, and used for contextual answers
- memories can be viewed, edited, tagged, assigned importance, and pruned
- tool use is split from normal conversation, with a lightweight tool model handling selection and background operations
- Skills use progressive disclosure so only relevant behavior instructions enter the context window
- Workspaces and MCP show a clean boundary between chat, tools, files, and external integrations

Sources:

- `https://alma.now/`
- `https://alma.now/docs/features/memory`
- `https://alma.now/docs/features/tools`
- `https://alma.now/docs/features/skills`
- `https://alma.now/docs/guide/`

## Non-Goals

- Do not turn `/lesson` into a free-form companion chat route.
- Do not let AIRI or a frontend prompt generate independent lesson answers.
- Do not let a general tool agent override page, block, answer target, or correction policy.
- Do not move real-time classroom turns onto a slow VFS-heavy research path.
- Do not copy Alma's product surface or provider UI.
- Do not claim full long-term character autonomy before it is measured in regression tests.

## Core Boundary

There must be one content authority and one presentation authority:

- **PepTutor LessonRuntime owns teaching content.** It controls page state, teaching block, answer target, retrieval mode, evaluation, remediation, and final teacher text.
- **Teacher Persona Kernel owns delivery style and continuity.** It shapes how the teacher sounds, remembers the relationship, tracks classroom affect, and emits performance intent.
- **AIRI owns embodied execution.** It speaks the text, drives mouth sync, expression, motion, interruption behavior, and visible stage state.

The runtime contract is:

`student voice -> ASR -> LessonRuntime -> controlled retrieval -> SimpleMem recall -> Teacher Persona Kernel -> LessonResponder -> AIRI performance plan -> TTS/lip-sync/expression/motion`

## Architecture

### 1. LessonRuntime

Responsibilities:

- load the active page, block, target sentence, and lesson manifest state
- classify the student turn as answer, help request, knowledge question, social turn, or branch
- run scoped retrieval through structured assets and optional vector retrieval
- evaluate answers and choose the next teaching action
- call the responder with compact lesson facts and persona context
- emit final `LessonTurnResult` and streaming text deltas

It must not:

- allow a free agent to choose an unrelated teaching goal
- let retrieved memories overwrite textbook targets
- let frontend notebook state influence backend teaching decisions

### 2. Teacher Persona Kernel

Responsibilities:

- assemble a compact persona context for each turn
- merge stable teacher identity with learner relationship memory
- maintain classroom affect state across turns
- produce a structured AIRI performance plan
- expose debug metadata so persona influence is inspectable

The kernel should be small and deterministic around the model call. It should not become a hidden second chatbot.

Suggested backend components:

- `TeacherPersonaProfile`: stable identity, voice, boundaries, teaching style, do/don't rules, catchphrases, pacing.
- `LearnerRelationshipProfile`: SimpleMem-derived facts, mistakes, preferences, mastery signals, confidence trend.
- `ClassroomAffectState`: teacher mood, student confidence, frustration/stuckness, interruption state, energy.
- `PersonaPromptAssembler`: produces compact prompt sections for `LessonResponder`.
- `AiriPerformancePlanner`: converts result metadata and affect state into `emotion`, `expression`, `motion`, `speech_style`, `mouth_intensity`, and `interrupt_policy`.

### 3. SimpleMem

SimpleMem remains the learner long-term memory authority for `/lesson`.

The next design should organize memory into three Alma-like layers:

- **Facts:** durable student facts and preferences, such as "needs slower split practice".
- **Episodes:** compressed lesson summaries, such as "P49 recycle speaking practice was completed after two retries".
- **Procedures:** learned teaching adaptations, such as "when this learner says they are stuck, give a Chinese explanation first, then a short English retry".

These layers should be retrieved before a response, but they must be filtered by:

- project
- student id
- lesson scope
- current session exclusion when needed
- relevance to the active page or block

### 4. LightRAG

LightRAG remains the textbook knowledge and route service.

The desired retrieval stack is controlled hybrid retrieval:

- exact lookup for UID, page, unit, target sentence, support asset, and textbook metadata
- scoped support-asset matching for vocabulary and useful expressions
- optional vector reranking within deterministic scope
- future graph relations between page, block, target sentence, common mistake, and support asset
- bounded query rewrite only for knowledge/help turns, with a strict retry limit

The system should not run unbounded agentic search during live speech turns.

### 5. AIRI Runtime

AIRI remains the user-facing embodied teacher.

Responsibilities:

- play teacher TTS and drive teacher mouth movement
- stop playback immediately on barge-in
- render listening, thinking, speaking, interrupted, encouraging, and correction states
- apply backend `AiriPerformancePlan`
- never rewrite backend teacher text

The frontend may choose a safe fallback expression or motion if a specific model cannot perform the requested action.

## Data Contract

The backend should eventually expose a structured persona/performance block inside the lesson debug and action payload:

```json
{
  "persona": {
    "profile_id": "peptutor-teacher-v1",
    "relationship_signals": ["slow_split_practice", "article_omission"],
    "affect_state": {
      "student_confidence": "low",
      "teacher_energy": "calm",
      "stuckness": 0.7
    }
  },
  "airi_performance": {
    "emotion": "encouraging",
    "expression": "soft_smile",
    "motion": "Explain",
    "speech_style": "slow_split",
    "mouth_intensity": 0.8,
    "interrupt_policy": "barge_in_allowed"
  }
}
```

The payload is advisory for AIRI presentation. It is not a second source of lesson content.

## Prompt Boundary

The responder prompt should be assembled from explicit sections:

- lesson objective
- current page/block facts
- selected retrieval/support facts
- answer evaluation and required teaching action
- learner relationship memory
- teacher persona style
- output constraints

The persona section may shape tone, pacing, encouragement, and classroom habits. It must not change:

- target answer
- correctness judgment
- page progression
- retrieval source facts
- required remediation action

## Real-Time Constraints

This design must protect live classroom latency:

- no VFS read loops in the hot path
- no unbounded search or tool loops in the hot path
- memory recall must return compact cards, not raw history
- teacher text should stream as soon as generation starts
- action/performance payload should be available before or near first audio
- interruption must cancel stale speech and stale lesson results

## Debug And Observability

Every persona-enabled turn should make the following visible in debug signals or logs:

- persona profile id and version
- which memory buckets were recalled
- which relationship signals influenced the response
- current classroom affect state
- selected speech style, emotion, expression, and motion
- whether the frontend applied or fell back from the requested action

This is necessary because "independent personality" is otherwise impossible to review objectively.

## Acceptance Criteria

This design is accepted only when the implementation can prove:

- the teacher keeps a stable persona across a multi-turn lesson
- student-specific memory changes how the teacher scaffolds without changing lesson correctness
- AIRI expression and mouth movement match teacher speaking state
- interruptions stop old playback and prevent stale result application
- debug signals reveal recall, persona, affect, and performance decisions
- tests catch persona drift, cross-student memory leakage, and lesson-goal override

## Risks

- Too much persona text can dilute lesson correctness.
- Too much memory recall can make the teacher overfit one old mistake.
- If frontend and backend both author personality, the teacher will feel inconsistent.
- If performance mapping is not observable, visual behavior will be hard to debug.
- If the hot path becomes agentic and tool-heavy, real-time voice quality will regress.

## Design Decision

Use a controlled Persona Kernel, not a free companion agent.

The strongest version of PepTutor is:

`AIRI embodiment + Alma-style memory/persona discipline + PepTutor deterministic teaching runtime`.
