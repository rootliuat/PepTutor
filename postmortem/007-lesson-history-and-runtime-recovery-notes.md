# 007 Lesson History And Runtime Recovery Notes

Date: 2026-04-28

## 背景

这次处理的不是单个输入框 bug，也不是单个历史记录 bug，而是课堂链路里的几个状态源互相打架：

- 后端有聊天 JSON 文件，但前端无法稳定恢复成完整课堂会话。
- 历史列表能看到文件，但点进去经常只剩开场白，或者混入别的页面内容。
- 新建会话后主舞台有开场消息，左侧聊天记录却显示空会话。
- 一旦恢复历史时缺少 runtime snapshot，前端会重新静默开课，page-entry watcher 又把历史消息覆盖掉。
- 组件各自维护一套 history hydrate / sync / snapshot watcher，导致顺序竞争和重复写入。

核心教训是：有存储不等于可恢复。能把文字写成 JSON，只解决了归档问题；要像原生 AIRI 那样继续会话，需要同时恢复 UI 消息、课堂 runtime 状态、当前 block、页面身份和会话身份。

## 这次做了什么

后端历史文件改成 v3 envelope：

```json
{
  "format": "peptutor-chat-history:v3",
  "raw_chat_session": {
    "messages": []
  },
  "restore_snapshot": {},
  "dialogue": []
}
```

其中三层含义不同：

- `raw_chat_session`：给前端完整恢复 UI 用，保留可见消息的 id、role、text、createdAt、metadata 等。
- `restore_snapshot`：给课堂 runtime 继续对话用，恢复 page_uid、current_block_uid、lesson state 等。
- `dialogue`：给人读和排查问题用，是压缩后的“米粒：/ 学生：”式记录。

后端保存时明确排除 `system` 和 `context` 消息，避免把 system prompt、调试上下文、active turn 等大包杂物写进人类聊天记录。

前端新增统一历史 store：

```text
frontend/airi/packages/stage-ui/src/stores/lesson-chat-history.ts
```

它接管这些职责：

- 初始化历史列表。
- 从文件恢复 raw messages。
- 从文件恢复 runtime snapshot。
- 新建课堂会话。
- 选择历史会话。
- 当前会话排队同步。
- 当前 runtime snapshot 持久化。
- 处理 page mismatch，防止不同页面写进同一个 JSON。

原来分散在 `LessonRuntimeChatPanel.vue` 和 `LessonSidebar.vue` 里的重复历史逻辑被移走。组件只负责展示和触发动作，不再各自抢着维护同一个历史状态。

## 关键问题和解决思路

### 1. 历史文件存在，但恢复不完整

旧文件只保存了压缩对话，适合看，不适合恢复。

解决方式是把“可阅读记录”和“可恢复状态”拆开：

- 可阅读记录放 `dialogue`。
- 完整 UI 消息放 `raw_chat_session.messages`。
- 课堂继续对话需要的状态放 `restore_snapshot`。

这样历史文件既能给人看，也能给程序恢复，而不是让一个字段承担三种职责。

### 2. 点历史后又回到开场白

根因是恢复历史时如果没有对应 snapshot，前端会调用静默开课。静默开课触发 page-entry watcher，历史消息又被新开场消息覆盖。

解决方式是让历史恢复路径优先读 `restore_snapshot`，并由统一 store 管理切换状态。恢复期间不让 page-entry 同步抢写。

### 3. 新建会话后左侧显示 0 条对话

新建会话时，主舞台的 page-entry 已经出现，但历史同步发生在 `switchingSession=true` 的阶段，被保护逻辑跳过了。

解决方式是在 create/select 完成、`switchingSession=false` 之后，再显式同步一次 page-entry 到当前 active session。

这个问题的教训是：同步动作必须发生在状态稳定之后。保护锁本身没错，错的是在锁还没释放时就期待同步成功。

### 4. P24 和 P4 混进同一个历史文件

旧逻辑没有把 page identity 当作数据完整性边界。当前 active session 属于 P24 时，切到 P4 仍可能继续往原 session 里写，最后一个 JSON 里同时出现两页内容。

解决方式是加 page mismatch guard：

- active session 有可见消息；
- active session 的 snapshot page 和当前页面不同；
- 那么不能继续写入这个 session；
- 必须创建当前页面的新会话。

这个判断不是用户体验细节，而是数据完整性边界。跨页混写一旦发生，后面再做恢复就无法判断哪个状态才是真的。

### 5. 多处 watcher 争抢同一份状态

之前 sidebar、runtime panel、history 文件工具各自有一部分历史逻辑。短期看方便，长期就会出现“谁最后写谁赢”的问题。

解决方式是收敛成一个 store，所有组件通过同一个 owner 读写。

这条经验很重要：同一类持久化状态只能有一个所有者。UI 组件可以订阅，可以触发命令，但不应该各自实现一套状态机。

## 验收方式

这次不是只跑单元测试，还做了真实浏览器流程。

真实浏览器流程：

