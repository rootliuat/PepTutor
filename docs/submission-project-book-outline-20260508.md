# PepTutor 项目书框架

面向提交日期：2026-05-08

## 1. 项目名称与一句话简介

项目名称：PepTutor

一句话简介：PepTutor 是一个面向小学英语教材的 AI 陪练老师系统，它把教材页、教学动作、课堂回复、语音播放、Live2D 表现和质量审计串成一条可观察、可验证的课堂链路。

## 2. 项目背景与问题定义

普通大模型可以聊天，但直接拿来做小学英语陪练会出现几个问题：

- 教学目标容易漂移：学生一句跑题输入可能让模型离开当前教材页。
- 问答边界不稳定：词汇解释、模块选择、故事阅读、问答练习容易混在一起。
- 课堂动作不可审计：系统说了什么容易看到，但为什么这样说、下一步希望学生做什么不清楚。
- 语音和形象表现缺少诊断：TTS、Live2D、Sidebar 状态如果不可观察，很难判断是真问题还是显示问题。
- 测试成本容易失控：一轮目标反复跑 full smoke 会消耗大量 token 和时间。

PepTutor 的问题定义不是“做一个万能聊天老师”，而是“让 AI 在指定教材页内稳定完成一个可验证的小学英语课堂动作”。

## 3. 目标用户与使用场景

目标用户：

- 小学英语学习者
- 家长或教师，用于课后陪练和课堂辅助
- 项目评审者，用于观察 AI 教学系统是否可控、可复现、可验证

使用场景：

- 学生打开 `/lesson`，选择教材页。
- 学生输入或说出一句话。
- 系统判断当前页、当前 block、学生意图和教学动作。
- 米粒老师给出短中文脚手架、英文目标和一个下一步动作。
- Sidebar 显示 route、TeachingMove、TTS、persona、interrupt 等诊断字段。

## 4. 系统总体架构

系统由四层组成：

1. 教材结构层：`app/knowledge/structured` 保存教材页、block、目标句、词汇、answer scope 等结构化数据。
2. 后端课堂运行层：`backend/LightRAG` 负责 lesson runtime、TeachingMove、redirect policy、LLM metering、audit 脚本。
3. 前端交互层：`frontend/airi` 提供 `/lesson` 页面、Sidebar、TTS/Live2D 状态展示、浏览器 smoke。
4. 验证与审计层：smoke、TeachingMove audit、classroom quality audit、redirect audit、browser smoke、test budget guard、curriculum graph audit。

核心设计原则是：教材路线由结构化 runtime 和 TeachingMove 控制，LLM 只负责在受限范围内组织可见表达。

## 5. 核心功能

- 教材页选择和课堂回合运行。
- 学生输入后识别 route 和教学动作。
- TeachingMove action contract 记录 `target_role`、`expected_student_action`、`question_target`、`answer_target`、`answer_frame`。
- redirect reply policy 使用经过验证的 action fields，避免污染 target。
- 米粒 persona capsule 进入受控 prompt 路径，但不控制 page/block/route。
- TTS 播放、stop reason、Live2D mouthOpen、Sidebar debug 可观察。
- browser smoke 和 backend smoke 验证课堂链路。
- test budget guard 防止反复跑高成本 smoke。

## 6. 教材结构化与知识图谱

P8.1/P8.2 已完成 full structured curriculum graph audit：

- 覆盖 4 册书
- 30 个单元
- 255 页
- 581 个教学 block
- 9328 个 graph nodes
- 22475 条 graph edges
- 六个 regression anchor pages 全部存在：6/6

图谱节点包括 Book、Unit、Page、Block、TeachingTarget、QuestionTarget、AnswerTarget、AnswerFrame、VocabItem、PhonicsPattern、StoryQuestion、AnswerScope、ReturnAnchor、SourceFile 等。

图谱审计产出 988 条 findings，并在 P8.2 中分成：

- 真实教材结构缺口：695
- 建模/规则误报类：60
- 低优先级风险信号：233

这部分没有引入模型训练、GRPO、LLM 抽取或 runtime 连接，是离线、确定性的教材结构分析。

## 7. TeachingMove 教学动作契约

TeachingMove 是 PepTutor 的课堂动作中间层。它把“老师下一步到底要学生做什么”结构化，而不是把所有决定交给 LLM。

典型字段：

- `target_role`: question / answer / phrase / phonics / story
- `expected_student_action`: read / answer / repeat / choose / role_play
- `question_target`
- `answer_target`
- `answer_frame`
- `action_source`

这让系统可以区分：

- 学生要读问题
- 学生要回答问题
- 学生要跟读回答句
- 学生要回到故事问题
- 学生要练 phonics 例词

PR #13 之后，`TB-G6S1U1-P4` 的问路页能保留 `Where is the museum shop?` 和 `It's near ...`，不再长期塌缩成裸词 `museum shop`。

## 8. 米粒人格与课堂表现边界

米粒的人格来源是短 persona capsule，不是完整 `soul.md`。

当前边界：

