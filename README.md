# PepTutor 米粒英语陪练课堂

English version: [README.en.md](README.en.md)

PepTutor 是一个面向小学英语教材陪练的可审计 AI 课堂系统。它把结构化教材、
课堂运行时、TeachingMove 教学动作契约、Live2D 前端课堂、语音输入输出和离线
证据工具组合在一起，用来解决普通大模型课堂容易跑题、重复、误判教学步骤的问题。

实时课堂主链路保持可控：RAGFlow、agentic 检索等外部工具只作为离线证据来源，
不控制课堂 route、block、TeachingMove 或学生可见回复。

GitHub 仓库：

```text
https://github.com/rootliuat/PepTutor
```

## 仓库内容

- `app/knowledge/`：教材资源、结构化课程数据和已评审的 teaching strategy 数据。
- `backend/LightRAG/`：课堂后端、LightRAG 服务、lesson runtime、语音代理、审计脚本和后端测试。
- `frontend/airi/`：基于 AIRI 的课堂界面、Live2D 舞台、ASR/TTS 前端集成和前端测试。
- `docs/`：交付文档、Teaching Harness 设计、课程图谱报告、RAGFlow/agentic 离线证据方案、演示材料。
- `scripts/`：本地启动脚本、smoke 包装器、审计脚本、课程图谱/证据工具和测试预算 guard。

## 系统架构

实时课堂链路：

```text
学生输入 / ASR
-> 前端课堂界面
-> 后端 LessonRuntime
-> planner / strategy runtime / TeachingMove
-> 确定性或 LLM 辅助的教师回复
-> 语音代理 / TTS
-> Live2D、聊天记录和 Sidebar 可观测信息
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

`app/knowledge/structured` 仍然是权威教材来源。RAGFlow、agentic 工具和未来可能的
GRPO 类实验，不能在未经评审的实现目标中覆盖实时课堂状态。

## 环境变量文件

项目本地主要使用两份环境变量文件：

```text
.env
backend/LightRAG/.env
```

使用示例文件生成本地配置：

```bash
cp .env.example .env
cp backend/LightRAG/.env.example backend/LightRAG/.env
```

真实环境文件不要提交到 Git：

```text
.env
backend/LightRAG/.env
frontend/airi/apps/stage-web/.env.local
```

环境职责：

| 文件 | 用途 |
| --- | --- |
| `.env` | 项目级语音和本地 demo 配置，主要是 TTS / ASR 代理凭据。 |
| `backend/LightRAG/.env` | 后端 LLM、embedding、向量检索和 LightRAG runtime 配置。 |
| `frontend/airi/apps/stage-web/.env.local` | 可选的前端本地覆盖配置，例如 lesson API 地址。 |

示例文件已经去掉真实 API：

```text
.env.example
backend/LightRAG/.env.example
```

里面只保留 `replace-with-your-...` 这类占位符。

## 本地启动

安装后端依赖：

```bash
cd backend/LightRAG
python -m venv .venv
.venv/bin/python -m pip install --no-build-isolation -e .[test]
```

安装前端依赖：

```bash
cd frontend/airi
pnpm install
```

启动课堂：

```bash
cd /root/my-project/PepTutor
./scripts/start_lesson_dev.sh
```

打开：

```text
http://127.0.0.1:5173/lesson
```

默认启动脚本会关闭较重的向量检索和 SimpleMem 功能，以减少本地 demo 的外部依赖。
如需完整链路：

```bash
./scripts/start_lesson_dev.sh --full-stack
```

## 验证

使用 `docs/test-budget-guard.md` 中的测试预算分层。默认先跑 L1 单测和 lint，
不要反复运行完整 20 页 smoke、browser smoke 或 deep smoke。

常用 L1 后端检查：

```bash
backend/LightRAG/.venv/bin/python -m pytest \
  backend/LightRAG/tests/test_page_teaching_strategy.py \
  backend/LightRAG/tests/test_teacher_strategy_renderer.py \
  backend/LightRAG/tests/test_lesson_strategy_runtime_slice.py -q
```

常用前端检查：

```bash
cd frontend/airi
pnpm -F @proj-airi/stage-ui exec vitest run \
  src/utils/lesson-text.test.ts \
  src/stores/modules/hearing.test.ts \
  src/stores/lesson-voice-hearing-fallback.test.ts
```

完整 smoke、browser smoke、deep smoke 由 `scripts/test-budget-guard.sh` 保护，
只有在目标明确且预算允许时才运行。

## 当前边界

- 当前没有实现 GRPO。
- 当前没有进行模型训练。
- RAGFlow 只是离线证据链路。
- Agentic retrieval 只是离线复核工具。
- TeachingMove 和已评审的 strategy state 仍然是课堂控制层。
- TTS 自然度和 Live2D mouthOpen 同步仍需要真实人工视听判断，不能宣称完全认证。

## 安全说明

- 不要提交 `.env`、`.env.local`、token、API key 或服务商密钥。
- 不要把生成的 smoke 报告和运行时聊天记录提交到 Git，除非任务明确要求提交一个小型、已评审的产物。
- 将 `app/knowledge/` 视为源数据。保留来源信息，任何 schema 变化都要记录。
