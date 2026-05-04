# Lesson Response Source Audit Notes

Date: 2026-04-28

## 背景

前端侧边栏之前会把回复路径显示成“规则兜底”或靠 `live_prompts`、`retrieval_mode` 猜测来源。后端日志里其实已经有 `Lesson teacher response audit`，但这个信息没有进入 `/lesson/turn` 的 `debug_signals`。

这会造成一个很实际的问题：真实 LLM 跑了，前端却像是规则回复。之后每次验收看到“规则兜底”，都会误判链路，又回头查 hashingkv、fallback、provider 配置。

## 这次怎么修

这次只补可观测性，不改课堂策略、不改 prompt、不加模板、不加预设、不加标签。

做法：

- `LessonResponder` 增加 `LessonResponderTurnResult`，在返回文本时同时返回来源审计。
- `LessonRuntime._respond_teacher_turn()` 返回 `text + audit`，调用方在构造 `debug_signals` 时带上 `response_audit`。
- `response_audit` 覆盖四种来源：
  - `policy`: answer turn 由 Teacher Turn Policy 直接决策并生成。
  - `llm`: responder LLM 成功生成。
  - `fallback`: LLM 调了，但输出被拒绝或异常后用了安全兜底。
  - `deterministic`: 没有 responder，本地程序逻辑直接出文本。
- 前端优先读 `debug_signals.response_audit`，不再把后端课堂回复误判成规则兜底。

## 踩到的坑

### 1. 原函数只返回字符串

`_respond_teacher_turn()` 原来只返回 `str`。日志里有审计，但 `LessonTurnResult` 拿不到。

如果强行从前端推断，只能继续猜。正确边界是：谁生成回复，谁给出来源审计。

### 2. streaming fallback 原日志有误导

streaming 出错后，如果 fallback 到 non-stream responder 并成功生成，旧代码仍可能额外打一条 stream fallback 日志。

这次结果对象以最终返回文本为准，避免“最终是 LLM，但看起来像 fallback”的二次误导。

### 3. no responder 不等于 fallback

没有 responder 时，本地文本不是“LLM 失败兜底”，而是 `deterministic`。这两个状态必须分开，否则排查时会以为模型调用失败。

## 验收结果

- `backend/LightRAG`: `776 passed, 33 skipped`
- `tests/test_lesson_runtime.py`: `126 passed`
- `ruff`: passed
- `stage-ui / stage-layouts / stage-web typecheck`: passed
- `stage-web browser`: `20 passed, 8 skipped`

### 真实浏览器复查

后续用真实 `lightrag-server` 跑了一轮 browser smoke，确认 `response_audit` 不只是后端单测通过，而是真的从 `/lesson/turn` 进入前端侧边栏：

- page entry: `source=llm`, `llm_called=true`, `fallback_used=false`, 侧栏显示 `LLM · xxms`。
- answer turn: `source=policy`, `llm_called=true`, `fallback_used=false`, 侧栏显示 `Policy LLM · xxms`。
- 测试里新增了 `expectRenderedReplyPath()`，直接用后端 `debug_signals.response_audit` 推导期望文案，避免前端再次靠猜测显示“规则兜底”。

一个容易误判的坑也确认了：直接在 Python 里 `build_lesson_runtime()` 不会接上 LightRAG server 的 `llm_model_func`，所以会看到 `live_prompts` 降级。真实验收必须走 `lightrag-server`，由 server 把 LLM binding 传给 lesson runtime。

## 更好的后续做法

现在 response source 已经进了 turn contract，而且真实浏览器侧边栏来源字段已经纳入 smoke 断言。下一步如果继续提高验收效率，可以补两个方向：

- fallback 时明确显示 fallback reason。
- 记录当前可见文案和后端 audit 的差异快照，方便以后排查“LLM 明明跑了但 UI 显示错”的问题。

这会让以后判断“LLM 有没有真的跑”不再依赖人工看日志。
