# Curriculum Retrieval Comparison Report

This report compares local curriculum evidence hits with offline agentic harness outputs.

RAGFlow/agentic evidence is supporting evidence only. `app/knowledge/structured` remains canonical.

## Summary

- query_count: 7
- provider: none
- status_counts: `{"prompt_only_needs_human_review": 7}`
- evidence_source_counts: `{"audit": 1, "candidate": 3, "structured": 52}`

## Query Comparison

### museum_shop_question

- query: Where is the museum shop?
- page_uid: TB-G6S1U1-P4
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"structured": 8}`
- provider_called: False
- provider_exit_code: None

### museum_shop_answer_frame

- query: It's near ...
- page_uid: TB-G6S1U1-P4
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"structured": 8}`
- provider_called: False
- provider_exit_code: None

### height_question

- query: How tall is it?
- page_uid: TB-G6S2U1-P4
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"structured": 8}`
- provider_called: False
- provider_exit_code: None

### p13_answer_scope

- query: TB-G6S2U2-P13 answer scope
- page_uid: TB-G6S2U2-P13
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"candidate": 1, "structured": 7}`
- provider_called: False
- provider_exit_code: None

### phonics_cl_clean

- query: cl as in clean
- page_uid: TB-G5S2U1-P6
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"candidate": 2, "structured": 6}`
- provider_called: False
- provider_exit_code: None

### favourite_food

- query: What's your favourite food?
- page_uid: TB-G5S1U3-P22
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"audit": 1, "structured": 7}`
- provider_called: False
- provider_exit_code: None

### story_scaffold_p31

- query: story scaffold P31
- page_uid: TB-G5S1U3-P31
- status: prompt_only_needs_human_review
- evidence_hit_count: 8
- source_counts: `{"structured": 8}`
- provider_called: False
- provider_exit_code: None
