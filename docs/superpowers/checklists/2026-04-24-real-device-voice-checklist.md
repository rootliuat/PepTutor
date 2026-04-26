# 2026-04-24 Real Device Voice Checklist

## Scope
- 目标：回到主机后，用真实浏览器、真实耳机/麦克风、真实后端 API，验收 `/lesson` 的 TTS、ASR 和完整 lesson 回合。
- 本清单默认使用：
  - 后端：`backend/LightRAG/.venv/bin/lightrag-server`
  - 前端：`frontend/airi/scripts/dev-lesson-https.sh`
  - 页面：`https://127.0.0.1:5174/lesson?page_uid=TB-G5S1U3-P24`
- 本清单默认当前 `.env` 已经配置好远端 LLM / Embedding，以及 Doubao ASR 服务端凭证；TTS 临时走免费的 Edge Xiaoxiao，不再消耗 Doubao 余额。

## 前置条件

### 1. 后端 env 检查
在启动前确认这些变量不是空值：

- `PEPTUTOR_REQUIRE_REMOTE_MODELS=1`
- `LLM_BINDING`
- `LLM_BINDING_HOST`
- `LLM_BINDING_API_KEY`
- `LLM_MODEL`
- `EMBEDDING_BINDING`
- `EMBEDDING_BINDING_HOST`
- `EMBEDDING_BINDING_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIM`
- `PEPTUTOR_LESSON_LIVE_PROMPTS=1`
- `PEPTUTOR_DEBUG_SIGNALS=1`
- `PEPTUTOR_LESSON_VECTOR_RETRIEVAL=0`
- `PEPTUTOR_DOUBAO_ASR_APP_ID`
- `PEPTUTOR_DOUBAO_ASR_API_KEY`
- `PEPTUTOR_DOUBAO_ASR_MODEL`
- `PEPTUTOR_DOUBAO_ASR_RESOURCE_ID`
- `PEPTUTOR_DOUBAO_ASR_APP_KEY`

额外检查：
- `LLM_BINDING_HOST` 和 `EMBEDDING_BINDING_HOST` 不能指向 `localhost` / `127.0.0.1`
- 不要让 `LLM_BINDING` 或 `EMBEDDING_BINDING` 退回 `ollama`

### 2. 后端启动
如果 shell 里有代理，先绕过本机流量：

```bash
export NO_PROXY=127.0.0.1,localhost,::1
```

启动后端：

```bash
cd /root/my-project/PepTutor/backend/LightRAG
PEPTUTOR_DEBUG_SIGNALS=1 \
./.venv/bin/lightrag-server --host 127.0.0.1 --port 9625
```

预期结果：
- 终端正常启动，不因为远端模型 guard 报错退出
- `http://127.0.0.1:9625/lesson/catalog` 可访问

失败时看哪里：
- 后端终端启动日志
- `docs/deployment/lesson-production.md`
- 如果提示 remote model guard 失败，优先看 `LLM_*` / `EMBEDDING_*`
- 如果提示 ASR speech proxy missing config，优先看 `PEPTUTOR_DOUBAO_ASR_*`
- 如果 Edge TTS 报 upstream error，优先看本机网络是否能访问 Microsoft Edge TTS 服务

### 3. 前端 HTTPS 启动
语音验收不要走纯 HTTP 页面，直接起 HTTPS：

```bash
cd /root/my-project/PepTutor/frontend/airi
VITE_PEPTUTOR_SKIP_REMOTE_ASSET_DOWNLOADS=1 \
./scripts/dev-lesson-https.sh
```

预期结果：
- 终端打印类似：
  - `Local: https://127.0.0.1:5174/lesson?page_uid=TB-G5S1U1-P2`
  - `Backend: http://127.0.0.1:9625 via /peptutor-api`
  - `TTS: peptutor-edge-tts / zh-CN-XiaoxiaoNeural`

失败时看哪里：
- 前端终端是否有 Vite 启动失败
- 证书文件是否能在 `frontend/airi/.cache/peptutor-dev-https/` 生成
- 如果 `5174` 被占用，先释放端口或换 `PEPTUTOR_STAGE_WEB_HTTPS_PORT`

### 4. 基础连通性检查
后端健康检查：

```bash
curl --noproxy '*' http://127.0.0.1:9625/lesson/catalog
```

