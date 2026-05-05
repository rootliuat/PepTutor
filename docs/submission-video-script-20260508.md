# PepTutor 6-8 分钟讲解视频脚本

目标时长：6-8 分钟

## 0:00-0:40 Opening: What PepTutor is

大家好，这是 PepTutor，一个面向小学英语教材的 AI 陪练老师系统。

它不是一个普通聊天机器人。PepTutor 的目标是：让 AI 在指定教材页里，稳定完成一个可观察、可审计、可验证的课堂动作。

学生输入一句话之后，系统不仅要生成老师回复，还要知道当前教材页、当前教学 block、当前英文目标、下一步希望学生读、答、跟读还是回到故事问题。

## 0:40-1:20 Why normal LLM tutoring is unstable

普通 LLM 直接做英语老师时，常见问题是：

- 学生一跑题，模型就离开教材。
- 问句、答句、词汇解释和模块选择容易混在一起。
- 老师回复看起来像课堂话术，但背后没有可审计的教学动作。
- TTS、Live2D、Sidebar 状态如果不可观察，就很难判断问题出在哪里。

PepTutor 解决的不是“让模型更会聊天”，而是“让模型在教材约束内稳定上课”。

## 1:20-2:10 System architecture overview

系统分为四层：

第一层是教材结构化数据，保存教材页、block、目标句、词汇、answer scope、return anchor。

第二层是后端 lesson runtime，它负责 route、TeachingMove、redirect policy、质量修订和 token/context metering。

第三层是前端 `/lesson` 页面，它提供学生输入、老师回复、TTS 播放、Live2D 表现和 Sidebar debug。

第四层是验证体系，包括 backend smoke、TeachingMove audit、classroom quality audit、redirect audit、browser smoke、persona audit、curriculum graph audit 和 Test Budget Guard。

另外，May 8 前新合入了两条离线证据线：RAGFlow curriculum evidence integration 和 agentic curriculum retrieval harness。它们只用于教材证据审阅，不控制课堂 runtime。

## 2:10-2:50 Demo startup path

演示启动命令：

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

启动后打开：

```text
http://127.0.0.1:5173/lesson
```

这里可以看到 lesson 页面。左侧或侧栏里能看到当前页面、route、TeachingMove、TTS 状态、persona 状态等诊断信息。

## 2:50-3:40 Lesson classroom flow

演示一页代表性教材，例如 `TB-G6S1U1-P4`。

这页是问路对话：

```text
Where is the museum shop?
It's near the door.
```

学生输入一个偏离目标的短语，例如 `turn left`。系统不会把目标长期压成裸词 `museum shop`，而是保留问路目标：

```text
Where is the museum shop?
It's near ...
```

这里可以展示 Sidebar：route 是课堂 answer/redirect 路径，TeachingMove 记录 question target、answer frame 和 expected action。

## 3:40-4:30 TeachingMove contract explanation

TeachingMove 是 PepTutor 的关键中间层。

它把老师下一步动作结构化，比如：

- target_role 是 question、answer、phonics 还是 story
- expected_student_action 是 read、answer 还是 repeat
- question_target 是哪一句问题
- answer_target 是哪一句回答
- answer_frame 是什么回答框架

这样做的好处是：LLM 不再自由决定教材路线。它只在受约束的动作里组织表达。

## 4:30-5:10 Mili persona boundary

PepTutor 里的老师叫米粒。

米粒 persona 使用的是短 capsule，不是完整 `soul.md`。它只影响语气和脚手架大小，比如温柔、耐心、短句引导。

米粒不能决定 page、block、route、answer scope 或 progression。兴趣爱好也不会进入每一轮课堂 prompt。

所以我们现在可以诚实地说：persona wiring 是干净的，但“完全像真人老师一样自然”还不是当前交付结论。

## 5:10-5:50 TTS / Live2D / Sidebar observation

前端可以观察：

- TTS synthesis 和 playback
- stop reason 和 normalized stop reason
- interrupt policy
- playback overlap
- Live2D mouthOpen
- route、source、persona、TeachingMove

这些字段让问题可诊断。比如现在可以看到 TTS 是否在播、mouthOpen 数值是否变化、是否出现 playback overlap。

