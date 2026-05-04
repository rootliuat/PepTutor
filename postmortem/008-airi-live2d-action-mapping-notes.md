# 008 AIRI Live2D Action Mapping Notes

Date: 2026-04-28

## 边界

这次只验证 AIRI 表现层，不改 Teacher Turn Policy，不改 prompt，不加模板、不加预设、不加课堂标签。

当前边界是：

- Teacher Kernel / Teacher Turn Policy 决定老师说什么。
- lesson runtime 给出轻量表现计划：speech style、mouth intensity、motion、expression。
- AIRI 负责 TTS 播放、嘴型驱动、Live2D motion 映射。
- 当前 Hiyori 模型没有 expression 文件，所以 expression 不能真实切表情，只能通过 motion 承载表现。

这条边界很重要。课堂决策和人物表现不能互相污染：不能为了让角色动起来，把教学判断写成前端模板；也不能为了课堂策略，把 AIRI 本体默认人格再拿回来生成老师回复。

## 本轮验证

真实浏览器地址：

```text
http://127.0.0.1:5180/lesson?page_uid=TB-G5S1U3-P24&student_id=codex-action-1820
```

后端：

```text
backend/LightRAG/.venv/bin/lightrag-server --host 0.0.0.0 --port 9625
```

前端：

```text
pnpm -F @proj-airi/stage-web exec vite --host 127.0.0.1 --port 5180 --strictPort
```

浏览器调试口：

```js
window.__PEPTUTOR_LIPSYNC_DEBUG__.state()
```

实测矩阵：

| 场景 | 老师动作计划 | 实际 Live2D motion | 表情结果 | TTS / 嘴型 |
| --- | --- | --- | --- | --- |
| 进 P24 开场 | `Curious` | `FlickUp` | `motion-only` | Edge Xiaoxiao 播放成功，mouthOpen 有音频驱动 |
| 学生答 `I am hungry.` 后推进 | `Happy` | `Tap` | `motion-only` | Edge Xiaoxiao 播放成功，mouthOpen 有音频驱动 |
| D3 学生答 `pizza` 后原地修 | `Think` | `FlickDown` | `motion-only` | Edge Xiaoxiao 播放成功，mouthOpen 有音频驱动 |
| 点击“再听一遍” | `Question` | `FlickDown` | `motion-only` | Edge Xiaoxiao 再播成功，mouthOpen 有音频驱动 |
| D3 学生答 `I'd like some water.` 后推进 | `Happy` | `Tap` | `motion-only` | Edge Xiaoxiao 播放成功，mouthOpen 有音频驱动 |

关键调试状态示例：

```json
{
  "nowSpeaking": true,
  "currentAudioSourceConnected": true,
  "lessonPerformanceAppliedMotion": "FlickDown",
  "lessonPerformanceAppliedExpression": "motion-only",
  "lessonPerformanceFallbackReason": "live2d_motion_alias:Think->FlickDown",
  "live2dLipSyncMouthOpen": 0.8854,
  "live2dLipSyncVolume": 0.9999
}
```

后端也确认了真实链路：

- `Lesson LLM audit ... status=success`
- `teacherresponse_source=llm` 或 `teacherresponse_source=policy`
- `Speech proxy TTS success ... voice=zh-CN-XiaoxiaoNeural ... content_type=audio/mpeg`

## 遇到的问题和处理方式

### 1. 表情看不到

原因不是前端没接，而是当前 Hiyori Live2D 模型没有 expression 文件。代码无法凭空切出模型不存在的表情。

处理方式：

- 先不伪造 expression 层。
- 只把 emotion 映射成可用 motion。
- 前端明确显示 `motion-only`，避免误判为“表情已接入”。

后续如果真要表情，有两个方案：

- 换带 expression 文件的模型。
- 做参数级表情预设，但这会变成模型适配工程，不应混进课堂逻辑。

### 2. motion 名称和模型动作组不一致

课堂层会给 `Happy`、`Think`、`Curious`、`Question` 这种语义动作，但 Hiyori 模型实际动作组是 `Tap`、`FlickUp`、`FlickDown` 等。

处理方式：

- 先 exact match。
- 再走语义别名映射。
- 映射失败时再退到模型已有的非 idle motion。
- UI 里显示 fallback reason，例如 `live2d_motion_alias:Think->FlickDown`。

