# PepTutor 项目书终稿草案

面向提交日期：2026-05-08

## 1. 项目名称

PepTutor：面向小学英语教材的可审计 AI 陪练老师系统。

## 2. 一句话简介

PepTutor 将教材页、教学动作、课堂回复、语音播放、Live2D 表现和质量审计串成一条可观察、可验证的课堂链路，让 AI 不只是聊天，而是在明确教材范围内完成稳定的小学英语陪练动作。

## 3. 项目背景

大模型已经具备较强的语言生成能力，但直接把大模型作为小学英语老师使用，会遇到一个根本问题：模型能说话，不代表它能稳定上课。

在真实教材陪练中，老师需要持续知道当前教材页、当前教学目标、学生刚才说了什么、下一步应该让学生读、回答、跟读，还是回到故事问题。普通 AI 对话系统往往只关注生成一句自然回复，很难保证它没有离开教材路线，也很难在出现问题时定位原因。

PepTutor 的设计起点是：把小学英语陪练变成一个可控运行时，而不是一次不可复现的聊天。

## 4. 问题定义

本项目重点解决五类问题。

第一，教学目标漂移。学生说出跑题词语后，AI 容易离开当前教材目标，或者把完整句型压缩成裸词。

第二，问答边界混乱。词汇解释、模块选择、问句回答、故事阅读、phonics 跟读如果没有结构化边界，容易在一轮回复里互相污染。

第三，课堂动作不可审计。只看老师最终回复，无法判断系统希望学生下一步做什么，也无法稳定复盘错误。

第四，语音和形象表现不可诊断。TTS 播放、打断、Live2D mouthOpen、Sidebar 状态如果不可观察，就难以判断体验问题来自后端、前端还是音视频层。

第五，验证成本失控。AI 课堂 smoke 测试会消耗 token 和时间，如果没有预算保护，很容易反复跑完整矩阵而没有新增证据。

## 5. 目标用户与使用场景

目标用户包括小学英语学习者、希望进行课后陪练的家庭、需要辅助练习材料的教师，以及需要评估 AI 教学系统可控性的评审者。

典型使用场景是：学生打开 `/lesson` 页面，选择当前教材页，输入或说出一句话。PepTutor 根据教材结构、当前 block、学生输入和教学动作契约，生成米粒老师的一轮回复。回复通常包含短中文脚手架、明确英文目标，以及一个下一步动作。与此同时，Sidebar 显示 route、TeachingMove、persona、TTS 等诊断字段，帮助开发者和评审者看到系统为什么这样上课。

## 6. 系统总体架构

PepTutor 由四层组成。

教材结构层以 `app/knowledge/structured` 为 canonical curriculum source，保存教材页、单元、block、问题目标、回答框架、词汇、phonics、answer scope 和 return anchor 等结构化信息。

后端课堂运行层位于 `backend/LightRAG`。它负责 lesson runtime、TeachingMove 生成、redirect policy、LLM token/context metering、质量修订和各类审计脚本。

前端交互层位于 `frontend/airi`。它提供 `/lesson` 页面、学生输入、老师回复、TTS 播放、Live2D 表现和 Sidebar 可观测字段。

验证与审计层包括 backend smoke、browser smoke、TeachingMove audit、classroom quality audit、redirect experience audit、persona consistency audit、curriculum graph audit 和 Test Budget Guard。

系统原则是：教材路线由结构化 curriculum、lesson runtime 和 TeachingMove 控制；LLM 只在受约束范围内组织可见表达；外部证据工具不控制课堂 runtime。

## 7. 核心功能

PepTutor 当前已具备以下核心能力。

它能读取结构化教材，围绕指定教材页运行课堂回合。学生输入后，系统会判断当前 route、目标 block、教学动作和回复策略。

它能生成结构化 TeachingMove，把“老师下一步要做什么”记录为可审计字段，而不是只保留自然语言回复。

它能在 redirect 场景中保留问答目标。例如问路页 `TB-G6S1U1-P4` 中，系统能够保留 `Where is the museum shop?` 和 `It's near ...`，避免长期塌缩成裸词 `museum shop`。

它能把米粒 persona 以短 capsule 进入受控 prompt 路径，让语气更温柔、耐心，但不让人格决定教材路线。

它能记录 TTS 播放状态、stop reason、normalized stop reason、Live2D mouthOpen、Sidebar debug 等可观测字段。

它能通过 smoke 和 audit 验证课堂链路，并通过 Test Budget Guard 限制高成本测试。

## 8. 教学动作契约 TeachingMove