前端同源代理检查：

```bash
curl -k --noproxy '*' https://127.0.0.1:5174/peptutor-api/lesson/catalog
```

浏览器打开：

```text
https://127.0.0.1:5174/lesson?page_uid=TB-G5S1U3-P24
```

第一次打开如果证书被拦：
- 继续访问本地自签证书页面

预期结果：
- 页面能打开
- 角色、左侧聊天记录、右侧 lesson 面板、底部输入条都可见
- 左侧 runtime facts 至少能看到：
  - `浏览器 = 安全上下文`
  - `流式 = 支持`
  - `自动发送 = 900ms`

失败时看哪里：
- 浏览器开发者工具 `Network`
- 左侧 runtime facts
- 前后端终端日志

### 5. 服务端 TTS 审计日志准备
这轮后端已经把 TTS 请求来源和文本摘要打进日志。验收前先确认你知道怎么查：

```bash
cd /root/my-project/PepTutor
rg -n "Speech proxy TTS (start|success|error)" backend/LightRAG/lightrag.log
```

预期结果：
- 能看到每条日志都带这些字段：
  - `client`
  - `client_chain`
  - `provider`
  - `source_tag`
  - `source_path`
  - `source_page_uid`
  - `origin`
  - `referer`
  - `user_agent`
  - `text_preview`
  - `text_sha1`

失败时看哪里：
- `backend/LightRAG/lightrag/api/speech_proxy_routes.py`
- 如果日志里完全没有这些字段，说明当前后端不是这轮更新后的进程

## TTS 验收

### 步骤
1. 打开：

```text
https://127.0.0.1:5174/lesson?page_uid=TB-G5S1U3-P24
```

2. 如果页面没有自动起课，点击右侧 `重新开始`。
3. 不要先开麦，先只验老师播报。
4. 听第一页 opening teacher response。

### 预期结果
- 页面一进入，或点击 `重新开始` 后，老师会自动播报当前页 opening 内容
- Live2D 嘴型跟着播报动
- 左侧 runtime 状态会进入 `说话中`
- 中央字幕条会显示当前 teacher response
- 浏览器能听到声音，不是静音、不是只有字幕没音频
- `Network` 里能看到：
  - `POST /peptutor-api/lesson/turn`
  - `POST /peptutor-api/api/peptutor/edge-tts`
- 后端日志里能看到：
  - `Speech proxy TTS start ... provider=edge ... source_tag=lesson-runtime source_path=/lesson source_page_uid=TB-G5S1U3-P24`
  - 后面紧接一条 `Speech proxy TTS success ...`

### 失败时看哪里
- 没有声音但有字幕：
  - 浏览器标签页是否静音
  - 系统输出设备是否切到耳机
  - `Network` 里 `edge-tts` 是否 `200`
  - 后端终端是否打印 TTS proxy 错误
  - 后端日志里的 `text_preview` 是否对应当前 opening 文本
- 连 opening teacher response 都没有：
  - `POST /peptutor-api/lesson/turn` 是否成功
  - 右侧当前任务和 `debug_signals` 卡是否刷新
  - 后端终端是否报 lesson runtime 错误
- 有声音但嘴型不动：
  - 页面必须在 HTTPS 下
  - 看浏览器控制台是否还有 lip sync 初始化错误

## ASR 验收

### 步骤
1. 保持页面在：

```text
https://127.0.0.1:5174/lesson?page_uid=TB-G5S1U3-P24
```

2. 点击底部麦克风按钮。
3. 在浏览器权限弹窗里允许麦克风。
4. 对着耳机麦克风说一句英文，例如：

```text
I'd like some water.
```

5. 观察左侧 runtime 卡、底部状态条、底部输入框。

### 预期结果
- 点击麦克风后，左侧状态先变成 `接入中`
- 授权成功后，左侧状态变成 `聆听中`
- 左侧 `当前设备` 会显示真实输入设备名，而不是 `未连接输入设备`
- 左侧 `权限` 会变成 `已授权`
- 说话时会出现 `实时转写`
- 底部输入框会短暂回填识别文本
- 左侧聊天记录或运行态里能看到当前 interim/final transcript
- 因为 lesson 当前强制 `900ms` auto-send，输入框里的文本可能在短暂停留后被自动发送并清空；这属于正常行为
- `Network` 里能看到 ASR websocket / speech proxy 活动：
  - `wss://.../peptutor-api/api/peptutor/doubao-realtime-asr`