这样能看清楚“老师想要的动作”和“模型实际能做的动作”之间的差距。

### 3. 课堂表现管道和 AIRI 通用 emotion 管道都会发 motion

浏览器 console 里能看到两类日志：

- 课堂表现层：`lessonPerformanceAppliedMotion`
- AIRI 通用管道：`emotion detected` / `Setting motion`

这不是当前验证的断链，但它是后续要小心的坑。两个管道都能动 Live2D，如果以后继续加动作，很容易互相覆盖。

当前处理方式：

- lesson 页面验收以 `__PEPTUTOR_LIPSYNC_DEBUG__.state()` 和侧边栏的 `实际动作` 为准。
- 不在这刀里重构 AIRI 通用 emotion 管道。
- 文档记录这个边界，避免后面误判 console 里多出来的 motion 日志。

更好的后续做法：

- lessonSafe 模式下，让课堂表现层成为 Live2D action 的单一 owner。
- AIRI 通用 emotion 管道只处理非 lesson 聊天。
- 这会改变表现层所有权，应该单独做，不和课堂策略混在一起。

### 4. TTS 有时被误判为没工作

之前容易只看 UI 文案或听不到扬声器声音，就判断 TTS 没接上。真实浏览器里应该看三个点：

- 后端 `Speech proxy TTS success`
- 前端 `currentAudioSourceConnected=true`
- Live2D `live2dLipSyncVolume` 和 `live2dLipSyncMouthOpen` 有变化

这次三项都成立，说明 Edge Xiaoxiao 到 audio playback 再到 mouthOpen 是通的。

### 5. WSL 端口绑定容易踩坑

前端 runtime config 会访问 WSL 网卡地址，之前如果后端只绑 `127.0.0.1`，浏览器侧会连不上。

处理方式：

- 后端真实浏览器验收用 `--host 0.0.0.0`。
- 本机脚本和 curl 仍用 `127.0.0.1`。
- 本地 curl 继续加 `--noproxy '*'`，避免代理把 localhost 报成假 502。

### 6. Python Playwright 不可用

当前环境里 `python3` 可用，但没有安装 `playwright` Python 模块。

处理方式：

- 这轮用 Chrome DevTools MCP 做真实浏览器操作。
- 没为了这次验证临时安装依赖，避免把环境问题混进功能验证。

后续如果要做可重复 CI/browser smoke，再补正式 Playwright 依赖和脚本。

### 7. 测试历史会污染真实历史列表

真实浏览器验收会写 `chat_history/peptutor-mili-teacher/`。

处理方式：

- 测试使用独立 student id，例如 `codex-action-1820`。
- 验收后清理对应测试历史文件。
- 不手动改用户已有历史。

## 结论

Live2D motion、Edge TTS、音频嘴型这条链路已经能跑通。当前看不到真实 expression 是模型素材缺失，不是播放链路没接。

下一刀如果继续处理表现层，应该只做一件事：收敛 lessonSafe 下的 action ownership，让课堂表现层成为唯一写 Live2D motion 的 owner。不要再往 prompt 或教学策略里加表现层标签。

## 2026-04-29 复查补丁

### 1. 非流式回放没有用 backend persona performance

现象：

- `/lesson/turn/stream` 会把 backend `airi_performance` 转成 ACT 事件。
- 但普通 `/lesson/turn` 后，前端 replay teacher prompt 时仍按 `evaluation` / `teaching_action` 自己猜一个动作。
- 结果是同一轮老师回复，流式和非流式可能出现不同的 motion / speech style / mouth intensity。

处理方式：

- 前端 `LessonTurnDebugSignals` 增加可选 `persona.airi_performance` 类型。
- `lessonAiriProfileForTurn()` 优先读取 backend persona performance。
- 只有 backend 没给 persona performance 时，才退回前端 heuristic。

这不是给老师话术加模板，也不是给 LLM 决策加标签；它只是在 AIRI 表现层复用后端已经算好的播放计划。

### 2. 页面跳转时历史会话切换抢跑，导致课堂状态被清空

现象：

