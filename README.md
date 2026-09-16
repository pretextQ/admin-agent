# Admin AI Agent

> 企业行政智能系统 · AI 行政数字员工
>
> **"员工动嘴，系统办事"**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/Node.js-20%2B-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18%2B-blue.svg)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](CHANGELOG.md)

---

## 项目简介

Admin AI Agent 是一套面向企业内部员工的 **AI 行政智能助理**。员工通过自然语言提出行政诉求，智能体理解意图并自动或半自动完成事务办理，支持多轮对话澄清与全流程状态跟踪。

**核心能力：**

- 🤖 自然语言理解：识别 **11 类行政业务场景**（对应 13 类意图标签，含 greeting/other）
- 🔄 多轮对话：信息不全时逐个反问，不猜测
- 🔧 工具调用：对接 OA、审批流、物资、日程等存量系统
- 📚 知识检索：RAG 检索制度文档并附引用来源
- 🔐 飞书 OAuth 登录：企业 SSO 授权 + 本地 JWT，开发环境提供 dev-login
- ⚖️ 分级授权：低 / 中 / 高风险场景采用不同处理策略
- 📋 全流程审计：操作留痕、可追溯

**支持场景：**

| 场景 | 频次 | 复杂度 | 自动化程度 |
|------|------|--------|-----------|
| 制度问答 | 高 | 简单 | ✅ 全自动（RAG） |
| 会议室 / 车辆预定 | 高 | 简单 | ✅ 全自动 |
| 综合查询（进度/余额） | 高 | 简单 | ✅ 全自动 |
| 物资领用 | 高 | 中 | ✅ 自动（校验库存/限额） |
| 请假申请 | 高 | 中 | ✅ 自动（校验余额/冲突） |
| 证明开具 | 中 | 中 | ✅ 自动（生成 + 推送盖章） |
| 报销申请 | 中 | 复杂 | ⚠️ 半自动（草拟 + 人工确认） |
| 差旅申请 / 订票 | 中 | 复杂 | ⚠️ 半自动 |
| 固定资产领用 / 归还 | 中 | 中 | ⚠️ 半自动 |
| 用印 / 盖章 / 合同 | 低 | 复杂 | ⚠️ 半自动（人工确认） |
| 入离职办理 | 低 | 复杂 | ⚠️ 半自动（分步引导） |

> 风险分级与人工确认策略见 [需求文档](docs/行政智能系统需求文档.md) §4.3。

---

## 技术栈

### 后端

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 语言 / 包管理 | Python 3.11+ / uv | 虚拟环境与依赖管理 |
| 后端框架 | FastAPI + Pydantic v2 | 异步高性能，自动生成 OpenAPI |
| 数据库 | PostgreSQL 15+ / SQLAlchemy 2.0 (async) | 主数据存储 |
| 缓存 / 会话 | Redis 7+ | 会话状态、限流 |
| 向量库 | ChromaDB + sentence-transformers | RAG 知识检索 |
| LLM | OpenAI 兼容 API | 意图识别、对话生成 |
| 任务队列 | Celery + Redis | 异步任务（通知、批量入库） |
| 迁移 | Alembic | 数据库版本管理 |
| 可观测性 | structlog + Prometheus | 结构化日志与指标 |
| 代码质量 | Ruff + mypy + pytest + pre-commit | 格式、类型、测试 |
| 部署 | Docker + Nginx | 容器化部署 |

### 前端

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 框架 | React 18 + TypeScript | 飞书 H5 应用 |
| 构建 | Vite 5 | 开发启动 <1s，HMR 极快 |
| UI 库 | Semi Design | 字节出品，飞书视觉语言一致 |
| 状态管理 | Zustand | 轻量（1KB），零 boilerplate |
| HTTP | Axios + TanStack Query | 拦截器 + 自动缓存/重试 |
| 路由 | React Router 6 | 标准方案，支持懒加载 |
| 包管理 | pnpm | 快速、磁盘友好 |
| 代码质量 | ESLint + Vitest | 格式、测试 |

