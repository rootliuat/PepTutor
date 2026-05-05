# PepTutor Manual Test Record: S3 Mili / TTS

Status: technical observation completed; human audio/visual judgement still pending.

This file is the manual observation record for:

```text
docs/manual-test-s3-mili-tts-20260504.md
```

Do not treat browser smoke as a substitute for this record. Browser smoke has verified that the route-focused real-browser harness can run. The observations below were gathered through the live browser UI and Sidebar state, but spoken TTS quality, mouthOpen naturalness, and whether Mili feels like a real teacher still need human judgement.

## Environment

- Project path: `/root/my-project/PepTutor`
- Startup command: `./scripts/start_lesson_dev.sh`
- Browser URL: `http://127.0.0.1:5173/lesson`
- Browser smoke reference: `temp/lesson-smoke-artifacts/lesson_browser_smoke_20260505_101008.json`
- Browser smoke status: `passed`

## Observation Fields

For each page, fill:

- Learner input
- Teacher response excerpt
- Sidebar values
- TTS playback state
- Mechanical wording: yes / no
- Overloaded turn: yes / no
- Off-route textbook behavior: yes / no
- mouthOpen abnormal: yes / no
- Interrupt abnormal: yes / no
- Classification
- Owner file
- Priority
- Allowed into next fix slice: yes / no

## TB-G5S1U3-P22

Focus: favourite food scaffold.

Technical observation:

| Field | Value |
| --- | --- |
| Learner input | `water` |
| Teacher response excerpt | `我听到你说 water，是“水”。这页的问题是：What's your favourite food?（你最喜欢的食物是什么？）你先说一个食物。` |
| Sidebar values | route `answer_turn_policy`; repair `reply_quality_revision;classroom_phrasing;redirect_reply_policy`; action `hint`; speech `gentle_correction`; persona `mili_persona_capsule/v1 · full_soul=false`; interrupt `barge_in_allowed`; overlap `false` |
| TTS playback state | `synthesis=http_ok`; playback ended cleanly; `stop_type=playback_ended`; audio about 10992ms |
| Mechanical wording | no |
| Overloaded turn | no |
| Off-route textbook behavior | no |
| mouthOpen abnormal | not confirmed by human; Sidebar returned to `open=0.00` after playback |
| Interrupt abnormal | no |
| Classification | acceptable S3 visible reply |
| Owner file | none |
| Priority | none |
| Allowed into next fix slice | no |

## TB-G6S1U1-P4

Focus: museum shop / location question.

Technical observation:

| Field | Value |
| --- | --- |
| Learner input | `第一块`, then `turn left` |
| Teacher response excerpt | After `turn left`: `我听到你说 turn left. 意思是“左转”。这页我们先看地点词：museum shop（博物馆商店）。你先读一遍。` |
| Sidebar values | route `answer_turn_policy`; repair `reply_quality_revision;redirect_reply_policy`; action `hint`; speech `gentle_correction`; persona `mili_persona_capsule/v1 · full_soul=false`; current block `TB-G6S1U1-P4-D2`; interrupt `barge_in_allowed`; overlap `false` |
| TTS playback state | TTS generated/played; one prior playback showed `stop=lesson-learner-send` when learner input was sent while speech was still active |
| Mechanical wording | partial: reply is natural enough sentence-by-sentence, but target is narrowed to `museum shop` |
| Overloaded turn | no |
| Off-route textbook behavior | yes, target narrows from location question/answer pair to noun phrase |
| mouthOpen abnormal | not confirmed by human |
| Interrupt abnormal | no; visible stop reason is reported |
| Classification | redirect helper / TeachingMove target-action issue |
| Owner file | `backend/LightRAG/lightrag/pedagogy/redirect_reply_policy.py`; possibly `backend/LightRAG/lightrag/orchestrator/teaching_move_planner.py` |
| Priority | P1 for next visible-experience slice |
| Allowed into next fix slice | yes, only as public question/answer target/action rule; no page_uid or smoke-input special case |

## TB-G6S2U1-P4

Focus: object-height answer frame.

Technical observation:

| Field | Value |
| --- | --- |
| Learner input | `第一块`, then `How tall are you?` |
| Teacher response excerpt | `我听到你说 How tall are you?，是“你有多高”。这页的问题是：How tall is it?（它有多高？）可以用这个句型回答：It's ... metres tall.` |
| Sidebar values | route `answer_turn_policy`; repair `reply_quality_revision;redirect_reply_policy`; action `hint`; speech `slow_split`; persona `mili_persona_capsule/v1 · full_soul=false`; current block `TB-G6S2U1-P4-D2`; interrupt `barge_in_allowed`; overlap `false` |
| TTS playback state | `synthesis=http_ok`; playback active during observation; earlier learner send produced `stop_type=manual_send_interrupt` as expected for barge-in/manual send |
| Mechanical wording | no |
| Overloaded turn | no |
| Off-route textbook behavior | no |
| mouthOpen abnormal | not confirmed by human; Sidebar showed active mouth/open values during playback |
| Interrupt abnormal | no |
| Classification | acceptable S3 visible reply; S4 visible stop reason evidence present |
| Owner file | none |
| Priority | none |
| Allowed into next fix slice | no |

## TB-G5S1U3-P31

Focus: story answer scaffold.

Technical observation:

| Field | Value |
| --- | --- |
| Learner input | `Zip` |
| Teacher response excerpt | `你说 Zip，我听到了。Zip 是故事里的角色。故事里老师问：What would Zoom like to eat?（Zoom 想吃什么？）你可以这样回答：Zoom would like ...` |
| Sidebar values | route `answer_turn_policy`; repair `reply_quality_revision;redirect_reply_policy`; action `hint`; speech `gentle_correction`; persona `mili_persona_capsule/v1 · full_soul=false`; current block `TB-G5S1U3-P31-D1`; interrupt `barge_in_allowed`; overlap `false` |
| TTS playback state | TTS synthesis started; stop reason showed `lesson-learner-send` from sending during active/queued audio |
| Mechanical wording | no |
| Overloaded turn | no |
| Off-route textbook behavior | no |
| mouthOpen abnormal | not confirmed by human |
| Interrupt abnormal | no |
| Classification | acceptable story scaffold |
| Owner file | none |
| Priority | none |
| Allowed into next fix slice | no |

## TB-G5S2U1-P6

Focus: phonics scaffold for `cl` / `clean`.

Technical observation:

| Field | Value |
| --- | --- |
| Learner input | `第二块`, then `water` |
| Teacher response excerpt | `我听到你说 water，是“水”。这一步练 cl 的发音，clean 里的 cl 要连起来读。跟我读：clean.` |
| Sidebar values | route `answer_turn_policy`; repair `reply_quality_revision;redirect_reply_policy`; action `hint`; speech `gentle_correction`; persona `mili_persona_capsule/v1 · full_soul=false`; current block `TB-G5S2U1-P6-D1`; interrupt `barge_in_allowed`; overlap `false` |
| TTS playback state | `synthesis=http_ok`; playback active during observation |
| Mechanical wording | no |
| Overloaded turn | no |
| Off-route textbook behavior | no |
| mouthOpen abnormal | not confirmed by human; Sidebar showed active open value while playing |
| Interrupt abnormal | no |
| Classification | acceptable phonics scaffold |
| Owner file | none |
| Priority | none |
| Allowed into next fix slice | no |

## TB-G6S2U2-P13

Focus: P13 vocabulary return and answer-scope boundary.

Technical observation:

| Field | Value |
| --- | --- |
| Learner input | `第一块`, then `What does had a cold mean?` |
| Teacher response excerpt | `哦，你问的是这个。had a cold就是“感冒了”的意思。比如，I had a cold last week. 我上周感冒了。好，现在回来刚才的小任务，你先试着说一遍：What did you do last weekend?（你上周末做了什么？）` |
| Sidebar values | route `rag_plus_llm`; action `explain`; content source `lesson_runtime_teacher_response`; retrieval `当前单元`; persona `mili_persona_capsule/v1 · full_soul=false`; current block `TB-G6S2U2-P13-D2`; interrupt `finish_current_sentence`; overlap `false` |
| TTS playback state | prior prompt playback ended cleanly; vocab-return reply synthesis started after response |
| Mechanical wording | no |
| Overloaded turn | mild, but acceptable for vocabulary explanation plus return |
| Off-route textbook behavior | no; did not reopen module choice after vocab explanation |
| mouthOpen abnormal | not confirmed by human |
| Interrupt abnormal | no; `finish_current_sentence` visible |
| Classification | acceptable P13 vocab return; monitor as rag_plus_llm return-anchor boundary |
| Owner file | none for immediate fix; monitor `redirect_reply_policy.py` / RAG return path if it regresses |
| Priority | monitor |
| Allowed into next fix slice | no immediate fix |

## P4 Initial Classification

| page_uid | issue | classification | owner | priority | next action |
| --- | --- | --- | --- | --- | --- |
| `TB-G5S1U3-P22` | Favourite-food redirect is short and on-route. | acceptable S3 visible reply | none | none | No fix. |
| `TB-G6S1U1-P4` | Off-topic `turn left` still redirects to `museum shop` noun phrase instead of preserving the location question/answer pair. | redirect helper / TeachingMove target-action issue | `redirect_reply_policy.py`, possibly `teaching_move_planner.py` | P1 | Fix only through public question/answer target-action priority; no page_uid/input special case. |
| `TB-G6S2U1-P4` | Learner `How tall are you?` is handled without durable target pollution; reply uses `How tall is it?` and `It's ... metres tall.` | acceptable S3 visible reply | none | none | No fix. |
| `TB-G5S1U3-P31` | Story redirect is short, clear, and uses answer frame. | acceptable story scaffold | none | none | No fix. |
| `TB-G5S2U1-P6` | Phonics redirect is clear; `cl' as in` did not appear. | acceptable phonics scaffold | none | none | No fix. |
| `TB-G6S2U2-P13` | `had a cold` explanation returns to `What did you do last weekend?`, not module choice. | acceptable P13 vocab return; monitor boundary | none immediate | monitor | No immediate fix; keep as regression watch. |

## Summary

Technical browser observation now covers all six target pages. The only concrete P5 candidate from this pass was `TB-G6S1U1-P4`, where the visible redirect could still collapse the route/location dialogue into `museum shop`.

Post-observation P5 L1 update: public location question/answer preservation is merged through PR #13: `https://github.com/rootliuat/PepTutor/pull/13`. It has not yet been browser-reobserved. Human judgement is still needed for spoken TTS quality, mouthOpen naturalness, and whether the overall Mili tone feels like a real teacher.
