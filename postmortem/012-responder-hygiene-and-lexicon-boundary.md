# 012 Responder Hygiene And Lexicon Boundary

## 背景

Page Overview fallback 落地后，真实浏览器 smoke 暴露了三个不是同一层的问题：

- 普通 responder 会在 page entry / navigation 里输出 emoji 和泛泛夸奖。
- Teacher Turn Policy 在词义插问里有时会把当前 block 写到同页别处，或者把 `awaiting_answer` 关掉。
- P26 已经变成多板块入口，旧 smoke 直接问 `snow`，没有先进入第一块，测试步骤和新课堂入口契约不一致。

## 做法

### 1. Responder 表达卫生

`LessonResponder` 的 prompt 增加表达边界：

- 文本里不输出 emoji，AIRI 前端负责表情和动作。
- 模块选择或部分输入只做具体回应，不做泛泛庆祝。
- 夸奖必须贴着学生具体说出的内容或策略。

同时加了通用 emoji 清理。非流式回复在 normalize 阶段清理；流式回复在每个 chunk 发给前端之前清理，保证浏览器不会先看到原始 emoji。

这里没有加页面预设、pizza 模板、场景词表，也没有把课堂决策交给禁词列表。它只处理最终文本外观。

### 2. 词义插问状态护栏

词义问题如 `What does stayed at home mean?` 是短支线，不是模块切换请求。

因此 answer policy 仍然负责生成老师回复，但程序写状态时加边界：

- `currentblockuid` 保持当前 block。
- `awaitinganswer` 保持 `true`。
- 如果 LLM 没给下一轮问题，沿用原来的 `last_teacher_question`。

这属于“程序校验/写状态”，不是“程序替 LLM 判断该怎么教”。LLM 仍然决定怎么解释词义、怎么接回课堂。

### 3. P26 smoke 步骤更新

P26 现在有多板块入口。浏览器 smoke 先选择 `第一块`，再问 `What does snow mean?`。

这个修改不是绕过产品逻辑，而是让验收步骤符合新入口：

1. 进入页面。
2. 看总览。
3. 选择板块。
4. 在该板块内问词义。

## 结果

- P26 `snow` 插问：留在 `TB-G5S1U3-P26-D1`，回复包含 `snow / 雪`，继续回到 `cow` 发音任务。
- G6 P13 `stayed at home` / `had a cold` 插问：留在 `TB-G6S2U2-P13-D2`，`awaiting_answer=true`，不会被写回 D1。
- Streaming responder 的 `done.teacher_response` 继续等于前端收到的 chunk 拼接文本，同时 chunk 已不含 emoji。

## 还剩的问题

普通 responder 偶尔仍会有“说对了 / 很准”这类轻微泛夸。现在只用 prompt 约束，不做词表替换。后续如果要继续收敛，优先做 responder 自审改写，而不是增加禁词或固定话术。