TeachingMove 是 PepTutor 的关键中间层。它把课堂回复背后的教学意图结构化，降低 LLM 自由发挥造成的风险。

典型 TeachingMove action contract 包含：

- `target_role`：question、answer、phrase、phonics、story 等目标类型
- `expected_student_action`：read、answer、repeat、choose、role_play 等下一步学生动作
- `question_target`：当前问题目标
- `answer_target`：当前回答句目标
- `answer_frame`：当前回答框架
- `action_source`：动作来源，例如 block core pattern、phonics context、story context

这样系统可以区分：学生是在读问题、回答问题、跟读答句、练 phonics，还是回到故事问题。TeachingMove 让课堂动作可以被测试、被审计，也让 redirect policy 能优先使用经过验证的目标字段。

## 9. 米粒人格与课堂表现边界

PepTutor 的老师角色叫米粒。米粒 persona 的运行时来源是短 persona capsule，而不是完整 `soul.md`。

米粒可以影响语气和脚手架大小：温柔、耐心、短句引导，先接住学生表达，再给短中文提示，最后只给一个动作。

米粒不能决定 page、block、route、answer scope、state patch 或 progression。米粒的兴趣爱好不进入每轮课堂 prompt，完整 `soul.md` 也不会进入 runtime prompt。

因此，当前项目可以声称 persona wiring 是干净、受控的；但不能声称米粒已经完全像真人老师一样自然。

## 10. TTS / Live2D / Sidebar 可观测性

前端 `/lesson` 页面将课堂运行状态暴露给 Sidebar 和浏览器 smoke，包括 TTS synthesis/playback 状态、`ttsPlaybackStopReason`、normalized stop reason、interrupt policy、playback overlap、Live2D mouthOpen、route、source、TeachingMove 和 persona debug。

这些字段让问题可以被定位。例如，如果 TTS 正在播放但 Live2D mouthOpen 没有变化，就可以判断问题可能位于前端音视频表现层，而不是后端课堂 route。

需要诚实说明的是：当前技术观察能证明字段可见、状态可诊断；但 TTS 自然度和 mouthOpen 嘴型同步自然度仍需要真实人类听看判断，不能仅凭 DOM 或日志宣称完全认证。

## 11. 教材结构化与 Curriculum Graph

P8.1/P8.2/P8.3a 完成了 full structured curriculum graph audit、findings triage 和 review-only candidate planner。

当前结构化图谱覆盖：

- 4 册书
- 30 个单元
- 255 页
- 581 个教学 block
- 9328 个节点
- 22475 条边
- 六个 regression anchor pages 全部存在：6/6

图谱节点包括 Book、Unit、Page、Block、QuestionTarget、AnswerFrame、VocabItem、PhonicsPattern、StoryQuestion、AnswerScope、ReturnAnchor 和 SourceFile 等。

图谱审计共发现 988 条 findings，并被归类为：真实教材结构缺口 695 条，建模/规则误报类 60 条，低优先级风险信号 233 条。

这不是模型训练，不是 GRPO，也不是 LLM 抽取；它是离线、确定性的结构化教材审计。

## 12. RAGFlow 离线证据链

PR #16 增加了 RAGFlow curriculum evidence integration。它的定位是外部离线证据链，而不是 live lesson runtime 的一部分。

RAGFlow 相关脚本支持服务检查、上传计划、chunk 导出、chunk 清洗、chunk 到 PepTutor evidence schema 的映射，以及 curriculum evidence index 构建。

RAGFlow 默认关闭，不是启动项目的必要依赖。它不替代 `app/knowledge/structured`，不控制 lesson route，不决定 page/block，不写 TeachingMove，不进入课堂 prompt，也不改变学生可见回复。

RAGFlow 的价值在于：为后续人工审核 answer scope、phonics inheritance、教材结构缺口提供外部证据来源。

## 13. Agentic CLI 离线复核链路

PR #17 增加了 agentic curriculum retrieval harness。它是离线复核工具，默认 provider 为 `none`。

当 provider 为 `none` 时，系统只生成 prompt 和 evidence review package，不调用外部 agent。未来如接入 kimi、deepagents、bub 或 generic CLI，也只能作为慢路径人工审阅工具。

Agentic harness 不允许编辑 `app/knowledge/structured`，不允许编辑 runtime code，不接入 lesson runtime，不控制 TeachingMove，不控制 redirect policy，也不决定课堂回复。

它的作用是把结构化图谱、RAGFlow 证据和候选问题整理成更容易人工复核的材料。

## 14. Smoke / Audit / Test Budget Guard

PepTutor 的验证体系包括：