### 失败时看哪里
- 点击麦克风后一直是 `接入失败`：
  - 左侧 runtime 卡里的失败文案
  - 浏览器地址是否仍然是 HTTPS
  - 浏览器权限设置里是否真的允许了麦克风
  - 系统是否识别到耳机输入设备
- 没有实时转写：
  - 左侧 `当前设备` 是否还是空
  - `Network` 里 ASR websocket 是否真正连上
  - 后端终端是否打印 realtime ASR websocket 错误
- 输入框没看到回填：
  - 先看左侧 `实时转写`
  - 如果左侧转写有内容但输入框没有，优先看前端控制台和 `ChatArea` 相关错误
- 说一句后立刻清空：
  - 先确认是不是正常 `900ms` auto-send，而不是失败
  - 如果左侧聊天记录已经出现学生那句，说明 ASR 到输入再到发送已经跑通

## 完整 Lesson 回合验收

### 步骤
1. 打开：

```text
https://127.0.0.1:5174/lesson?page_uid=TB-G5S1U3-P24
```

2. 点击 `重新开始`，确认老师 opening 先正常播报。
3. 点击麦克风并授权。
4. 说一句完整回答，例如：

```text
I'd like some water.
```

5. 不手动点发送，等待 `900ms` auto-send。
6. 等老师返回下一轮回复。
7. 在右侧 `Page UID` 里切到 `TB-G5S1U3-P25`，点击 `跳转`。
8. 再确认切页后的 opening teacher response 会自动播报。

### 预期结果
- 开课后 teacher opening 正常出声
- 学生说话后，左侧状态进入 `聆听中`
- 识别文本进入 `实时转写`
- `900ms` 后无需手点发送，学生句子进入左侧聊天记录
- 后端返回新的 teacher response
- 新 teacher response 会继续播报
- 后端日志会新增第二组 `Speech proxy TTS start/success`，而且 `source_page_uid` 仍然是当前页面 UID
- 右侧 `debug_signals` / memory debug 卡跟着最新 turn 更新，不停留在旧 turn
- 切到 `P25` 后：
  - URL query 里的 `page_uid` 改为 `TB-G5S1U3-P25`
  - 右侧当前页信息改为 `P25`
  - 新页面 opening teacher response 自动播报

### 失败时看哪里
- 学生句子没有自动发送：
  - 左侧 `自动发送` 是否还是 `900ms`
  - 左侧聊天记录是否出现学生句子
  - `Network` 是否发出新的 `POST /peptutor-api/lesson/turn`
- 学生句子发送了，但老师没回：
  - `POST /peptutor-api/lesson/turn` 返回码
  - 后端终端是否报 lesson runtime 异常
  - 右侧 `debug_signals` 是否更新
- 老师文字回了，但不播报：
  - `POST /peptutor-api/api/peptutor/edge-tts` 是否成功
  - 左侧状态是否进入 `说话中`
  - 系统输出设备是否切到了正确耳机
  - 后端 `Speech proxy TTS success` 是否存在；如果只有 `start` 没有 `success`，看对应 `error` 行
- 切页后还是旧页：
  - 看 URL 的 `page_uid`
  - 看右侧 `Page UID` 输入框和当前页标题
  - 看 `POST /peptutor-api/lesson/turn` body 里是不是新页 UID

## 推荐记录方式
- 每完成一段，截一张图：
  - opening teacher 播报中
  - 麦克风 `聆听中`
  - 左侧 `实时转写`
  - auto-send 后的新 teacher response
  - `P25` 切页成功
- 如果某一步失败，至少保留：
  - 浏览器 `Console`
  - 浏览器 `Network`
  - 后端终端最后 50 行日志

## 验收通过标准
- `TTS`：teacher opening 明确出声，字幕和嘴型同步可见
- `ASR`：说一句英文后，能看到实时转写，并能进入输入/发送链
- `完整回合`：开课 -> 学生说话 -> 自动发送 -> 收到 teacher response -> 切页 -> 新页 opening 再次播报
- `排查信息`：任何失败都能定位到浏览器、前端、后端三者之一，而不是“没有现象，不知道卡在哪”
