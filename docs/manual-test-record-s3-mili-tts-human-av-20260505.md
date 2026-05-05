# PepTutor Human AV Re-observation: S3 Mili / TTS

Date: 2026-05-05  
Scope: focused live classroom re-observation after PR #13.  
Stack: `./scripts/start_lesson_dev.sh` with backend `127.0.0.1:9625` and frontend `127.0.0.1:5173/lesson`.

## Human AV Verdict

This pass closes the post-PR technical re-observation for `TB-G6S1U1-P4`: the visible reply no longer collapses to bare `museum shop`; it preserves both `Where is the museum shop?` and the answer frame `It's near ...`.

The strict human AV boundary is still not fully closed by this agent run because the operator must hear the audio and visually judge mouthOpen timing in the real browser. I can inspect live DOM, Sidebar, TTS playback state, stop reasons, overlap, mouthOpen numeric values, and visible reply text; I cannot honestly certify spoken naturalness or face/lip synchronization as a human listener/viewer.

Result: no code change yet. The next minimal fix slice should not start until a human operator fills the two unresolved AV fields:

- TTS naturalness as actually heard;
- mouthOpen synchronization as actually seen during playback.

## Rating Scale

Numeric ratings below are text/DOM proxy ratings only unless marked `human-required`.

| rating | meaning |
| --- | --- |
| 1 | bad / clearly broken |
| 2 | weak / noticeable problem |
| 3 | acceptable but not teacher-like |
| 4 | good enough for demo |
| 5 | natural and teacher-like |

## Observation Table

| page_uid | learner input | teacher visible reply | TTS / Sidebar evidence | ratings | issue bucket | next slice |
| --- | --- | --- | --- | --- | --- | --- |
| `TB-G5S1U3-P22` | `water` | `我听到你说 water，是“水”。这页的问题是：What's your favourite food?（你最喜欢的食物是什么？）你先说一个食物。` | route `answer_turn_policy`; action `hint`; speech `gentle_correction`; persona `mili_persona_capsule/v1 · full_soul=false`; TTS reached `http_ok` and `playback_ended`; overlap `false`; mouthOpen returned to `0.00`. | tts_naturalness `human-required`; mouthopen_sync `human-required`; teacher_likeness `4`; reply_naturalness `4`; not_overloaded `5`; student_action_clarity `4` | `acceptable_no_fix` | no |
| `TB-G6S1U1-P4` | `第一块`, then `turn left` | After PR #13: `我听到你说 turn left. 意思是“左转”。这页的问题是：Where is the museum shop?（博物馆商店在哪里？）可以用这个句型回答：It's near ...` | route `answer_turn_policy`; repair `reply_quality_revision;classroom_phrasing;redirect_reply_policy`; speech `gentle_correction`; persona `mili_persona_capsule/v1 · full_soul=false`; TTS `http_ok`, `playback=playing`; overlap `false`; mouthOpen numeric value changed during playback and was not stuck at `0.00`. | tts_naturalness `human-required`; mouthopen_sync `human-required`; teacher_likeness `4`; reply_naturalness `4`; not_overloaded `5`; student_action_clarity `4` | `acceptable_no_fix` | no |
| `TB-G6S2U1-P4` | `How tall are you?` | `我听到你说 How tall are you?，是“你有多高”。这页的问题是：How tall is it?（它有多高？）可以用这个句型回答：It's ... metres tall.` | route `answer_turn_policy`; speech `slow_split`; current block `TB-G6S2U1-P4-D2`; TTS `http_ok`; overlap `false`; visible target stayed on object-height question. | tts_naturalness `human-required`; mouthopen_sync `human-required`; teacher_likeness `4`; reply_naturalness `4`; not_overloaded `5`; student_action_clarity `5` | `acceptable_no_fix` | no |
| `TB-G5S1U3-P31` | `Zip` | `你说 Zip，我听到了。Zip 是故事里的角色。故事里老师问：What would Zoom like to eat?（Zoom 想吃什么？）你可以这样回答：Zoom would like ...` | route `answer_turn_policy`; action `hint`; speech `gentle_correction`; current block `TB-G5S1U3-P31-D1`; overlap `false`; story question and answer frame both visible. | tts_naturalness `human-required`; mouthopen_sync `human-required`; teacher_likeness `4`; reply_naturalness `4`; not_overloaded `4`; student_action_clarity `4` | `acceptable_no_fix` | no |
| `TB-G5S2U1-P6` | `water` | `我听到你说 water，是“水”。这一步练 cl 的发音，clean 里的 cl 要连起来读。跟我读：clean.` | route `answer_turn_policy`; action `hint`; speech `gentle_correction`; current block `TB-G5S2U1-P6-D1`; TTS `http_ok`; `cl' as in` absent. | tts_naturalness `human-required`; mouthopen_sync `human-required`; teacher_likeness `4`; reply_naturalness `4`; not_overloaded `5`; student_action_clarity `5` | `acceptable_no_fix` | no |
| `TB-G6S2U2-P13` | `What does had a cold mean?` | `哦，你问的是这个。had a cold就是“感冒了”的意思。比如，I had a cold last week. 我上周感冒了。好，现在回来刚才的小任务，你先试着说一遍：What did you do last weekend?（你上周末做了什么？）` | route `rag_plus_llm`; action `explain`; interrupt `finish_current_sentence`; current block `TB-G6S2U2-P13-D2`; did not reopen module choice. | tts_naturalness `human-required`; mouthopen_sync `human-required`; teacher_likeness `3`; reply_naturalness `3`; not_overloaded `3`; student_action_clarity `4` | `acceptable_no_fix` for current slice; monitor `textbook_data_or_answer_scope` / `redirect_reply_policy` if module-choice wording regresses | no immediate code |