- backend 20-page lesson smoke
- TeachingMove audit
- classroom quality audit
- redirect experience audit
- browser smoke
- persona consistency audit
- LLM token/context metering
- curriculum graph audit
- Test Budget Guard

Test Budget Guard 将验证分为 L1、L2、L3：L1 是相关单测和 lint，L2 是目标页小验证，L3 是最多一次完整 20-page smoke。browser/deep smoke 只在前端、S4、TTS、Live2D 相关目标中使用。

这使项目能够在保持质量闭环的同时避免 token 和时间成本失控。

## 15. 已完成成果

截至 2026-05-05：

- P0 startup complete
- P1 browser smoke complete
- P2 manual test prep complete
- P3 technical observation complete，但 true human AV judgement still pending
- P4 technical classification complete
- P5 engineering fix complete with PR #13
- PR #15 merged：full curriculum graph audit and candidate planner
- PR #16 merged：offline RAGFlow curriculum evidence integration
- PR #17 merged：offline agentic curriculum retrieval harness

最新 docs-only delivery baseline 为：

```text
f779f4dd812b5ce52967ae031ff62778019a3b3a
```

PR #17 merge commit 为：

```text
c565b0321fa9848bb256aba490ad871bf74de5f9
```

## 16. 技术亮点

PepTutor 的技术亮点不在于单次回复，而在于整个课堂链路的可控性。

第一，TeachingMove 把课堂动作结构化，使 question、answer、story、phonics 等路径可审计。

第二，redirect policy 使用 validated action fields，降低 target 被学生输入、wrapper 或 LLM 表面话术污染的风险。

第三，米粒 persona 是受边界约束的 capsule，不让人格影响教材路线。

第四，TTS、Live2D、Sidebar 状态可观测，使前后端问题可以定位。

第五，curriculum graph audit 覆盖全部结构化教材，而不是只覆盖 demo 页。

第六，RAGFlow 和 agentic harness 被设计为离线证据链，不把外部工具引入课堂控制路径。

第七，Test Budget Guard 防止反复运行高成本 smoke。

## 17. 对比普通 AI 对话系统的优势

普通 AI 对话系统通常以生成自然回答为中心。PepTutor 以课堂运行链路为中心。

PepTutor 知道当前教材页、当前 block、当前目标句、当前 answer frame 和下一步学生动作。它能把老师回复背后的教学动作暴露出来，也能通过 audit 判断回复是否偏离目标。

这让 PepTutor 更接近“可审计的 AI 教学运行时”，而不是一个普通聊天机器人。

## 18. 当前限制

当前项目仍有明确限制。

米粒 visible personality 不是最终完成状态。她已经有受控 persona capsule 和部分可见语气边界，但还不能声称完全拟人化。

TTS 自然度和 Live2D mouthOpen 同步仍需要真实人类 AV 评价。

P8.3a 是 review-only candidate plan，尚未直接改结构化教材数据。

RAGFlow 和 agentic harness 都是离线证据链，不控制 classroom runtime。

GRPO 已延期，没有实现。模型训练没有实现。LLM extraction 没有实现。PepTutor 也不声称已经解决完整 autonomous teacher。

## 19. 未来计划

May 8 之后，可以沿三条线推进。

第一，教材数据收紧：人工审核 answer scope、phonics page-level inheritance、story/question 建模误报，逐步修正结构化教材。

第二，产品体验硬化：继续推进 S4 backend natural interrupt trigger、browser smoke productization、TTS/Live2D 人类 AV 观察。

第三，离线证据能力：继续探索 RAGFlow-style book parsing、chapter-level plain text hierarchy、stronger retrieval route、agentic review provider，以及仅用于离线抽取评估的 SFT/DPO/GRPO。

这些未来方向不属于 May 8 当前交付，不应在演示中声称已经完成。

## 20. 演示流程

演示启动：

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

打开：

```text
http://127.0.0.1:5173/lesson
```

建议演示页面：

- `TB-G6S1U1-P4`：展示 PR #13 后 `Where is the museum shop?` 和 `It's near ...` 的问答目标保留。
- `TB-G5S2U1-P6`：展示 phonics scaffold 和 `cl' as in` 不泄漏。
- `TB-G5S1U3-P31`：展示 story scaffold。

演示时展示 Sidebar 中的 route、TeachingMove、persona、TTS 和 stop reason 等字段。

如果现场启动失败，不要临时跑 full smoke。直接使用 `docs/submission-demo-checklist-20260508.md`、图谱审计文档和已记录的 targeted validation 说明系统边界与完成情况。