---

## 项目结构

```text
admin-ai-agent/
├── app/                                    ✅ 包根
│   ├── __init__.py                         ✅
│   └── admin_ai/                           ✅ 主包
│       ├── __init__.py                     ✅
│       ├── main.py                         ✅ FastAPI 入口
│       ├── config.py                       ✅ Settings / get_config()
│       ├── api/                            ✅ 路由层
│       │   ├── routes.py                   ✅ 路由汇总
│       │   ├── deps_context.py             ✅ 依赖注入上下文
│       │   ├── response.py                 ✅ 统一响应信封与异常处理器
│       │   ├── schemas.py                  ✅ API Schema
│       │   ├── auth.py                     ✅ 认证接口
│       │   ├── chat.py                     ✅ 对话接口
│       │   ├── task.py                     ✅ 任务/待办接口
│       │   ├── knowledge.py                ✅ 知识库接口
│       │   ├── admin.py                    ✅ 管理后台接口
│       │   └── websocket.py                ✅ WebSocket 对话
│       ├── core/                           ✅ 业务核心
│       │   ├── agent/                      ✅ orchestrator / intent / slot / dialog / prompt
│       │   ├── rag/                        ✅ retriever
│       │   ├── tools/                      ✅ base / registry
│       │   ├── rules/                      ✅ engine
│       │   └── auth/                       ✅ deps / jwt_token / sso（飞书 OAuth）
│       ├── db/                             ✅ 数据库
│       │   ├── database.py                 ✅ Base / engine / session
│       │   ├── models.py                   ✅ SQLAlchemy 模型
│       │   ├── schemas.py                  ✅ 持久层 Schema
│       │   └── redis.py                    ✅ Redis 连接
│       ├── services/                       ✅ 服务层
│       │   ├── chat_service.py             ✅ 对话服务
│       │   ├── task_service.py             ✅ 任务服务
│       │   ├── knowledge_service.py        ✅ 知识库服务
│       │   └── notification_service.py     ✅ 通知服务
│       ├── middleware/                     ✅ 中间件
│       │   ├── audit.py                    ✅ 审计中间件
│       │   └── logging.py                  ✅ 日志中间件
│       └── utils/                          ✅ 工具函数
│           ├── logger.py                   ✅ structlog 配置
│           └── exceptions.py               ✅ 异常层级
│
├── migrations/                             ✅ Alembic 迁移
│   ├── env.py                              ✅
│   └── versions/                           ✅ 001_initial_tables
│
├── scripts/                                ✅ 运维脚本
│   └── seed_admin.py                       ✅ 管理员账号初始化
│
├── tests/                                  ✅ 测试
│   ├── conftest.py                         ✅ 共享 fixture 与 marker
│   └── admin_ai/                           ✅ 与主包同构
│       ├── test_api/                       ✅ API 测试
│       ├── test_core/                      ✅ 核心模块测试
│       └── test_services/                  ✅ 服务层测试
│
├── frontend/                               ✅ 前端（React + Semi Design）
│   ├── src/
│   │   ├── api/                            ✅ API 层（axios + 信封解包）
│   │   ├── stores/                         ✅ Zustand 状态管理
│   │   ├── hooks/                          ✅ 自定义 Hooks
│   │   ├── pages/                          ✅ 页面（chat / tasks / callback / login）
│   │   ├── components/                     ✅ 通用组件（Layout / ErrorBoundary / Empty）
│   │   ├── utils/                          ✅ 工具函数（飞书环境检测）
│   │   └── types/                          ✅ TypeScript 类型定义
│   ├── public/                             ✅ 静态资源 + 飞书 H5 SDK
│   ├── package.json
│   └── vite.config.ts
│
├── docs/                                   ✅ 项目文档
│   ├── 行政智能系统需求文档.md              ✅ PRD
│   ├── api/api-spec.md                     ✅ 接口规范
│   ├── architecture/技术方案设计.md          ✅ 架构设计
│   ├── scenarios/                          ✅ 业务场景设计（11 个场景）
│   └── guides/                             ✅ 开发规范 / 测试计划 / 部署运维
│
├── alembic.ini                             ✅
├── pyproject.toml                          ✅
├── requirements.txt                        ✅
├── requirements-dev.txt                    ✅
├── .env.example                            ✅
├── CHANGELOG.md                            ✅
├── CONTRIBUTING.md                         ✅
├── SECURITY.md                             ✅
└── README.md                               ✅
```

