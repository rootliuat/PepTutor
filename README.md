# PepTutor / 米粒英语陪练课堂

PepTutor is an auditable AI English tutoring classroom for primary-school
textbook practice. It combines a structured curriculum, a lesson runtime,
TeachingMove contracts, a Live2D classroom frontend, speech input/output, and
offline evidence tools. The live classroom control layer remains deterministic
and reviewable: external tools such as RAGFlow or agentic retrieval are offline
evidence sources, not runtime teachers.

PepTutor 是一个面向小学英语教材陪练的可审计 AI 课堂系统。项目把结构化教材、
课堂运行时、TeachingMove 教学动作契约、Live2D 前端课堂、语音输入输出和离线
证据工具组合在一起。课堂主链路保持可控：RAGFlow、agentic 检索等外部工具只作
离线证据来源，不控制实时课堂。

GitHub repository:

```text
https://github.com/rootliuat/PepTutor
```

## What This Repository Contains / 仓库内容

- `app/knowledge/` — curriculum assets and reviewed teaching-strategy data.
- `backend/LightRAG/` — lesson backend, LightRAG service, lesson runtime,
  speech proxy, audits, and backend tests.
- `frontend/airi/` — AIRI-based classroom UI, Live2D stage, ASR/TTS frontend
  integration, and frontend tests.
- `docs/` — delivery docs, teaching-harness design, curriculum graph reports,
  RAGFlow/agentic offline evidence plans, demo and submission materials.
- `scripts/` — local dev launcher, smoke wrappers, audit scripts, curriculum
  graph/evidence tooling, and test-budget guard.

- `app/knowledge/`：教材资源和已评审的教学策略数据。
- `backend/LightRAG/`：课堂后端、LightRAG 服务、lesson runtime、语音代理、
  审计脚本和后端测试。
- `frontend/airi/`：基于 AIRI 的课堂界面、Live2D 舞台、ASR/TTS 前端集成和前端
  测试。
- `docs/`：交付文档、Teaching Harness 设计、课程图谱报告、RAGFlow/agentic
  离线证据方案、演示和比赛材料。
- `scripts/`：本地启动脚本、smoke 包装器、审计脚本、课程图谱/证据工具和测试预算
  guard。

## Architecture / 系统架构

Live classroom path:

```text
learner input / ASR
-> frontend lesson UI
-> backend LessonRuntime
-> planner / strategy runtime / TeachingMove
-> deterministic or LLM-assisted teacher reply
-> speech proxy / TTS
-> Live2D + transcript + sidebar observability
```

课堂实时链路：

```text
学生输入 / ASR
-> 前端课堂界面
-> 后端 LessonRuntime
-> planner / strategy runtime / TeachingMove
-> 确定性或 LLM 辅助的教师回复
-> 语音代理 / TTS
-> Live2D、聊天记录和 Sidebar 可观测信息
```

Offline evidence path:

```text
structured curriculum
-> curriculum graph audit
-> candidate planner
-> RAGFlow evidence chunks
-> agentic review harness
-> human-reviewed tightening plan
```

离线证据链路：

```text
结构化教材
-> 课程图谱审计
-> 候选修复规划
-> RAGFlow 证据分块
-> agentic 复核工具
-> 人工评审后的数据收紧方案
```

`app/knowledge/structured` remains the canonical curriculum source. RAGFlow,
agentic tools, and future GRPO-style experiments must not override live lesson
state without a reviewed implementation goal.

`app/knowledge/structured` 仍然是权威教材来源。RAGFlow、agentic 工具和未来可能
的 GRPO 类实验，不能在未经评审的实现目标中覆盖实时课堂状态。

## Environment Files / 环境变量文件

The project uses two main local environment files:

```text
.env
backend/LightRAG/.env
```

项目本地主要使用两份环境变量文件：

```text
.env
backend/LightRAG/.env
```

Use the examples as templates:

```bash
cp .env.example .env
cp backend/LightRAG/.env.example backend/LightRAG/.env
```

使用示例文件生成本地配置：

```bash
cp .env.example .env
cp backend/LightRAG/.env.example backend/LightRAG/.env
```

Never commit real API keys. The real files are ignored by Git:

```text
.env
backend/LightRAG/.env
frontend/airi/apps/stage-web/.env.local
```

不要提交真实 API Key。真实环境文件已被 Git 忽略：

```text
.env
backend/LightRAG/.env
frontend/airi/apps/stage-web/.env.local
```

Environment responsibilities:

| File | Purpose |
| --- | --- |
| `.env` | Project-level speech and local demo settings, especially TTS/ASR proxy credentials. |
| `backend/LightRAG/.env` | Backend LLM, embedding, vector retrieval, and LightRAG runtime settings. |
| `frontend/airi/apps/stage-web/.env.local` | Optional frontend-only local overrides such as lesson API URL. |