- 米粒可以影响语气：温柔、耐心、短句引导。
- 米粒可以影响脚手架大小：先接住学生表达，再给短中文提示。
- 米粒不能决定教材路线。
- 米粒不能改变 page/block/route。
- 米粒不能改变 answer scope。
- 米粒兴趣爱好不进入每轮课堂 prompt。
- 完整 `soul.md` 不进入 runtime prompt。

这意味着当前项目已经完成 persona wiring，但还没有宣称“完全拟人化老师体验”完成。

## 9. TTS / Live2D / Sidebar 可观测性

前端 `/lesson` 页面提供可观察字段：

- TTS synthesis/playback 状态
- `ttsPlaybackStopReason`
- normalized stop reason
- interrupt policy
- playback overlap
- Live2D mouthOpen 状态
- route / source / TeachingMove / persona debug

P3 技术观察已经确认 DOM/Sidebar 能看到 TTS 和 mouthOpen 状态，但真正的语音自然度、嘴型同步自然度仍需要人类听看判断。

## 10. Smoke / Audit / Test Budget Guard 验证体系

当前验证体系包含：

- backend 20-page lesson smoke
- TeachingMove audit
- classroom quality audit
- redirect experience audit
- browser smoke
- persona consistency audit
- LLM token/context metering
- curriculum graph audit
- Test Budget Guard

Test Budget Guard 将验证分层：

- L1：相关单测 + lint
- L2：目标页小验证
- L3：最多一次完整 20-page smoke
- browser/deep smoke 仅在前端、S4、TTS、Live2D 相关目标中使用

这解决了早期 `/goal` 反复跑 full smoke 造成 token 和时间消耗失控的问题。

## 11. 当前完成情况

截至 2026-05-05：

- P0 startup complete
- P1 browser smoke complete
- P2 manual test prep complete
- P3 technical observation complete，但 true human AV judgement still pending
- P4 technical classification complete
- P5 engineering fix complete with PR #13
- P8.1/P8.2 curriculum graph audit and triage complete with PR #15

PR #15 已合并，图谱审计和候选计划进入 main。

## 12. 关键技术成果

- 教材页和 block 的结构化运行链路。
- TeachingMove action contract，降低 LLM 自由发挥风险。
- redirect policy 对 question/answer/story/phonics 等场景使用受验证字段。
- 米粒 persona capsule 受控注入。
- TTS/Live2D/Sidebar 可观察性。
- browser smoke 报告区分 real backend passed 和 mock suite skipped。
- LLM token/context metering 和 prompt 成本归因。
- full structured curriculum graph audit。
- Test Budget Guard 防止高成本验证失控。

## 13. 对比普通 AI 对话系统的优势

普通 AI 对话系统的重点是生成回答。PepTutor 的重点是课堂链路：

- 它知道当前教材页和 block。
- 它知道当前教学动作。
- 它能记录 answer frame 和 return anchor。
- 它能审计老师回复是否偏离目标。
- 它能看到 TTS/Live2D/Sidebar 状态。
- 它有 budget guard，避免测试成本不可控。

因此 PepTutor 更接近“可审计的 AI 教学运行时”，不是普通聊天机器人。

## 14. 当前限制

- 米粒的 visible personality 还不是最终体验，只是完成了受控人格接入和部分可见语气切片。
- TTS 自然度和 mouthOpen 同步还没有人类 AV 认证。
- P8.3a 只完成 answer-scope 候选计划，没有直接改教材数据。
- RAGFlow 没有集成。
- GRPO 没有实现。
- 没有引入模型训练。
- full autonomous teacher 还没有解决。
- 40-44 页扩展矩阵尚未进行。

## 15. 未来工作

May 8 之后可以推进：

- RAGFlow-style book parsing
- chapter-level plain-text hierarchy
- stronger embedding/retrieval route as slow path
- agentic retrieval harness，例如 deepagent / kimi-cli-like 工具
- curriculum graph reward/eval
- P8.3a answer-scope source review
- P8.3b phonics graph inheritance
- possible future SFT/DPO/GRPO for offline extraction only
- S4 backend natural interrupt trigger
- browser smoke productization

这些是未来方向，不属于 May 8 交付。

## 16. 5 月 8 日演示路径

建议演示路径：

1. 启动项目：

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

2. 打开：

```text
http://127.0.0.1:5173/lesson
```

3. 展示课堂页：

- `TB-G6S1U1-P4`：问路 Q/A，展示 `Where is the museum shop?` 和 `It's near ...`
- `TB-G5S2U1-P6`：phonics，展示 `clean` 例词和 `cl' as in` 不泄漏
- `TB-G5S1U3-P31`：story scaffold

4. 输入学生句子，观察：

- teacher reply
- Sidebar route/action
- TTS status
- persona debug
- stop reason / overlap

5. 展示图谱文档：

- `docs/curriculum-graph-schema-v1.md`
- `docs/curriculum-graph-audit-summary-20260505.md`
- `docs/curriculum-graph-findings-triage-20260505.md`
- `docs/curriculum-data-tightening-candidates-20260505.md`

6. 明确说明：

当前交付证明的是“可控、可观察、可审计的教材陪练系统”，不是已经完成完全拟人化、完全自主化的 AI 老师。