1. 打开 P4。
2. 当前历史初始为 1 条 page-entry。
3. 发送 `Let's try`。
4. 再发送 `Mr Li is young`。
5. 历史增长到 5 条，当前 block 为 `TB-G5S1U1-P4-D1`。
6. 新建会话。
7. 新会话能看到 1 条 page-entry，不再是空历史。
8. 打开历史列表，选择刚才的 P4 会话。
9. 恢复出 5 条消息和 D1 状态。
10. 继续发送 `Picture 2`。
11. 历史增长到 7 条，block 前进到 `TB-G5S1U1-P4-D2`。

最后生成的 v3 文件：

```text
chat_history/peptutor-mili-teacher/2026-04-28_07-09-45_pr9wZ-pAmCV5OlPAWduJ.json
```

这个文件里有：

- `format = peptutor-chat-history:v3`
- `raw_chat_session.messages = 7`
- `restore_snapshot.page_uid = TB-G5S1U1-P4`
- `restore_snapshot.current_block_uid = TB-G5S1U1-P4-D2`

截图记录：

```text
frontend/airi/apps/stage-web/tmp-lesson-history-restore-desktop.png
frontend/airi/apps/stage-web/tmp-lesson-history-restore-mobile.png
```

## 验证命令

后端历史路由测试：

```bash
cd backend/LightRAG && .venv/bin/python -m pytest tests/test_lesson_chat_history_routes.py -q
```

结果：

```text
2 passed
```

后端全量测试：

```bash
cd backend/LightRAG && .venv/bin/python -m pytest tests -q
```

结果：

```text
768 passed, 33 skipped, 5 warnings
```

后端 lint：

```bash
cd backend/LightRAG && .venv/bin/ruff check .
```

结果：通过。

前端历史 store 单测：

```bash
cd frontend/airi && pnpm -F @proj-airi/stage-ui test:run src/stores/lesson-chat-history.test.ts
```

结果：

```text
3 passed
```

前端类型检查：

```bash
cd frontend/airi && pnpm -F @proj-airi/stage-ui typecheck
cd frontend/airi && pnpm -F @proj-airi/stage-layouts typecheck
```

结果：通过。

变更文件 lint：

```bash
cd frontend/airi && pnpm exec moeru-lint \
  packages/stage-ui/src/stores/lesson-chat-history.ts \
  packages/stage-ui/src/stores/lesson-chat-history.test.ts \
  packages/stage-layouts/src/components/Widgets/LessonRuntimeChatPanel.vue \
  packages/stage-layouts/src/components/Widgets/LessonSidebar.vue \
  packages/stage-layouts/src/components/Widgets/lesson-chat-history-files.ts
```

结果：0 errors / 0 warnings。

## 仍然存在的问题

旧的污染历史文件不会被自动清理。

例如旧文件里已经混入 P24 和 P4 的内容，新逻辑能防止未来继续混写，但不能凭空判断旧文件哪一段该保留、哪一段该删除。这个需要单独做迁移/修复工具，不能在运行时偷偷改。

前端根目录 `pnpm lint` 仍能看到一些既有问题，分布在 Doubao proxy、Live2D import、runtime import sort、hearing/audio-device 等无关文件。这次只保证本次改动文件 lint 干净，没有顺手重构无关问题。

TTS、Live2D 嘴型、情绪动作不是这次历史恢复的主线。这些链路要单独按“teacher_response -> SSE -> TTS -> audio play -> mouthOpen/expression/motion”排查，不能和历史存储混在同一刀里。

## 更好的长期做法

### 1. 用事件日志替代只存最终消息

更可靠的结构应该是 append-only event log：

```text
session_created
page_entered
teacher_replied
student_sent
block_changed
runtime_snapshot_checkpointed
session_selected
session_closed
```

UI 消息和 runtime snapshot 都可以从事件重放得到。当前 v3 文件已经比旧格式可靠，但仍然是“消息 + snapshot”的折中方案，不是真正的事件溯源。

### 2. 后端成为 session identity 的唯一权威

现在前端 store 已经统一了，但更稳的设计是让后端明确分配和校验：

- session_id
- character_id
- student_id
- page_uid
- lesson_id
- current_block_uid
- format_version

前端不能随便把当前页面写进任意 session。后端收到 page mismatch 的写入请求时，应该直接拒绝或返回 conflict。

### 3. 给历史文件加 schema 校验

v3 已经有 `format` 字段，但还没有严格 JSON schema。后面应该加 schema 校验，至少覆盖：

- required fields
- message role whitelist
- snapshot page_uid/current_block_uid 类型
- 禁止 system/context 写入 raw visible messages
- format version fallback 策略

这样格式错误会在测试和保存时暴露，而不是到浏览器恢复时才发现。

### 4. 做一次 legacy migration

旧 v1/v2 文件目前只能尽力 fallback。长期应该写一个只读迁移工具：