环境职责：

| 文件 | 用途 |
| --- | --- |
| `.env` | 项目级语音和本地 demo 配置，尤其是 TTS/ASR 代理凭据。 |
| `backend/LightRAG/.env` | 后端 LLM、embedding、向量检索和 LightRAG runtime 配置。 |
| `frontend/airi/apps/stage-web/.env.local` | 可选的前端本地覆盖配置，例如 lesson API 地址。 |

## Local Development / 本地启动

Install backend dependencies:

```bash
cd backend/LightRAG
python -m venv .venv
.venv/bin/python -m pip install --no-build-isolation -e .[test]
```

安装后端依赖：

```bash
cd backend/LightRAG
python -m venv .venv
.venv/bin/python -m pip install --no-build-isolation -e .[test]
```

Install frontend dependencies:

```bash
cd frontend/airi
pnpm install
```

安装前端依赖：

```bash
cd frontend/airi
pnpm install
```

Start the classroom stack:

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

启动课堂：

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

Open:

```text
http://127.0.0.1:5173/lesson
```

访问：

```text
http://127.0.0.1:5173/lesson
```

The default launcher disables heavy vector retrieval and SimpleMem features so
the classroom starts with fewer external dependencies. To use the full stack:

```bash
./scripts/start_lesson_dev.sh --full-stack
```

默认启动脚本会关闭较重的向量检索和 SimpleMem 功能，以减少本地 demo 的外部依赖。
如需完整链路：

```bash
./scripts/start_lesson_dev.sh --full-stack
```

## Validation / 验证

Use the test-budget ladder in `docs/test-budget-guard.md`.

使用 `docs/test-budget-guard.md` 中的测试预算分层。

Typical L1 backend checks:

```bash
backend/LightRAG/.venv/bin/python -m pytest \
  backend/LightRAG/tests/test_page_teaching_strategy.py \
  backend/LightRAG/tests/test_teacher_strategy_renderer.py \
  backend/LightRAG/tests/test_lesson_strategy_runtime_slice.py -q
```

常用 L1 后端检查：

```bash
backend/LightRAG/.venv/bin/python -m pytest \
  backend/LightRAG/tests/test_page_teaching_strategy.py \
  backend/LightRAG/tests/test_teacher_strategy_renderer.py \
  backend/LightRAG/tests/test_lesson_strategy_runtime_slice.py -q
```

Typical frontend checks:

```bash
cd frontend/airi
pnpm -F @proj-airi/stage-ui exec vitest run \
  src/utils/lesson-text.test.ts \
  src/stores/modules/hearing.test.ts \
  src/stores/lesson-voice-hearing-fallback.test.ts
```

常用前端检查：

```bash
cd frontend/airi
pnpm -F @proj-airi/stage-ui exec vitest run \
  src/utils/lesson-text.test.ts \
  src/stores/modules/hearing.test.ts \
  src/stores/lesson-voice-hearing-fallback.test.ts
```

Do not run full 20-page smoke, browser smoke, or deep smoke repeatedly. Those
commands are guarded by `scripts/test-budget-guard.sh`.

不要反复运行完整 20 页 smoke、browser smoke 或 deep smoke。这些命令受
`scripts/test-budget-guard.sh` 保护。

## Current Boundaries / 当前边界

- GRPO is not implemented.
- Model training is not implemented.
- RAGFlow is an offline evidence pipeline only.
- Agentic retrieval is an offline review harness only.
- TeachingMove and reviewed strategy state remain the classroom control layer.
- TTS naturalness and Live2D mouthOpen synchronization still require human AV
  judgement before being called fully certified.

- 当前没有实现 GRPO。
- 当前没有进行模型训练。
- RAGFlow 只是离线证据链路。
- Agentic retrieval 只是离线复核工具。
- TeachingMove 和已评审的 strategy state 仍然是课堂控制层。
- TTS 自然度和 Live2D mouthOpen 同步仍需要真实人工视听判断，不能宣称完全认证。

## Security / 安全

- Do not commit `.env`, `.env.local`, tokens, API keys, or provider secrets.
- Keep generated smoke reports and runtime chat history out of Git unless a task
  explicitly requests a small reviewed artifact.
- Treat `app/knowledge/` as source data. Preserve provenance and document schema
  changes.

- 不要提交 `.env`、`.env.local`、token、API key 或服务商密钥。
- 不要把生成的 smoke 报告和运行时聊天记录提交到 Git，除非任务明确要求提交一个
  小型、已评审的产物。
- 将 `app/knowledge/` 视为源数据。保留来源信息，任何 schema 变化都要记录。
