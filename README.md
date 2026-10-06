# Admin AI Agent

企业行政智能助理：员工通过自然语言发起请假、报销、会议室预定等请求，系统完成信息补全、规则检查、确认、工具调用和任务跟踪。

**当前版本：0.1.0 / Alpha。** 已有员工端与后端业务原型，下游联调使用开发桩，尚未完成真实企业系统接入和生产验收。模块状态与验证范围见 [当前状态](docs/guides/当前状态.md)。

## 开始开发

1. [开发入门](docs/guides/开发入门.md)：当前 Windows 目录 `D:\projects\admin-ai-agent`，环境与启动步骤。
2. [开发计划](docs/planning/开发计划.md)：优先修复项和验收标准。
3. [文档导航](docs/README.md)：按产品、架构、接口、前端和运维查资料。

默认远程：[GitHub 仓库](https://github.com/pretextQ/admin-agent)。原 [Gitee 仓库](https://gitee.com/qiulongfei4408/admin-ai-agent) 保留为额外远程。

## 主要实现

- 自然语言意图与槽位抽取、多轮补全、风险确认和规则回退。
- 任务/对话落库、本人进度查询、组织与审批规则路由。
- 飞书 OAuth 与开发登录；模型调用经统一脱敏网关。
- 文本知识入库、Chroma 检索与带来源的模板回答。
- 员工端登录、聊天、任务、审批和历史恢复。

这些能力仍有边界：假期校验使用示例余额、真实审批回调未接、RAG 模型需配置，WebSocket 只有回显。文件服务、独立后台 UI、监控、限流与容器部署尚未完成。证明开具目前是下游申请转发，预览/下载为产品设计目标，不能视为自动生成并盖章已经实现。

## 技术栈与目录

后端：Python 3.11+、FastAPI、SQLAlchemy、PostgreSQL、Redis；模型使用兼容协议适配；知识检索使用 Chroma。前端：React 19、TypeScript、Vite、Semi Design、Zustand、Axios。

```text
app/admin_ai/    后端 API、编排、审批、规则、工具与模型网关
frontend/       员工端应用
migrations/     Alembic 数据库迁移（001 / 002 / 003）
scripts/        开发桩、种子、同步、备份与冒烟
tests/          后端测试
docs/           开发与设计文档；历史资料在 archive/
```

实际依赖以 `pyproject.toml`、`frontend/package.json` 与前端锁文件为准。Celery、LangChain、sentence-transformers 等声明不代表相应业务模块已接入。

## 本地开发简表

以下命令在项目根 PowerShell 执行；先准备 PostgreSQL/Redis，创建 `admin_ai` 数据库。

```powershell
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
Copy-Item .env.example .env
# 配置数据库、Redis；无模型时清空示例 OPENAI_API_KEY
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts/seed_admin.py
.\.venv\Scripts\python.exe scripts/seed_org_demo.py
```

已有 `.env` 时不要覆盖。启动开发桩和后端使用两个终端：

```powershell
.\.venv\Scripts\python.exe scripts/dev_stubs.py
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.admin_ai.main:app --reload --host 127.0.0.1 --port 8000
```

第三个终端启动前端：

```powershell
Set-Location frontend
pnpm install --frozen-lockfile
pnpm dev
```

前端端口 3000；API 端口 8000；Swagger 仅 DEBUG=true 时开启。详细配置与本机脚本限制见 [开发入门](docs/guides/开发入门.md)。仓库尚无 Docker 部署文件，不能直接通过 docker compose 启动。

## 验证与参与

```powershell
.\.venv\Scripts\python.exe -m pytest tests/admin_ai -q
```

测试默认排除集成、端到端与真实模型用例。更多检查见 [测试计划](docs/guides/测试计划.md)。

[贡献指南](CONTRIBUTING.md) · [开发规范](docs/guides/开发规范.md) · [安全策略](SECURITY.md) · [更新日志](CHANGELOG.md)
