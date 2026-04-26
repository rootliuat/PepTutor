# PepTutor 迁移到 WSL 的最小实施方案

## 目标
把当前 `PepTutor` 从 Windows 原生开发模式，迁移到一套更稳定的 WSL 开发环境，同时保留现有 Windows 副本，不做一次性硬切。

这次迁移的目标不是“一天内把所有东西全搬完”，而是：

1. 先在 WSL 里得到一套可跑的 `backend/LightRAG`
2. 再补 `backend/SimpleMem`
3. 最后补 `frontend/airi`
4. 等 WSL 跑稳后，再把它作为主开发环境

## 为什么值得迁
当前这个项目在 Windows 下已经暴露出几类典型噪声：

- 编码问题：`gbk / utf-8`
- 文件锁问题：本地 `Qdrant` 嵌入式锁文件
- 路径与权限问题
- 代理与网络行为不稳定
- Python 包在 Windows 下兼容碎片更多

对于这个项目的组合：

- Python 后端
- LangGraph / FastAPI
- Qdrant / LanceDB / SQLite
- Node 前端
- 真实 LLM 调用

WSL 会更接近后面云端 Linux 服务器的运行环境。

## 迁移原则
- 保留当前 Windows 工作副本，不覆盖、不删除
- WSL 内重新建立干净环境，不复用 Windows 的 `.venv`
- 仓库放在 WSL Linux 文件系统里，不放在 `/mnt/f/...`
- `.env` 手工迁移，不提交到 Git
- 先迁后端，再迁前端
- 每一步都要有验证命令

## 推荐目录
不要把主工作副本继续放在 `/mnt/f/TestCode/...`。

推荐：

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone <your-repo-or-local-copy> PepTutor
```

建议最终工作目录类似：

```bash
~/workspace/PepTutor
```

## 需要一起带过去的关键文件
这些是当前已经沉淀好的设计、试点数据和运行链路文件，迁移时要确保都在新副本里可用。

### 文档
- [current-status.md](/F:/TestCode/github_project/PepTutor/docs/current-status.md)
- [pilot-implementation-log.md](/F:/TestCode/github_project/PepTutor/docs/pilot-implementation-log.md)
- [lesson-testing-status.md](/F:/TestCode/github_project/PepTutor/docs/lesson-testing-status.md)
- [pilot-unit3-slicing-plan.md](/F:/TestCode/github_project/PepTutor/docs/pilot-unit3-slicing-plan.md)
- [test-data-samples.md](/F:/TestCode/github_project/PepTutor/docs/test-data-samples.md)
- [wsl-migration-plan.md](/F:/TestCode/github_project/PepTutor/docs/wsl-migration-plan.md)

### 人格与提示词
- [soul.md](/F:/TestCode/github_project/PepTutor/soul.md)
- [teacher_reasoning_service.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_reasoning_service.py)
- [teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/teacher_response.py)

### 教学主链路
- [lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/orchestrator/lesson_graph.py)
- [lesson_routes.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/api/routers/lesson_routes.py)
- [retrieval_scope.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/retrieval_scope.py)
- [memory_writeback.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/memory_writeback.py)
- [simplemem_client.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/lightrag/pedagogy/simplemem_client.py)

### 试点教材数据
- [g5s1u3-pilot-manifest.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-pilot-manifest.json)
- [g5s1u3-p24-p25-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p24-p25-pilot.json)
- [g5s1u3-p26-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p26-pilot.json)
- [g5s1u3-p27-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p27-pilot.json)
- [g5s1u3-p28-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p28-pilot.json)
- [g5s1u3-p29-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p29-pilot.json)
- [g5s1u3-p30-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p30-pilot.json)
- [g5s1u3-p31-pilot.json](/F:/TestCode/github_project/PepTutor/app/knowledge/structured/g5s1u3-p31-pilot.json)

### 当前关键测试
- [test_pilot_teacher_reasoning.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_reasoning.py)
- [test_pilot_teacher_response.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response.py)
- [test_pilot_teacher_response_opening_prompt.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_teacher_response_opening_prompt.py)
- [test_pilot_lesson_graph.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_graph.py)
- [test_pilot_lesson_api.py](/F:/TestCode/github_project/PepTutor/backend/LightRAG/tests/test_pilot_lesson_api.py)

## 不要迁移的本地垃圾
这些不要从 Windows 副本直接复制过去：

- `backend/LightRAG/.venv`
- `backend/SimpleMem/.venv`
- `frontend/airi/node_modules`
- `frontend/airi/.turbo`
- `backend/LightRAG/temp`
- 本地 Qdrant 嵌入式数据目录
- `.pytest_cache`
- `.ruff_cache`

## 推荐迁移顺序

### 阶段 1：准备 WSL 基础环境
在 Windows 里先确认：

```powershell
wsl -l -v
```

如果还没有 Ubuntu，安装：

```powershell
wsl --install -d Ubuntu
```

进入 WSL 后安装常用依赖：

```bash
sudo apt update
sudo apt install -y build-essential git curl unzip pkg-config libssl-dev python3 python3-venv python3-pip
```

如果前端也要在 WSL 里跑，再装 Node：

```bash
curl -fsSL https://get.pnpm.io/install.sh | sh -
```

或者你自己的 Node 安装方式，但要求最终有：

- `node`
- `pnpm`

### 阶段 2：把仓库放进 WSL Linux 文件系统
推荐方式是重新克隆；如果暂时没有远程仓库，就从 Windows 工作副本复制过去。

如果从 Windows 副本复制：

```bash
mkdir -p ~/workspace
rsync -a --exclude '.venv' --exclude 'node_modules' --exclude '.turbo' --exclude '.pytest_cache' --exclude '.ruff_cache' /mnt/f/TestCode/github_project/PepTutor/ ~/workspace/PepTutor/
```

如果 `rsync` 没装：

```bash
sudo apt install -y rsync
```

### 阶段 3：先迁 `backend/LightRAG`

```bash
cd ~/workspace/PepTutor/backend/LightRAG
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install --no-build-isolation -e .[test]
```

本地 `.env` 需要重新建，不要直接提交：

```bash
cp .env.example .env  # 如果存在
```

然后补这些你当前已经在 Windows 用过的关键项：

```env
LLM_BINDING=openai
LLM_MODEL=deepseek-chat
LLM_BINDING_HOST=https://api.deepseek.com
LLM_BINDING_API_KEY=...