1. 扫描历史目录。
2. 识别混页文件。
3. 输出诊断报告。
4. 能安全迁移的转成 v3。
5. 不能安全迁移的标记为 legacy-readonly。

不要在用户打开历史时自动修，因为运行时自动修历史很容易把损坏扩大。

### 5. 加真实浏览器回归测试

这次手动浏览器验收证明链路能跑，但长期不能靠人工记忆。应该加一条 route-focused browser smoke：

1. 打开页面。
2. 发两轮消息。
3. 新建会话。
4. 选择旧会话。
5. 断言消息数、最后一条文本、current_block_uid。
6. 继续发一轮。
7. 断言历史 JSON 没有跨页混写。

这比单测更能防止 watcher 顺序和页面状态竞争退化。

### 6. 历史列表展示数据来源

调试时最好能在 UI 里看到：

- format version
- has raw_chat_session
- has restore_snapshot
- page_uid
- current_block_uid
- last sync status
- restore warning

用户不需要天天看到这些，但开发模式下应该能打开。否则历史坏了时只能猜。

## 这次最重要的学习

第一，历史记录不是“聊天文本列表”，而是一个可恢复的课堂会话。

第二，能让人读的记录和能让程序恢复的记录不是同一个东西。前者要干净，后者要完整。

第三，跨页面、跨角色、跨学生写入同一个 session 是数据污染，不是 UI 小问题。

第四，复杂前端里最危险的不是某个函数写错，而是多个 watcher 都觉得自己有权同步状态。

第五，修这种问题不能只看文件有没有生成，要从真实用户路径验收：进页、发消息、新建、恢复、继续发、再看 JSON。

第六，后续如果继续接 AIRI 原生能力，边界仍然要清楚：Teacher Kernel 决定课堂内容，AIRI 决定播放和表现，历史系统负责保存和恢复课堂会话。三者不能互相抢职责。

## 2026-04-28 补充：单活 lesson tab / 会话租约

后续验收又暴露了同一棵问题树上的另一个根因：刷新或多标签页并存时，页面还没确定“这次应该恢复还是开新课”，就已经有组件开始初始化历史、启动 page entry 或同步当前会话。

这会带来两个结果：

- 刷新时偷偷重新 `startLesson`，多烧一次 LLM/TTS，并可能用新的开场白覆盖恢复出来的历史。
- 旧 lesson 标签页还挂着时继续同步旧本地会话，生成孤儿 JSON 或把过期状态写回当前历史。

这次补的不是教学逻辑，而是写入所有权：

- 租约按 `peptutor-mili-teacher + student_id + page_uid` 分桶，而不是全局抢一个 key。
- 同一个学生同一页只允许一个 lesson 标签页写历史；新标签接管后，旧标签进入只读。
- 父级 lesson route 负责初始化历史；`LessonSidebar` 和 `LessonRuntimeChatPanel` 不再各自提前初始化，避免子组件 mounted 早于 route page/student 解析。
- 页面恢复到 v3 snapshot 后，不再自动重新 `startLesson`；只有当前历史可写且可继续时才允许自动开课。
- 历史列表继续展示 `可继续 / 只读 / 可查看`，旧污染数据不自动修。

这次真实浏览器验收路径：

1. 进入 `TB-G5S1U3-P24`，学生 ID 为 `codex-lease-test-20260428-2212`。
2. 首轮 page entry 正常生成，历史为 1 条。
3. 发送 `I am hungry.`，恢复到 D3，历史为 3 条。
4. 刷新页面，网络请求只有 catalog/history 读取和 history sync，没有重新 POST `/lesson/turn`。
5. 刷新后继续发送 `I'd like some water.`，课堂继续到 D4，历史为 5 条。
6. 同一 isolated context 再打开一个相同 student/page 的 lesson 标签页。
7. 回到旧标签页，输入框显示“旧 lesson 标签页只读，当前写入已交给最新标签页”，发送被禁用。

验证结果说明这刀修的是“谁有权写”的问题，而不是“写什么”的问题。Teacher Turn Policy、prompt、RAG、TTS/Live2D 表现都没有动。

踩坑：

- 最初后端只监听 `127.0.0.1`，但前端 runtime config 指向 `172.20.133.79:9625`，浏览器里表现为 `Failed to fetch`。验收时需要让后端监听 `0.0.0.0`，或者把 runtime config 收到同一个 host。
- 子组件 `onMounted()` 比父级 route 的 `onMounted()` 更早，历史初始化放在子组件里会抢在 `page_uid/student_id` 解析前执行。这类初始化必须放回 route owner。
- 只看左侧消息数不够，必须看 Network：刷新恢复是否真的没有 `/lesson/turn`，否则 UI 看起来没问题，但后台已经重新开课。

更好的后续做法：

- 后端也校验 session 写入租约或 revision，前端只做第一道防线。
- history sync payload 带 `lease_token` 和 `snapshot_revision`，后端发现旧标签页写入时返回 conflict。
- 前端开发模式显示当前 lease identity、writer tab、read-only 原因，减少以后排查时间。
