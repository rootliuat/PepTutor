# PepTutor S3 Mili / TTS Manual Test Checklist

Purpose: verify the May 4 S3 visible classroom tone slice in a real classroom session. This checklist is for human observation, not an automated acceptance gate.

Global expectations:

- Teacher reply first acknowledges the learner, then gives a short Chinese scaffold, then shows the English target, then gives one next action.
- Mili sounds warm and teacher-like, but does not sell personality, add hobbies, or leave the textbook route.
- Sidebar exposes `teaching_action`, `target_role`, `expected_student_action`, `speech_style`, `speech_style_tag`, `interrupt_policy`, TTS synthesis/playback state, and persona capsule status.
- TTS plays the final teacher reply. `mouthOpen` should follow playback and should not keep moving after playback stops.
- Interrupt behavior should match the visible `interrupt_policy`; do not mark Live2D expression gaps as classroom content failures.

## Startup And Test Entry

Start the local lesson stack:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Open the browser entry:

```text
http://127.0.0.1:5173/lesson
```

Before recording page observations, confirm:

- The backend reports `/lesson/catalog` ready.
- The frontend reports Vite ready.
- The lesson page loads without a blank screen.
- The Sidebar is visible or can be opened.
- TTS provider state is visible in the Sidebar.

For each page below, use the page selector or route controls to reach the listed `page_uid`, then enter the learner inputs in order. Do not mark browser infrastructure failures as classroom behavior failures; record them separately as browser infra issues.

## TB-G5S1U3-P22

Focus: favourite food question scaffold.

Inputs:

- `第一块`
- `water`
- `Yesterday I played football.`
- `I like sandwiches.`

Expected teacher behavior:

- Acknowledges the learner phrase without generic praise.
- Keeps the target around `What's your favourite food?`.
- Gives the short scaffold `你最喜欢的食物是什么？`.
- Offers a compact answer frame such as `My favourite food is ...`.
- Ends with one action, such as asking the learner to answer with one food.

Expected Sidebar / TTS state:

- `target_role`: `question`
- `expected_student_action`: `answer`
- `speech_style_tag`: `short_scaffold` or equivalent short scaffold state
- TTS synthesis and playback states move from pending/playing to ended without overlap.

Observe:

- 是否像真人老师
- 是否过载
- 是否机械
- 是否跑教材
- TTS 是否能播
- 打断是否正常
- mouthOpen 是否乱动

## TB-G6S1U1-P4

Focus: museum shop location question.

Inputs:

- `第一块`
- `turn left`
- `Where is the museum shop?`
- `I want to play basketball.`

Expected teacher behavior:

- Does not collapse the lesson target into only `museum shop`.
- Keeps the classroom target around `Where is the museum shop?` and the answer frame `It's near ...`.
- Avoids visible wrappers such as `跟着老师读` as the final target.
- Does not praise unrelated input with empty praise.

Expected Sidebar / TTS state:

- `target_role`: `question` or `answer`, depending on the current turn
- `expected_student_action`: `answer` or `repeat`
- `speech_style_tag`: `short_scaffold`, `gentle_redirect`, or `calm_correction`
- TTS playback stop reason remains clear if interrupted.

Observe:

- 是否像真人老师
- 是否过载
- 是否机械
- 是否跑教材
- TTS 是否能播
- 打断是否正常
- mouthOpen 是否乱动

## TB-G6S2U1-P4

Focus: height dialogue and object-height answer frame.

Inputs:

- `第一块`
- `How tall are you?`
- `I'm 1.58 metres.`
- `water`

Expected teacher behavior:

- Keeps the textbook question as `How tall is it?`.
- Does not let learner input `How tall are you?` become the durable target.
- Uses an answer frame such as `It's ... metres tall.` when the learner needs to answer.
- Does not show malformed punctuation like `I'm 1.6 metres tall?`.

Expected Sidebar / TTS state:

- `target_role`: `question`
- `expected_student_action`: `answer`
- `speech_style_tag`: `short_scaffold`
- TTS plays the answer-frame reply without overlap.

Observe:

- 是否像真人老师
- 是否过载
- 是否机械
- 是否跑教材
- TTS 是否能播
- 打断是否正常
- mouthOpen 是否乱动

## TB-G5S1U3-P31

Focus: story answer scaffold.

Inputs:

- `第一块`
- `Zip`
- `water`
- `I can read the story.`

Expected teacher behavior:

- Acknowledges story-related input briefly.
- Keeps the story question clear: `What would Zoom like to eat?`.
- Uses the frame `Zoom would like ...`.
- Does not combine too many moves: no long story explanation plus model answer plus extra drill in one turn.

Expected Sidebar / TTS state:

- `target_role`: `story`
- `expected_student_action`: `answer`
- `speech_style_tag`: `story_prompt`
- TTS should finish cleanly; if interrupted, stop reason should be visible.

Observe:

- 是否像真人老师
- 是否过载
- 是否机械
- 是否跑教材
- TTS 是否能播
- 打断是否正常
- mouthOpen 是否乱动

## TB-G5S2U1-P6

Focus: phonics scaffold for `cl` / `clean`.

Inputs:

- `第一块`
- `water`
- `I want to play basketball.`
- `clean`

Expected teacher behavior:

- Uses a phonics target such as `clean`.
- Does not show `cl' as in`.
- Explains the phonics action briefly, for example that the `cl` sound is practiced in `clean`.
- Ends with one repeat action.

Expected Sidebar / TTS state:

- `target_role`: `phonics`
- `expected_student_action`: `repeat`
- `speech_style_tag`: `phonics_repeat`
- TTS should read the clean phonics target without garbled fragments.

Observe:

- 是否像真人老师
- 是否过载
- 是否机械
- 是否跑教材
- TTS 是否能播
- 打断是否正常
- mouthOpen 是否乱动

## TB-G6S2U2-P13

Focus: P13 vocab return and answer-scope boundary regression.

Inputs:

- `第一块`
- `What does had a cold mean?`
- `I stayed at home.`
- `我想学第二块`

Expected teacher behavior:

- Explains vocabulary briefly, then returns to the current task target rather than reopening module choice unnecessarily.
- Does not change P13 answer scope data.
- Does not regress into `你想先学哪一块` after a vocabulary return unless the learner explicitly asks to choose a block.

Expected Sidebar / TTS state:

- `target_role` and `expected_student_action` should match the current task, not a stale module choice.
- `speech_style_tag` should remain a classroom action style, not a persona-interest or idle-chat style.
- TTS state should be visible for synthesis and playback.

Observe:

- 是否像真人老师
- 是否过载
- 是否机械
- 是否跑教材
- TTS 是否能播
- 打断是否正常
- mouthOpen 是否乱动

## Result Notes

For each page, record:

- Passed / needs review
- The exact learner input that triggered a concern
- The teacher reply excerpt
- Sidebar values for teaching action and TTS state
- Whether the issue is classroom content, target/action contract, TTS playback, interrupt handling, or Live2D capability gap