PILOT_LESSON_LLM_ENABLED=1
PILOT_TEACHER_AGENT_LLM_ENABLED=1

QDRANT_PATH=/home/<your-user>/.local/share/peptutor/qdrant_local
```

如果继续用嵌入式 Qdrant，WSL 下推荐用 Linux 路径，不要再用 Windows 盘符映射路径。

### 阶段 4：验证 `LightRAG`

```bash
cd ~/workspace/PepTutor/backend/LightRAG
source .venv/bin/activate
python -m pytest tests/test_pilot_teacher_reasoning.py tests/test_pilot_teacher_response.py tests/test_pilot_teacher_response_opening_prompt.py
python -m pytest tests/test_pilot_lesson_graph.py tests/test_pilot_lesson_api.py
python -m ruff check --no-cache lightrag/pedagogy/teacher_reasoning_service.py lightrag/pedagogy/teacher_response.py lightrag/orchestrator/lesson_graph.py
```

通过标准：
- prompt / reasoning / response 测试通过
- `lesson_graph` / `lesson_api` 测试通过
- `ruff` 通过

### 阶段 5：再迁 `backend/SimpleMem`

```bash
cd ~/workspace/PepTutor/backend/SimpleMem
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install fastapi==0.115.0 \"uvicorn[standard]==0.32.0\" pydantic==2.12.0 lancedb==0.25.3 pyarrow==22.0.0 numpy==2.2.6 httpx==0.28.1 pytest==8.4.2 ruff==0.14.0
```

补本地 `.env`，至少包括：

```env
TENCENT_SECRET_ID=...
TENCENT_SECRET_KEY=...
TENCENT_ASR_SECRET_ID=...
TENCENT_ASR_SECRET_KEY=...
```

验证：

```bash
cd ~/workspace/PepTutor/backend/SimpleMem
source .venv/bin/activate
python -m pytest tests cross/tests
python -m ruff check .
```

### 阶段 6：最后迁 `frontend/airi`

```bash
cd ~/workspace/PepTutor/frontend/airi
pnpm install
pnpm test:run
pnpm lint
pnpm typecheck
```

如果只做最小联调，先跑 `stage-web` 即可。

## 推荐服务启动顺序

### 最小后端联调
1. `SimpleMem`
2. `LightRAG`

### 完整前后端联调
1. `SimpleMem`
2. `LightRAG`
3. `frontend/airi`

## WSL 下的建议运行方式

### SimpleMem
```bash
cd ~/workspace/PepTutor/backend/SimpleMem
source .venv/bin/activate
python -m uvicorn cross.asgi:app --host 127.0.0.1 --port 8321
```

### LightRAG
```bash
cd ~/workspace/PepTutor/backend/LightRAG
source .venv/bin/activate
python -m uvicorn lightrag.api.lightrag_server:app --host 127.0.0.1 --port 9625
```

### AIRI
```bash
cd ~/workspace/PepTutor/frontend/airi
pnpm dev
```

## 最小验收标准

### 验收 1：后端测试
- `teacher_reasoning` / `teacher_response` 相关测试通过
- `lesson_graph` / `lesson_api` 测试通过

### 验收 2：真实 lesson API
请求：

```json
{
  "thread_id": "demo-001",
  "student_id": "stu-001",
  "user_text": "学习五年级上册第31页"
}
```

期望：
- 正确进入 `第31页`
- 中文介绍本页
- 带重点句型
- 给一个短 probe

### 验收 3：真实 LLM
期望返回中可观察到：
- `teacher_reasoning.used_llm = true`
- `response_generation.used_llm = true`

### 验收 4：前端联调
在 AIRI 输入：
- `学习五年级上册第31页`
- `I am hungry.`
- `能拆开练吗？这个太长了`

期望：
- 走 lesson 路由
- 不掉回普通聊天
- 拆开练时进入更小粒度练习

## 迁移完成后的推荐主环境
如果以下条件同时满足，就可以把 WSL 作为主开发环境：

- `LightRAG` 测试通过
- `SimpleMem` 测试通过
- `frontend/airi` 基本联调通过
- 真实 lesson API 可用
- 真实 DeepSeek 调用可用

这时 Windows 副本保留为备份，不再作为主开发环境。

## 当前最小落地建议
先不要一次迁三端。

建议顺序：
1. 先在 WSL 里迁 `backend/LightRAG`
2. 跑通当前 lesson 教学链路
3. 再补 `SimpleMem`
4. 最后补 `frontend/airi`

这样迁移成本最小，也最不容易把现在已有成果打乱。
