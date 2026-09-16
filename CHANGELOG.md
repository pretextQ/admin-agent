# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。

---

## [0.1.0] - 2026-09-16

### 新增
- **对话接口接上编排器** — `/chat/send` 调用 `orchestrator.process()`，返回统一信封
- **编排器逻辑补漏** — 未知意图转人工、确认恢复路径、工具报错返回 transfer_task_data
- **Alembic 首次迁移** — 7 张表：users / conversations / messages / tasks / approvals / audit_logs / knowledge_docs
- **审批多级链修复** — action/状态校验、多步审批检查、加签（add_sign）、timeline ownership
- **知识库接口诚实化** — upload 返回 `pending_index`、search 用 ILIKE 关键词匹配占位
- **飞书 OAuth 登录** — 授权码模式（`/auth/feishu/login-url` + `/auth/feishu/callback`）
- **开发环境登录** — `/auth/dev-login` 仅 development 可用，无需飞书 OAuth
- **管理员种子脚本** — `scripts/seed_admin.py` 初始化 admin001 账号
- **会议室规则校验** — `_validate_meeting_room`（时长 ≤8h、同一天）
- **UserModel.open_id 字段** — 飞书用户关联
- **KnowledgeDocModel.content 字段** — 知识文档内容存储
- **飞书配置项** — `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_REDIRECT_URI`，生产 fail-fast

### 变更
- `/auth/login` 和 `/auth/refresh` 端点已删除，替换为飞书 OAuth 流程
- `/chat/send`、`/chat/history`、`/chat/confirm`、`/chat/transfer` 全部挂 `get_current_user` 认证
- 规则引擎 validators 新增 `meeting_room` 类型

### 文档
- 需求文档 V1.2 → V1.3：前置条件改为飞书授权登录
- API 文档 V1.2 → V1.3：认证接口替换为飞书 OAuth
- 技术方案 V1.3 → V1.4：新增飞书 OAuth 时序图
- 部署与运维：配置管理补飞书配置项
- 测试计划：认证用例改为飞书回调链路（mock）

### 新增
- 项目文档结构
- 需求文档（PRD）
- 技术方案设计
- API 接口文档
- 开发规范、代码风格指南、测试计划、设计计划与里程碑
- 工具链收敛为 ruff（format + lint）+ mypy + pytest + pre-commit
- **FastAPI 项目骨架**（`app/admin_ai/main.py`）
- **配置模块**（`app/admin_ai/config.py`）— pydantic-settings，生产 fail-fast
- **数据库层**（`app/admin_ai/db/`）— SQLAlchemy 2.0 async 模型：User / Conversation / Message / Task / Approval / AuditLog / KnowledgeDoc
- **API 路由层**（`app/admin_ai/api/`）— 认证 / 对话 / 任务 / 知识库 / 管理后台 / WebSocket 全套路由
- **统一响应信封** `{code, message, data}` 与全局异常处理器
- **智能体核心模块**（`app/admin_ai/core/agent/`）— 编排器 / 意图识别 / 槽位抽取 / 多轮对话管理 / Prompt 模板
- **RAG 检索器**（`app/admin_ai/core/rag/retriever.py`）
- **工具注册中心**（`app/admin_ai/core/tools/`）— BaseTool / ToolRegistry / ToolResult
- **规则引擎**（`app/admin_ai/core/rules/engine.py`）— ValidationResult / RuleEngine
- **认证依赖**（`app/admin_ai/core/auth/deps.py`）— get_current_user / get_admin_user
- **服务层**（`app/admin_ai/services/`）— ChatService / TaskService / KnowledgeService / NotificationService
- **中间件**（`app/admin_ai/middleware/`）— AuditMiddleware / TraceIdMiddleware
- **Redis 连接管理**（`app/admin_ai/db/redis.py`）
- **异常层级**（`app/admin_ai/utils/exceptions.py`）
- **Alembic 迁移配置**（`alembic.ini` + `migrations/env.py`）
- **测试基础设施** — conftest.py / mock_llm / 自定义 marker
- **单元测试** — 意图识别 / 槽位抽取 / API 健康检查，共 13 个用例，全部通过
- **业务场景设计文档**（`docs/scenarios/`）— 11 个场景的完整业务逻辑设计（意图/槽位/规则/流程/工具/异常/审计/测试用例）

### 变更
- `pyproject.toml` 确立为依赖与工具链的唯一真相源，`requirements*.txt` 由其派生
- 软件版本统一为 `0.1.0`（pyproject / `.env` / FastAPI 应用）
- 统一目录布局与导入路径为 `app/admin_ai/...`，first-party 为 `app`

### 修复
- 修正 `.env.example` 与 `Settings` 字段不一致可能导致的配置静默失效问题

### 文档
- 统一 API 响应信封 `{code, message, data}` 与错误码口径
- 对齐覆盖率口径（Core ≥90%、Service ≥85%、API ≥80%、整体 ≥80%）
- 对齐验收指标（意图识别第 2 周 ≥85%、M4/上线 ≥92%）

### 移除
- 移除 black / isort / flake8 及其依赖，改由 ruff 统一承担

---

## [0.0.1] - 2026-09-15

### 新增
- 项目初始化
- Git 仓库创建
- 基础文档结构

---

## 版本说明

版本格式：主版本号.次版本号.修订号

- **主版本号**：不兼容的 API 修改
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

当前开发版本为 `0.1.0`（未发布），`0.0.1` 为初始基线版本。

[0.1.0]: https://gitee.com/qiulongfei4408/admin-ai-agent/compare/v0.0.1...v0.1.0
[0.0.1]: https://gitee.com/qiulongfei4408/admin-ai-agent/releases/tag/v0.0.1
