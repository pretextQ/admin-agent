# Admin AI Agent

一个围绕企业行政事务打造的个人 AI 项目。

希望把员工“找制度、填表单、问进度”的过程，变成一次自然语言对话：说清楚需求，由系统补全信息、检查规则、发起办理，并持续跟踪结果。

> **员工说需求，系统协助办事。**

项目正在开发中，当前版本为 **0.1.0 / Alpha**。已经具备前后端业务原型，外部业务系统目前使用开发桩联调，后续逐步接入真实系统。

## 项目想法

行政办理往往涉及多个入口：先查制度、准备材料，再进入 OA 等系统提交申请，最后询问审批进度。这个项目希望把这些步骤连接起来，提供一个统一入口。

例如，员工可以提出：

- “公司的差旅报销标准是什么？”
- “我想申请两天年假，需要提供什么信息？”
- “帮我预定一个能容纳十个人的会议室。”
- “我提交的报销现在到哪一步了？”

这些是项目希望覆盖的使用场景。信息不足时继续追问，重要操作先确认，需要审批的业务按规则流转，结果以实际业务系统为准。

## 业务范围

产品设计包含 11 个场景，详细规则见 [业务场景文档](docs/scenarios/README.md)。

| 方向 | 场景 |
|---|---|
| 查询与预定 | 制度问答、会议室／车辆预定、单据进度与余额查询 |
| 日常申请 | 物资领用、请假、证明开具、报销、差旅 |
| 资产与人员事务 | 固定资产领用／归还、用印盖章、入离职办理 |

场景设计代表产品目标，实际实现与验证范围以 [当前状态](docs/guides/当前状态.md) 为准。

## 当前开发进度

目前已有：

- 自然语言意图与槽位抽取、多轮补全、风险确认和规则回退。
- 任务/对话落库、本人进度查询、组织与审批规则路由。
- 飞书 OAuth 与开发登录；模型调用经统一脱敏网关。
- 文本知识入库、Chroma 检索与带来源的模板回答。
- 员工端登录、聊天、任务、审批和历史恢复。

接下来优先完善：

1. 统一假期余额来源，完善业务参数、登录校验与审计保护。
2. 打通真实业务系统中的申请、审批、执行和取消流程。
3. 配置知识检索模型，完善制度问答和检索失败时的回复。
4. 根据首期范围补齐管理后台、文件服务、部署和监控。

当前尚未完成生产验收。真实下游接入、审批回调和部分知识检索能力仍需完善；WebSocket 目前只有回显，员工端使用 HTTP。任务优先级与验收标准统一维护在 [开发计划](docs/planning/开发计划.md)。

## 技术栈与目录

| 部分 | 当前主要技术 |
|---|---|
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 数据与状态 | PostgreSQL、Redis |
| 模型与知识检索 | 兼容接口的模型服务、统一调用网关、Chroma |
| 前端 | React 19、TypeScript、Vite、Semi Design、Zustand、Axios |
| 开发检查 | pytest、Ruff、mypy、oxlint |

```text
app/admin_ai/    后端 API、编排、审批、规则、工具与模型网关
frontend/       员工端应用
migrations/     Alembic 数据库迁移（001 / 002 / 003）
scripts/        开发桩、种子、同步、备份与冒烟
tests/          后端测试
docs/           开发与设计文档；历史资料在 archive/
```

依赖定义见 [pyproject.toml](pyproject.toml) 和 [前端 package.json](frontend/package.json)。完整后端依赖锁定、前端测试和 CI 仍在开发计划中。

## 本地开发

下面以 Windows PowerShell 为例。需要 Python 3.11+（建议使用 3.12）、uv、Node.js、pnpm、PostgreSQL 15+ 和 Redis。Node.js 版本需满足当前前端依赖要求。详细配置见 [开发入门](docs/guides/开发入门.md)。

### 1. 获取项目

```powershell
git clone https://github.com/pretextQ/admin-agent.git D:\projects\admin-ai-agent
Set-Location D:\projects\admin-ai-agent
```

已有本地仓库时直接进入目录，无需重复克隆。

### 2. 准备环境

```powershell
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

在 PostgreSQL 中创建 `admin_ai` 数据库，并编辑本地 `.env`：

- 设置 `ENVIRONMENT=development`。
- 配置实际的 `DATABASE_URL` 和 `REDIS_URL`。
- 不使用模型时清空示例 `OPENAI_API_KEY`；使用模型时配置对应 Key、地址与模型名。
- 本地需要 Swagger 时设置 `DEBUG=true`。

真实密钥只放本地配置，不提交到仓库。已有 `.env` 会保留。

### 3. 初始化数据库

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts/seed_admin.py
.\.venv\Scripts\python.exe scripts/seed_org_demo.py
```

种子数据用于开发演示，包含管理员、普通员工和部门关系。

### 4. 启动服务

在项目根目录分别打开两个终端。终端一启动 OA、财务、物资开发桩：

```powershell
.\.venv\Scripts\python.exe scripts/dev_stubs.py
```

终端二启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.admin_ai.main:app --reload --host 127.0.0.1 --port 8000
```

第三个终端启动前端：

```powershell
Set-Location D:\projects\admin-ai-agent\frontend
pnpm install --frozen-lockfile
pnpm dev
```

| 入口 | 地址 |
|---|---|
| 员工端 | http://localhost:3000 |
| 后端存活检查 | http://127.0.0.1:8000/api/health |
| API 文档 | http://127.0.0.1:8000/docs，仅 DEBUG=true 时开启 |

容器部署文件尚未落地，当前按上述方式本地启动。

## 验证

在项目根目录运行后端默认单元测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/admin_ai -q
```

默认排除真实数据库集成、端到端和真实模型用例。前端检查、开发桩冒烟及其他验证方式见 [测试计划](docs/guides/测试计划.md)。

## 开发文档

| 文档 | 内容 |
|---|---|
| [文档导航](docs/README.md) | 全部文档的统一入口 |
| [开发入门](docs/guides/开发入门.md) | 环境配置与启动步骤 |
| [当前状态](docs/guides/当前状态.md) | 实现边界与验证证据 |
| [开发计划](docs/planning/开发计划.md) | 下一步任务与验收标准 |
| [需求说明](docs/product/需求说明.md) | 产品目标与业务要求 |
| [后端技术方案](docs/architecture/行政智能系统-技术方案设计.md) | 模块职责与数据流 |
| [API 说明](docs/api/api-spec.md) | 当前接口与规划接口 |
| [开发规范](docs/guides/开发规范.md) | 编码、迁移与提交约定 |

历史交接、评审和模板保留在 [归档目录](docs/archive/README.md)。后续开发以当前状态与开发计划为准。