---

## 环境要求

| 环境 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.11+ | 推荐 3.12 |
| Node.js | 20+ | 前端构建 |
| pnpm | 9+ | 前端包管理 |
| uv | 最新版 | Python 包管理工具（可回退到 pip） |
| PostgreSQL | 15+ | 主数据库 |
| Redis | 7+ | 缓存 / 会话 |
| Docker | 24+ | 容器化部署（可选） |

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://gitee.com/qiulongfei4408/admin-ai-agent.git
cd admin-ai-agent
```

### 2. 环境配置

```bash
cp .env.example .env
# 编辑 .env，至少填写：
#   DATABASE_URL      PostgreSQL 连接
#   REDIS_URL         Redis 连接
#   OPENAI_API_KEY    LLM API Key
#   FEISHU_APP_ID     飞书应用 ID（生产必须配置）
#   FEISHU_APP_SECRET 飞书应用 Secret（生产必须配置）
```

### 3. 后端开发

```bash
# 安装 uv（如未安装）
pip install uv

# 创建并激活虚拟环境
uv venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate          # Windows

# 安装依赖
uv pip install -r requirements-dev.txt

# 执行数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.admin_ai.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 前端开发

```bash
cd frontend

# 安装依赖
pnpm install

# 启动开发服务器（http://localhost:3000，API 代理到 8000）
pnpm dev

# 构建生产版本
pnpm build

# 代码检查
pnpm lint
```

### 5. Docker 启动

> 部署所需文件见 [部署与运维](docs/guides/部署与运维.md)。

```bash
docker compose up -d
docker compose logs -f api
```

### 6. 访问服务

| 服务 | 地址 |
|------|------|
| 前端开发 | http://localhost:3000 |
| API 服务 | http://localhost:8000 |
| 健康检查 | http://localhost:8000/api/health |
| Swagger 文档 | http://localhost:8000/docs |
| ReDoc 文档 | http://localhost:8000/redoc |

### 7. 本地开发登录

开发环境（`ENVIRONMENT=development`）提供 `dev-login` 端点，无需飞书 OAuth 即可获取 JWT：

```bash
# 获取管理员 Token
curl "http://localhost:8000/api/v1/auth/dev-login?employee_id=admin001"

# 获取普通员工 Token
curl "http://localhost:8000/api/v1/auth/dev-login?employee_id=emp001"

# 初始化管理员账号（首次）
python scripts/seed_admin.py
```

---

## 开发指南

### 代码检查与格式化

```bash
# 格式化 + Lint（Ruff 覆盖 black/isort/flake8）
ruff format app/ tests/
ruff check --fix app/ tests/

# 类型检查
mypy app/
```

### 测试

```bash
# 全部测试
pytest tests/admin_ai -q

# 带覆盖率（整体门槛 80%）
pytest --cov=app.admin_ai --cov-report=term-missing --cov-fail-under=80

# 运行指定测试
pytest tests/admin_ai/test_core/test_intent.py -v

# 跳过慢测试
pytest -m "not slow"
```

### 数据库迁移