## Post-PR G6S1 P4 Finding

Concrete check required by the goal:

- Input: `turn left`
- Visible reply preserved `Where is the museum shop?`: yes.
- Visible reply preserved `It's near ...`: yes.
- Visible reply collapsed to bare noun phrase `museum shop`: no.
- TTS request/playback surfaced in Sidebar: yes, `http_ok`, `playback=playing`, `overlap=false`.
- Human TTS naturalness: not certified in this agent run.

This closes the former P5 visible target regression from a text/DOM standpoint.

## Issue Register

| page_uid | observed behavior | why it is a real issue | bucket | suspected owner | priority | enters next minimal fix | work type |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all six | TTS naturalness is not human-certified in this run. | The goal asks whether Mili feels like a real teacher; DOM/TTS status cannot prove audible naturalness. | `tts_audio_quality` | human QA / frontend TTS observation | P1 | yes, as human observation, not code | manual AV judgement |
| all six | mouthOpen synchronization is not human-certified in this run. | Numeric mouthOpen values show movement/return, but do not prove lip timing quality. | `live2d_mouthopen_sync` | frontend Live2D observation | P1 | yes, as human observation, not code | manual AV judgement |
| `TB-G6S2U2-P13` | Vocab explanation plus return is longer than redirect-only turns. | Acceptable now, but it is the most likely page to feel less teacher-like under audio because it combines explanation and return anchor. | `visible_reply_wording` | `backend/LightRAG/lightrag/pedagogy/responder.py` / RAG return path, only if human review flags it | P3 | no current code | monitor |

## Next Minimal Fix Candidates

| rank | candidate | evidence | decision |
| --- | --- | --- | --- |
| 1 | Human AV signoff pass | Required fields remain `human-required` for TTS and mouthOpen. | Do this next; no code. |
| 2 | P13 vocab-return wording trim | P13 is acceptable technically but potentially less teacher-like because it explains vocab and returns in one turn. | Only consider if human audio review marks it long/unnatural. |
| 3 | Live2D expression capability gap | Sidebar reports `live2d_expression_unavailable:*` and `motion-only` fallback. | Not a classroom-content fix; separate Live2D asset/capability slice. |

## Recommendation

