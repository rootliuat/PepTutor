# Curriculum Evidence Review Queue

This is a human-review queue for offline curriculum evidence. It does not approve data mutation.

## Summary

- queue_count: 7
- p1_count: 4
- should_mutate_data_now_count: 0

## Queue

### CEQ-001 museum_shop_question

- query: Where is the museum shop?
- page_uid: TB-G6S1U1-P4
- priority: P1
- evidence_hit_count: 8
- review_reason: Review local evidence and any agent notes before deciding whether data tightening is needed.
- suggested_action: Compare structured evidence, audit evidence, and agent notes; decide whether to defer or open a data-review PR.
- should_mutate_data_now: False

### CEQ-003 height_question

- query: How tall is it?
- page_uid: TB-G6S2U1-P4
- priority: P1
- evidence_hit_count: 8
- review_reason: Review local evidence and any agent notes before deciding whether data tightening is needed.
- suggested_action: Compare structured evidence, audit evidence, and agent notes; decide whether to defer or open a data-review PR.
- should_mutate_data_now: False

### CEQ-004 p13_answer_scope

- query: TB-G6S2U2-P13 answer scope
- page_uid: TB-G6S2U2-P13
- priority: P1
- evidence_hit_count: 8
- review_reason: P13 answer-scope evidence remains human-reviewed and must not be inferred as return-anchor risk.
- suggested_action: Human-review answer-scope boundaries only; do not invent module-choice or return-anchor findings.
- should_mutate_data_now: False

### CEQ-005 phonics_cl_clean

- query: cl as in clean
- page_uid: TB-G5S2U1-P6
- priority: P1
- evidence_hit_count: 8
- review_reason: Phonics pattern/exemplar evidence should be reviewed for page-level inheritance, not data mutation.
- suggested_action: Review phonics inheritance/modeling before editing curriculum data.
- should_mutate_data_now: False

### CEQ-002 museum_shop_answer_frame

- query: It's near ...
- page_uid: TB-G6S1U1-P4
- priority: P3
- evidence_hit_count: 8
- review_reason: Review local evidence and any agent notes before deciding whether data tightening is needed.
- suggested_action: Compare structured evidence, audit evidence, and agent notes; decide whether to defer or open a data-review PR.
- should_mutate_data_now: False

### CEQ-006 favourite_food

- query: What's your favourite food?
- page_uid: TB-G5S1U3-P22
- priority: P3
- evidence_hit_count: 8
- review_reason: Review local evidence and any agent notes before deciding whether data tightening is needed.
- suggested_action: Compare structured evidence, audit evidence, and agent notes; decide whether to defer or open a data-review PR.
- should_mutate_data_now: False

### CEQ-007 story_scaffold_p31

- query: story scaffold P31
- page_uid: TB-G5S1U3-P31
- priority: P3
- evidence_hit_count: 8
- review_reason: Review local evidence and any agent notes before deciding whether data tightening is needed.
- suggested_action: Review story scaffold evidence and keep visible teaching-action changes separate.
- should_mutate_data_now: False
