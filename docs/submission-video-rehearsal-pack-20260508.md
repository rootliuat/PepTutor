# PepTutor Video Rehearsal Pack

Target length: 6-8 minutes

Date: 2026-05-05

## 0:00-0:30 Opening

Screen action:

```text
Show title slide or /lesson page.
```

What to say:

```text
大家好，这是 PepTutor，一个面向小学英语教材的 AI 陪练老师系统。它的目标不是做一个万能聊天机器人，而是让 AI 在指定教材页里稳定完成一个可观察、可审计、可验证的课堂动作。
```

What not to say:

```text
不要说 PepTutor 已经是完整自主 AI 老师。
不要说米粒已经完全像真人。
```

Fallback if demo fails:

```text
Open docs/submission-one-page-scorecard-20260508.md and introduce the architecture summary.
```

## 0:30-1:10 Problem Definition

Screen action:

```text
Show project book section "问题定义" or keep /lesson visible.
```

What to say:

```text
普通大模型直接做小学英语老师时，最大问题是课堂目标不稳定。学生一句跑题输入，模型可能离开教材；问句、答句、词汇解释、模块选择也容易混在一起。PepTutor 解决的是课堂控制问题：当前页是什么、当前 block 是什么、下一步要学生读、答还是跟读，这些都要可审计。
```

What not to say:

```text
不要说普通 LLM 完全不能教学；重点是它不够可控、不可审计。
```

Fallback if demo fails:

```text
Use docs/submission-project-book-final-draft-20260508.md sections 3-4.
```

## 1:10-2:00 Architecture Overview

Screen action:

```text
Show docs/submission-project-book-final-draft-20260508.md section 6 or Sidebar if stack is running.
```

What to say:

```text
系统分四层。第一层是 app/knowledge/structured，它仍是 canonical curriculum source。第二层是 backend/LightRAG 的 lesson runtime 和 TeachingMove。第三层是 frontend/airi 的 /lesson、TTS、Live2D 和 Sidebar。第四层是 smoke、audit 和 Test Budget Guard。课堂控制层是 TeachingMove，不是 RAGFlow，也不是外部 agent。
```

What not to say:

```text
不要说 RAGFlow 或 agentic harness 在 live lesson 里控制路由。
```

Fallback if demo fails:

```text
Show docs/no-runtime-external-agent-boundary-20260508.md.
```

## 2:00-3:00 Classroom Demo Path

Screen action:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Open:

```text
http://127.0.0.1:5173/lesson
```

Show one page:

```text
TB-G6S1U1-P4
```

Optional pages:

```text
TB-G5S2U1-P6
TB-G5S1U3-P31
```

What to say:

```text
这里演示 TB-G6S1U1-P4。它是问路问答页，核心是 Where is the museum shop? 和 It's near ...。PR #13 之后，这个页面不会长期塌缩成裸词 museum shop，而是保留问答目标。右侧 Sidebar 可以看到 route、TeachingMove 和 answer frame。
```

What not to say:

```text
不要临时跑 full smoke。
不要说所有教材页都已经达到最终课堂自然度。
```

Fallback if demo fails:

```text
Use docs/submission-demo-checklist-20260508.md.
Show existing docs and explain recorded targeted validation.
Do not rerun full smoke during recording.
```

## 3:00-3:50 TeachingMove Contract

Screen action:

```text
Show Sidebar TeachingMove fields or project-book section 8.
```

What to say:

```text
TeachingMove 是 PepTutor 的关键中间层。它记录 target_role、expected_student_action、question_target、answer_target、answer_frame。这样系统能区分学生是在读问题、回答问题、练 phonics，还是回到 story question。LLM 不是自由决定教材路线，而是在这个动作契约内组织表达。
```

What not to say:

```text
不要说 TeachingMove 消灭了所有教学问题；它解决的是可控性和可审计性。
```

Fallback if demo fails:

```text
Show docs/submission-project-book-final-draft-20260508.md section 8.
```

## 3:50-4:40 Mili Visible Tone And Boundary

Screen action:

```text
Show teacher reply and persona fields if visible.
```

What to say:

```text
PepTutor 的老师叫米粒。米粒使用短 persona capsule，不使用完整 soul.md。她可以影响语气，比如温柔、耐心、短句引导；但不能决定 page、block、route、answer scope 或 progression。兴趣爱好也不会进入每轮课堂 prompt。
```

What not to say:

```text
不要说米粒已经完全拟人化。
不要说兴趣爱好会参与课堂路线。
```

Fallback if demo fails:

```text
Use docs/submission-project-book-final-draft-20260508.md section 9.
```

## 4:40-5:30 Curriculum Graph Audit

Screen action:

```text
Show docs/curriculum-graph-audit-summary-20260505.md or project-book section 11.
```

What to say:

```text
P8.1 到 P8.3a 完成了全结构化教材图谱审计。覆盖 4 册书、30 个单元、255 页、581 个 block，图谱有 9328 个 nodes 和 22475 条 edges。六个 regression anchor pages 全部存在，6/6。审计发现 988 条 findings，并区分真实结构缺口、规则误报和低优先级风险。
```

What not to say:

```text
不要说这是 LLM 自动抽取。
不要说这是模型训练。
不要说已经自动修改了教材数据。
```

Fallback if demo fails:

```text
Use docs/submission-one-page-scorecard-20260508.md key numbers.
```

## 5:30-6:15 RAGFlow Offline Evidence Pipeline

Screen action:

```text
Show docs/ragflow-service-integration-plan-20260505.md or docs/no-runtime-external-agent-boundary-20260508.md.
```

What to say:

```text
PR #16 加的是 RAGFlow 离线证据管线。它可以做服务检查、上传计划、chunk 导出、清洗、映射和 evidence index。它默认关闭，不是课堂启动依赖，不替代 app/knowledge/structured，也不控制 lesson route 或 TeachingMove。
```

What not to say:

```text
不要说 RAGFlow 已经驱动课堂检索。
不要说 RAGFlow 控制 lesson routing。
```

Fallback if demo fails:

```text
RAGFlow 不需要现场运行。直接展示文档即可，因为它本来就是 offline evidence pipeline。
```

## 6:15-6:50 Agentic Offline Review Harness

Screen action:

```text
Show docs/agentic-cli-harness-config-20260505.md or docs/curriculum-evidence-review-queue-20260505.md.
```

What to say:

```text
PR #17 增加的是 agentic curriculum retrieval harness。默认 provider=none，只生成 prompt 和 evidence review package。未来可以接 kimi、deepagents、bub 或 generic CLI 作为慢路径审阅工具，但 agent 不控制课堂，也不能改结构化教材。
```

What not to say:

```text
不要说外部 agent 在教学生。
不要说 agentic CLI 已经接入 runtime。
```

Fallback if demo fails:

```text
Agentic harness 不需要现场运行。展示 review queue 文档即可。
```

## 6:50-7:30 Validation And Budget Guard

Screen action:

```text
Show docs/submission-readiness-summary-20260508.md or docs/test-budget-guard.md.
```

What to say:

```text
PepTutor 有 backend smoke、browser smoke、TeachingMove audit、classroom quality audit、redirect audit、curriculum graph audit 和 Test Budget Guard。Test Budget Guard 把验证分成 L1、L2、L3，防止每个目标反复跑 full smoke。PR #15、#16、#17 都用 targeted tests 验证；P8.6/P8.7 是 docs-only，没有跑 full、browser 或 deep smoke。
```

What not to say:

```text
不要说 May 8 前每个文档改动都重新跑了 full smoke。
```

Fallback if demo fails:

```text
Use readiness summary validation section.
```

## 7:30-8:00 Honest Limitations And Future Work

Screen action:

```text
Show project-book limitations section.
```

What to say:

```text
当前限制也很明确：米粒不是完全真人化；TTS 自然度和 mouthOpen 同步还需要人类 AV 判断；RAGFlow 和 agentic harness 是离线证据工具；GRPO 没有实现；没有模型训练；PepTutor 也不声称解决了完整 autonomous teacher。下一步是教材数据收紧、S4/TTS/Live2D 产品化，以及离线证据能力加强。
```

What not to say:

```text
不要过度承诺。
不要把未来方向说成已经完成。
```

Fallback if demo fails:

```text
Close with docs/submission-one-page-scorecard-20260508.md known limitations.
```