Recommendation: no code change yet. Complete one human-operated audio/visual pass using `docs/manual-test-s3-mili-tts-20260504.md`, and fill the two currently unresolved rating columns. The next code slice should be selected only after that pass identifies a concrete P1/P2 issue.

Budget record for this pass:

- full 20-page smoke: 0
- browser smoke: 0
- deep smoke: 0
- local dev stack: started once with `./scripts/start_lesson_dev.sh`
- focused browser UI observation: yes

## Completion Audit Against Goal

Objective restated: complete the remaining P3 human audio/visual observation boundary by observing the six target pages in the live lesson UI, rating Mili's teacher-likeness, TTS naturalness, and mouthOpen synchronization, and selecting exactly one next minimal fix slice or explicitly choosing no code change.

| requirement | evidence | status |
| --- | --- | --- |
| Use `./scripts/start_lesson_dev.sh` | Local stack started; backend ready on `127.0.0.1:9625`; Vite ready on `127.0.0.1:5173`. | complete |
| Open `http://127.0.0.1:5173/lesson` | Focused browser observation was performed through the live UI. | complete |
| Use checklist `docs/manual-test-s3-mili-tts-20260504.md` | The six checklist pages and inputs are mirrored in the observation table. | complete |
| Record all six target pages | Table includes `TB-G5S1U3-P22`, `TB-G6S1U1-P4`, `TB-G6S2U1-P4`, `TB-G5S1U3-P31`, `TB-G5S2U1-P6`, `TB-G6S2U2-P13`. | complete |
| Re-observe `TB-G6S1U1-P4` after PR #13 using `turn left` | The G6S1 P4 row and post-PR section record the `turn left` result. | complete |
| Confirm G6S1 P4 preserves `Where is the museum shop?` | Visible reply contains `Where is the museum shop?（博物馆商店在哪里？）`. | complete |
| Confirm G6S1 P4 preserves `It's near ...` | Visible reply contains `可以用这个句型回答：It's near ...`. | complete |
| Confirm G6S1 P4 no longer collapses to bare `museum shop` | Reply uses the full question and answer frame; it is not a bare noun phrase drill. | complete |
| Record visible teacher reply | Each page row has the visible reply text. | complete |
| Record TTS text when visible/inferable | Current teacher line doubles as inferable TTS text; TTS status is recorded in each row. | complete |
| Record Sidebar route/action/speech/persona/interrupt/TTS fields | Each row records the available Sidebar route/action/speech/persona/TTS/interrupt evidence, with more detail for the newly re-observed G6S1 P4 path. | complete |
| Record playback status, stop reason, overlap | Table and post-PR section record `http_ok`, playing/ended, stop/overlap where observed. | complete |
| Rate teacher-likeness | Proxy text/DOM ratings are present for each page. | complete as proxy |
| Rate reply naturalness, not_overloaded, student_action_clarity | Proxy ratings are present for each page. | complete as proxy |
| Rate TTS naturalness | Marked `human-required` for every page. A browser DOM observer cannot hear and judge audio quality. | incomplete |
| Rate mouthOpen synchronization | Marked `human-required` for every page. Numeric mouthOpen values show movement/return but cannot prove natural synchronization. | incomplete |
| Record whether Mili feels like a real English teacher | Text/reply proxy ratings are present; true AV judgement remains blocked by missing human listener/viewer signoff. | partially complete |
| Use concrete issue buckets | Issue register uses `tts_audio_quality`, `live2d_mouthopen_sync`, `visible_reply_wording`, and `acceptable_no_fix`. | complete |
| Identify next minimal fix slice | Recommendation is `no code change yet`; next required slice is human AV signoff, not implementation. | complete |
| Do not run full smoke | `full 20-page smoke: 0`. | complete |
| Do not run browser smoke | `browser smoke: 0`. | complete |
| Do not run deep smoke | `deep smoke: 0`. | complete |
| Do not change classroom/runtime behavior | This pass created only this observation document. | complete |

Completion status: not fully achieved. The remaining uncovered requirements are the true human audio and visual ratings for TTS naturalness and mouthOpen synchronization. Treat this as an explicit blocker, not as a code failure.