- 真实浏览器 smoke 在 `P24 -> P25 -> P26` 后失败。
- 截图里页面已经显示 P26，但课堂 runtime 被清成“未开始”，textarea 处于 disabled。
- 根因是 `ensureCurrentLessonHistorySession()` 在页面切换时没有等 lesson start 完成；找不到当前页历史会话时直接 `resetLessonState()`，把刚启动的新页 runtime 清掉。

处理方式：

- history 身份优先用 `selectedPageUid/studentId`，而不是旧 runtime page。
- lesson 正在 loading 时不切历史会话。
- 如果当前 runtime 已经匹配当前页和学生，只创建新历史 session，不清 runtime。

这个修法保护数据安全：不迁移旧历史、不改旧 JSON、不重写用户数据，只避免前端生命周期把新课堂状态误删。

验证：

```text
pnpm exec vitest run packages/stage-ui/src/stores/lesson.test.ts packages/stage-ui/src/stores/lesson-chat-history.test.ts packages/stage-ui/src/stores/lesson-chat-provider.test.ts packages/stage-ui/src/composables/queues.test.ts packages/stage-ui/src/stores/lesson-airi-runtime.test.ts
=> 5 passed, 35 tests passed

pnpm -F @proj-airi/stage-ui typecheck
=> passed

NO_PROXY=127.0.0.1,localhost,::1 bash scripts/smoke_lesson_browser.sh
=> 8 passed, 19 skipped
```

### 3. classroom ambient 动作会污染老师回复表现审计

现象：

- 老师回复的 backend performance 已经正确应用，例如 `Curious -> FlickUp`。
- 播放结束后，lesson 页面会进入 listening / idle / thinking 这类本地 classroom state。
- 这些本地 ambient 动作之前复用了同一个 `markPerformanceApplied()` 路径，所以侧栏和 `__PEPTUTOR_LIPSYNC_DEBUG__` 可能显示最后一次 ambient 动作，而不是最后一轮老师回复真正的 backend performance。

处理方式：

- `applyLive2dPerformanceMotion()` 增加 `recordPerformanceState` 开关。
- 后端老师回复表现计划继续记录到 `performanceApplyStatus / appliedMotion / appliedExpression`。
- 本地 classroom ambient 动作仍然可以驱动 Live2D 当前 motion，但不再覆盖老师回复表现审计。

这次没有改 Teacher Turn Policy、prompt、模板、预设或标签；只改 AIRI 表现层的状态归属。

真实浏览器复查：

```text
http://127.0.0.1:5180/lesson?page_uid=TB-G5S1U3-P24&student_id=codex-action-owner-1745b
```

进页开场播放结束后：

```json
{
  "nowSpeaking": false,
  "currentAudioSourceConnected": false,
  "lessonPerformanceSource": "frontend_lesson_runtime_profile",
  "lessonPerformanceApplyStatus": "fallback",
  "lessonPerformanceAppliedMotion": "FlickUp",
  "lessonPerformanceAppliedExpression": "motion-only",
  "lessonPerformanceFallbackReason": "live2d_motion_alias:Curious->FlickUp"
}
```

学生输入 `第二块`，老师回复播放结束后：

```json
{
  "nowSpeaking": false,
  "currentAudioSourceConnected": false,
  "lessonPerformanceSource": "lesson_persona_context",
  "lessonPerformanceApplyStatus": "applied",
  "lessonPerformanceAppliedMotion": "Idle",
  "lessonPerformanceAppliedExpression": "motion-only",
  "lessonPerformanceFallbackReason": "live2d_expression_mapped_to_motion"
}
```

额外踩坑：

- 手动启动 Vite 时如果没带 `VITE_PEPTUTOR_LESSON_API_URL=http://127.0.0.1:9625`，页面会显示 `Failed to fetch`。
- 手动裸启 `backend/LightRAG/.venv/bin/lightrag-server` 时如果当前目录不是 `backend/LightRAG`，后端可能读不到该目录下的 `.env`，会退到默认 Ollama 配置；日志表现为 `llmprovider=ollama`、LLM 502、然后使用 fallback。
- 正确做法是用 `scripts/start_lesson_dev.sh` / `scripts/smoke_lesson_browser.sh`，或至少先 `cd backend/LightRAG` 再启动后端。
- 项目 smoke 脚本会自动注入正确后端地址；手动 MCP 浏览器验收需要显式带这个环境变量。