```bash
# 生成迁移
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

---

## 部署

生产部署、灰度与回滚、备份恢复、监控告警的完整说明见 [部署与运维](docs/guides/部署与运维.md)。

### 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_VERSION` | 应用版本 | `0.1.0` |
| `DEBUG` | 调试模式（生产必须 false） | `false` |
| `DATABASE_URL` | PostgreSQL 连接串 | - |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | LLM API Key | - |
| `OPENAI_BASE_URL` | LLM API 地址 | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名称 | `gpt-4o-mini` |
| `CHROMA_HOST` / `CHROMA_PORT` | 向量库地址 | `localhost` / `8005` |
| `SECRET_KEY` | JWT 密钥（生产必须修改） | - |
| `FEISHU_APP_ID` | 飞书应用 App ID | - |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret（生产必须配置） | - |
| `FEISHU_REDIRECT_URI` | 飞书 OAuth 回调地址 | - |
| `CORS_ORIGINS` | 允许的跨域来源 | `[]`（生产禁止 `["*"]`） |

完整清单见 [.env.example](.env.example)。

---

## 文档

| 文档 | 说明 |
|------|------|
| [需求文档](docs/行政智能系统需求文档.md) | 产品需求文档（PRD） |
| [技术方案](docs/architecture/行政智能系统-技术方案设计.md) | 后端技术架构设计 |
| [前端技术方案](docs/frontend/前端技术方案设计.md) | 前端架构设计（React + Semi Design） |
| [API 文档](docs/api/api-spec.md) | 接口规范 |
| **[业务场景设计](docs/scenarios/README.md)** | **11 个业务场景详细设计（意图/槽位/规则/流程）** |
| [设计计划与里程碑](docs/guides/设计计划与里程碑.md) | 项目规划 |
| [开发规范](docs/guides/开发规范.md) | 工程流程与约束 |
| [代码风格指南](docs/guides/代码风格指南.md) | 代码风格细则 |
| [测试计划](docs/guides/测试计划.md) | 测试策略 |
| [部署与运维](docs/guides/部署与运维.md) | 部署、监控、运维 |
| [安全策略](SECURITY.md) | 安全与漏洞报告 |
| [贡献指南](CONTRIBUTING.md) | 参与方式 |
| [更新日志](CHANGELOG.md) | 版本历史 |

---

## 项目状态

### 后端

- [x] 需求文档
- [x] 技术方案设计
- [x] API 接口文档
- [x] 工程规范与测试计划
- [x] 项目文档结构
- [x] 项目骨架代码（FastAPI + SQLAlchemy + 路由 + 中间件）
- [x] 核心模块开发（编排器 / 意图识别 / 工具 / 规则引擎）
- [x] 数据库模型（User / Conversation / Message / Task / Approval / Audit / Knowledge）
- [x] Alembic 首次迁移（7 张表）
- [x] 对话接口接上编排器（chat.py → orchestrator.process()）
- [x] 审批多级链（多步审批 / 加签 / 状态校验）
- [x] 飞书 OAuth 登录（授权码模式 / dev-login）
- [x] 单元测试（全部通过）
- [ ] 集成测试与联调
- [ ] 上线部署

### 前端

- [x] 前端技术方案设计（React + Semi Design + 飞书 H5）
- [x] 项目脚手架（Vite + React 19 + TypeScript）
- [x] 类型定义 + API 层（Axios 拦截器 + 信封解包）
- [x] Zustand 状态管理（auth/chat/app stores）
- [x] 认证流程（OAuth 回调 + dev-login + useAuth hook）
- [x] 对话页面（消息收发 + 确认卡片 + 转人工）
- [x] 任务页面（列表 + 筛选 + 详情 + 时间线）
- [x] 布局组件 + 路由配置 + ErrorBoundary
- [x] 生产构建通过（595KB JS + 236KB CSS）
- [ ] 审批操作（同意/驳回/加签）— 下迭代
- [ ] WebSocket 实时对话 — 下迭代
- [ ] E2E 测试
- [ ] 前端部署

---

## 贡献指南

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解分支、提交与 PR 流程。

---

## 版本历史

当前版本 **0.1.0**。详见 [CHANGELOG.md](CHANGELOG.md)。

---

## 开源协议

本项目采用 [MIT](LICENSE) 协议。

---

## 联系方式

- 问题反馈：[Gitee Issues](https://gitee.com/qiulongfei4408/admin-ai-agent/issues)
- 安全漏洞：见 [SECURITY.md](SECURITY.md)