但是 TTS 自然度和嘴型同步自然度，仍然需要人类听看判断，不能只靠 DOM 证据宣称完成。

## 5:50-6:35 Curriculum graph audit

P8.1/P8.2 完成了全结构化教材图谱审计。

覆盖：

- 4 册书
- 30 个单元
- 255 页
- 581 个教学 block

图谱节点包括 Book、Unit、Page、Block、QuestionTarget、AnswerFrame、VocabItem、PhonicsPattern、StoryQuestion、AnswerScope 和 ReturnAnchor。

这不是模型训练，不是 GRPO，也不是 LLM 抽取。它是离线、确定性的结构化教材审计。

它帮助我们知道哪些地方是教材结构缺口，哪些是规则误报，哪些只是低优先级风险信号。

PR #16 增加了 RAGFlow 离线证据管线，用于服务检查、资料上传计划、chunk 导出、清洗、映射和 evidence index。RAGFlow 是外部证据来源，默认关闭，不接管课堂。

PR #17 增加了 agentic curriculum retrieval harness。它默认 provider=none，只生成 review prompt 和证据包；即便未来接 kimi-cli、deepagents 或其他 CLI，也只做离线人工审阅，不让 agent 控制课堂。

## 6:35-7:10 Smoke/audit validation

PepTutor 有多层验证：

- backend 20-page smoke
- TeachingMove audit
- classroom quality audit
- redirect experience audit
- browser smoke
- curriculum graph audit

同时 Test Budget Guard 防止每次目标都反复跑 full smoke。现在 full smoke、browser smoke、deep smoke 都按目标和预算分层执行。

这说明系统不是靠一次 demo 演示，而是靠可复现的测试和审计链路推进。

## 7:10-7:45 Current limitations and honest blocker

当前限制也需要说明清楚：

- 米粒的真人感还没有完全完成。
- TTS 自然度和 mouthOpen 同步还需要人类 AV 评价。
- RAGFlow 已有离线证据集成，但没有接入 live classroom runtime。
- Agentic CLI harness 已有离线 review 工具，但没有接入 live classroom runtime。
- GRPO 没有实现。
- 没有做模型训练。
- P8.3a 只是 answer-scope 数据收紧候选计划，还没有直接改教材数据。
- `app/knowledge/structured` 仍是 canonical curriculum source。

这不是全自动老师的最终形态，而是一个可控、可观察、可审计的教材陪练原型。

## 7:45-8:00 Future plan

下一步会推进三条线：

第一，继续做教材图谱数据收紧，比如 answer scope、phonics inheritance、story role classification。

第二，继续产品化 browser smoke、S4 interrupt、TTS/Live2D 观察。

第三，未来可以探索 RAGFlow-style book parsing、agentic retrieval harness 的人工审阅流程，以及只用于离线抽取的 SFT/DPO/GRPO。

但这些都是 May 8 之后的方向。当前交付的核心价值是：PepTutor 已经把 AI 英语陪练从“不可控聊天”推进到“可验证课堂运行时”。

## 60-Second Demo Flow

```text
1. Run ./scripts/start_lesson_dev.sh
2. Open http://127.0.0.1:5173/lesson
3. Select TB-G6S1U1-P4 or another representative page
4. Enter a student input
5. Show teacher reply
6. Show Sidebar route / TeachingMove / TTS / persona fields
7. Mention TB-G6S1U1-P4 location QA preservation after PR #13
```

## Claims To Avoid

Do not claim:

- fully human-like Mili is complete
- TTS naturalness is certified
- mouthOpen sync is certified
- GRPO is implemented
- RAGFlow controls lesson routing
- agentic CLI controls classroom
- full autonomous teacher is solved

For RAGFlow, the safe wording is: an offline evidence integration exists; it is not connected to live classroom control.

For the agentic harness, the safe wording is: provider=none by default; it prepares prompt/evidence review packages and does not control the classroom.

Safe claims:

- routing and TeachingMove contracts are auditable
- graph audit covers the full structured curriculum
- classroom behavior is observable and testable
- budget guard prevents uncontrolled smoke runs
- the system has a clear path from demo to product hardening
