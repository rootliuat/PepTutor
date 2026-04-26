# Pilot Unit 3 Slicing Plan

## Goal
Build the first manual pilot for `G5 S1 Unit 3, p24-p31` so the teacher can stay on-page, probe lightly, and teach from classroom-sized knowledge slices instead of raw page text.

## Scope
- textbook range: `五年级上册 Unit 3, p24-p31`
- supported user entries:
  - `学习五年级上册第31页`
  - `五年级上31页`
  - `学习五年级上第三单元`
- priority classroom scenes:
  - dialogue teaching
  - error correction
  - interactive follow-up
- language style:
  - Chinese-led explanation
  - English practice and repetition

## Source Files
- raw textbook: [01.五年级上册语料.js](/F:/TestCode/github_project/PepTutor/app/knowledge/raw/01.五年级上册语料.js)
- word list: [05.五年级上册单词表.md](/F:/TestCode/github_project/PepTutor/app/knowledge/raw/05.五年级上册单词表.md)
- useful expressions: [09.五年级上册Useful expressions.md](/F:/TestCode/github_project/PepTutor/app/knowledge/raw/09.五年级上册Useful%20expressions.md)

## Page Map
| Page | Current raw focus | Planned `page_type` | Stage priority |
| :--- | :--- | :--- | :--- |
| p24 | food and drink ordering dialogue | `dialogue` | A |
| p25 | food vocabulary and role-play | `vocabulary` | A |
| p26 | `ow` phonics page | `phonics` | B |
| p27 | favourite food dialogue | `dialogue` | A |
| p28 | food description adjectives | `vocabulary` | A |
| p29 | Robin note reading task | `reading` | A |
| p30 | check and wrap-up | `review` | B |
| p31 | story time | `story` | A |

Stage `A` pages should be sliced first because they directly support the target scenes. Stage `B` pages stay in scope for the pilot unit, but can be normalized after the main flow is stable.

## Slicing Principle
Do not slice by file, paragraph, or full-page chunk. Slice by what a teacher would actually teach in one short classroom move.

Each `TeachingBlock` must satisfy all of the following:
- one clear teaching goal
- one short Chinese overview is possible
- one or two short probe questions are possible
- learner state can be judged as `mastered`, `shaky`, or `not_mastered`
- a repair path exists if the learner gets stuck

## Output Layers
### 1. `PageLesson`
One record per page.

Required fields for the pilot:
- `page_uid`
- `grade`
- `semester`
- `unit`
- `page`
- `page_type`
- `page_intro_cn`
- `entry_probe_questions`
- `priority_blocks`

### 2. `TeachingBlock`
Main classroom unit for routing, retrieval, and answer evaluation.

Required fields for the pilot:
- `block_uid`
- `page_uid`
- `page_type`
- `block_type`
- `teaching_goal`
- `teaching_summary`
- `focus_vocabulary`
- `core_patterns`
- `allowed_answer_scope`
- `entry_probe_questions`
- `repair_modes`
- `next_block_uids`

### 3. `KnowledgeAtom`
Small support knowledge that should not directly drive the whole lesson.

Pilot atom types:
- `word`
- `phrase`
- `sentence_pattern`
- `phonics_pattern`
- `grammar_hint`

### 4. `LearningTarget`
Knowledge-point level mastery target used by diagnosis and memory write-back.

Examples:
- `LT-G5S1U3-P24-pattern-what-would-you-like-to-eat`
- `LT-G5S1U3-P25-word-sandwich`
- `LT-G5S1U3-P29-reading-food-preference-note`

## First-Pass Block Plan
### p24 `dialogue`
- block 1: understand `I'm hungry.` and `What would you like to eat?`
- block 2: answer with `A sandwich, please.`
- block 3: extend to drink question `What would you like to drink?`

### p25 `vocabulary`
- block 1: recognize and say `tea`, `ice cream`, `sandwich`, `hamburger`, `salad`
- block 2: use `I'd like ...` to order one item
- block 3: role-play waiter and customer

### p27 `dialogue`
- block 1: ask `What's your favourite food?`
- block 2: answer with `... . It's/They're ...`
- block 3: follow up from menu to preference

### p28 `vocabulary`
- block 1: adjectives `fresh`, `healthy`, `delicious`, `hot`, `sweet`
- block 2: describe food with `It is ...` or `They are ...`

### p29 `reading`
- block 1: understand likes and dislikes in Robin notes
- block 2: identify what both people can eat
- block 3: write a simple note to Robin

### p31 `story`
- block 1: story entry and key action chain
- block 2: core dialogue replay
- block 3: retell or role-play with scaffold

## Repair Strategy
The pilot only needs a small repair set:
- `repeat`
- `slow_read`
- `word_drill`
- `sentence_drill`
- `choice_probe`
- `asr_clarify`

Use them only inside the current block unless the learner clearly asks to navigate elsewhere.

## Task Breakdown
### Task 1
Freeze the page map and block map for `p24-p31`.

Acceptance:
- every page has one `page_type`
- every page has a short Chinese intro
- every page has 1 to 2 entry probes

Validation:
- review by file inspection
- confirm that no page is left without `page_type` or probe questions

### Task 2
Manually normalize stage `A` pages into `PageLesson` and `TeachingBlock` records.

Acceptance:
- `p24`, `p25`, `p27`, `p28`, `p29`, `p31` each have classroom-sized blocks
- each block has a clear `teaching_goal` and `repair_modes`

Validation:
- replay page-level requests against the normalized data
- confirm that each request stays on the requested page

### Task 3
Extract `KnowledgeAtom` support data from the unit word list and useful expressions.

Acceptance:
- unit words are linked to at least one page or block
- useful expressions are mapped to sentence-pattern atoms

Validation:
- sample-check `sandwich`, `salad`, `What would you like to eat?`, `What's your favourite food?`

### Task 4
Add `LearningTarget` IDs and page-entry diagnosis prompts.

Acceptance:
- every high-priority block has at least one mastery target
- every target can be judged as `mastered`, `shaky`, or `not_mastered`

Validation:
- run three manual dialogue cases per target:
  - correct independent answer
  - partial answer with prompting
  - wrong or missing answer

### Task 5
Backfill stage `B` pages `p26` and `p30`.

Acceptance:
- `p26` is usable as a phonics page
- `p30` is usable as a review page

Validation:
- check that phonics and review do not reuse dialogue flow by mistake

## Scenario Validation
### Scenario A: page entry
Input: `学习五年级上册第31页`

Pass criteria:
- teacher gives a short Chinese page overview
- teacher asks 1 to 2 short probes
- teacher does not jump to another page

### Scenario B: correction
Input:
- teacher asks for `I'm hungry.`
- learner says `I am hungry` or misreads a food word

Pass criteria:
- teacher keeps the current block
- teacher corrects lightly first
- teacher can switch to `word_drill` or `sentence_drill`

### Scenario C: interaction
Input:
- learner says `能拆开练吗`
- learner asks `只练这个单词`

Pass criteria:
- teacher immediately shrinks the task
- teacher stays on current knowledge target
- teacher does not start a new page or a new long script

## Out of Scope for This Slice
- full automation for all grades
- final vector ingestion pipeline
- long-term memory write-back implementation
- frontend voice integration

## Completion Rule
This pilot slice is complete only when the normalized data can support the three priority scenes above with explicit validation notes, not just file conversion.
