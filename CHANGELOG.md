# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。

---

## [Unreleased]

### 新增
- **LLM 回复生成接入**：`Orchestrator._compose_reply` 在工具执行成功后用 `REPLY_PROMPT` 生成自然语言回复，替代固定话术"操作已完成"——实测回复能带出工具返回的关键信息（如"已为您提交 2026 年 9 月 25 日至 26 日的年假申请""受理编号 MOCK-2046C424""发票 INV-2026-777.pdf 已关联"）；LLM 未配置或调用失败时自动回退原模板且不阻断业务流程；`REPLY_PROMPT` 由"仅定义无调用方"的死模板改为实际使用（新增执行结果字段）
- **环境一键重建脚本** `scripts/setup_dev_env.sh`：换机器后 clone 仓库执行即可恢复开发环境——检查/安装 uv、创建 venv 并装依赖、生成 `.env`、检测并拉起 PostgreSQL/Redis、建库迁移种子、自动跑 pytest 核验；幂等设计，`--check` 只体检不安装
- **数据备份/恢复脚本** `scripts/db_backup.sh`：`pg_dump` 导出 admin_ai 库到 `backups/*.sql`（已 gitignore）并可恢复；恢复前自动生成当前数据快照以便回滚；内置处理 Windows 下 psql 的两个坑（MSYS 路径需 `cygpath` 转换、中文数据需 `PGCLIENTENCODING=UTF8`）
- **转人工落地**：`/chat/transfer` 由固定话术改为真实处理——校验会话存在性与属主后置 `conversations.status=transferred`、写入历史消息（meta 记录 `transfer_to_human` 与 `reason`）、清除会话待确认状态、调用 `NotificationService` 通知人工客服
- **端到端冒烟脚本** `scripts/e2e_smoke.py`：登录 → 聊天 → 工具（开发桩）→ 任务 → 审批 全链路 9 步验证
- **审批操作界面**：任务详情页支持同意/驳回（`can_approve` 标记）与属主取消（`is_owner` 标记）；详情对当前审批人开放
- **审批链创建**：高风险任务（报销/用印）确认执行后自动转 APPROVING 并为首个管理员生成待审批记录，低风险任务自动完成
- **对话落库**：`/chat/send`、`/chat/confirm` 写入 `conversations`/`messages` 表；`/chat/history/{id}` 返回真实历史（含卡片还原），仅会话属主可查；前端聊天页进入时自动恢复历史消息
- **任务落库**：工具执行成功后自动创建 `tasks` 记录（标题按业务与槽位生成，报销/用印标记 high risk），任务列表/详情/时间线有了真实数据来源
- **RAG 制度问答闭环**：编排器接入检索器，policy_query 返回带引用来源的回答；知识上传分片向量化入库（chunk_count 回填）；`/knowledge/search` 向量检索优先、ILIKE 兜底；文档删除同步清理向量分片；Chroma 服务/本地嵌入式双模式，调用超时自动降级
- **下游服务开发桩** `scripts/dev_stubs.py`：8001/8002/8003 模拟 OA/财务/物资系统，本地即可端到端联调工具链路
- **审计落库**：审计中间件对 POST/PUT/DELETE 请求写入 `audit_logs`（动作、用户、请求体、IP、UA、结论），失败仅告警不阻断业务；`GET /admin/audit-logs` 改为真实查询
- **管理后台真实数据**：`/admin/dashboard`、`/admin/metrics` 基于数据库统计（今日会话/任务、转人工率、完成率、高频意图），`/admin/tools` 读取工具注册中心
- **安全测试**：新增 admin 鉴权（401/403）、会话属主校验、任务取消状态校验、审计落库与 TraceId 中间件共 19 个用例
- **LLM 客户端工厂** `app/admin_ai/core/llm.py` — 按 `OPENAI_API_KEY` 构建 OpenAI 兼容客户端；未配置或依赖缺失时降级为规则回退
- **会话状态存储** `ConversationStateStore`（内存 / Redis 双实现）— 按 conversation_id 保存意图、业务类型、槽位、待确认状态

### 修复
- **`/chat/transfer` 补齐会话校验**：原端点无任何校验、不落库、对任意会话都谎报"已转接成功"——任何登录用户可对他人会话发起转人工；现校验会话存在（40004）与属主（40003），并真实落库会话状态与消息
- **修复任务写入真实 PostgreSQL 必失败的问题**：迁移创建的原生枚举类型为小写 value（如 `pending`），而 `SAEnum` 绑定的是大写 name（`PENDING`），所有任务/消息/会话的查询与写入均报枚举无效——模型列补 `values_callable` 对齐（此前从未在真实 PG 上验证过，E2E 冒烟发现）
- **修复对话写入的读写竞态**：`get_db_session` 的 teardown 提交发生在响应发送之后，紧随其后的查询可能读到提交前快照（E2E 中表现为任务列表计数为 0）；对话接口改为端点内显式提交
- **修复 Redis 8 客户端与 Redis 5 服务端不兼容**：redis-py 默认 RESP3 握手（`HELLO 3`）被服务端拒绝，所有 `from_url` 显式 `protocol=2`
- **槽位规则回退补强**：`《单据名》`→document_name、用印份数→copies、报销发票附件→invoice，无 LLM 时用印/报销流程可一步补全
- **加签后原审批记录关闭**：修复原审批人与被加签人重复审批的问题；禁止加签给自己
- **任务列表统计修正**：pending/approving 数量改为过滤后全量集合的 count，不再只统计当前页
- **datetime 统一**：新增 `utc_now()`（无时区 UTC），替换模型默认值与接口中 `datetime.utcnow`/带时区 `now()` 混用（jwt 签发除外）
- **知识库搜索 tags 匹配生效**：原实现在 `limit()` 之后过滤且候选集不含 tags-only 文档（死逻辑），现放大候选窗口并补独立 tags 扫描
- **`/admin/*` 接口补齐鉴权**（原 5 个端点完全无鉴权且返回硬编码数据）：全部挂 `get_admin_user` 依赖
- **高风险确认增加会话属主校验**：`ConversationState` 记录 `user_id`，`/chat/send` 与 `/chat/confirm` 均拒绝非属主操作，杜绝代他人确认报销/用印的风险
- **任务取消增加状态校验**：仅 pending/processing/approving 可取消，已完成/已失败/已取消任务返回 40001
- **中间件正式启用**：`TraceIdMiddleware`、`AuditMiddleware` 注册到应用（原已实现未注册，审计表永远为空）
- **全局异常处理器不再吞异常**：未处理异常记录结构化错误日志（含堆栈）后返回 50001
- **`confirmAction` 参数名纠正**：前端 `taskId` 改为 `conversationId`，与后端实现对齐（与 API 规格的 task_id 分歧为遗留决策 D-01）
- **多轮对话不再丢失状态**：`/chat/send` 每轮恢复并写回会话状态，槽位补全可跨请求完成
- **有 LLM 时不再空转**：修复 `SlotExtractor` 在传入 LLM 客户端时直接返回已有槽位（不抽取）的问题
- **编排器支持槽位续填**：正在补全槽位时跳过意图识别，避免把补充信息误判为未知意图而转人工
- **高风险确认可恢复**：`/chat/confirm/{conversation_id}` 基于会话状态恢复业务类型与槽位，取消不执行工具
- **前端 OAuth 回调**：先落 token 再调用 `/auth/me`，修复回调必然 401 跳回登录页的问题

### 变更
- **接入 DeepSeek 作为 LLM**（`OPENAI_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`）：意图识别与槽位抽取改走真实 LLM；实测发不含规则关键词的消息可识别为 `leave_request` 并追问槽位。`pytest` 95 passed、`e2e_smoke` 9/9 无回归。该 Key 可用模型为 `deepseek-flash` 与 `deepseek-v4-pro`（`deepseek-chat` 等旧名会被路由到 flash），5 条典型消息两模型均 5/5 命中，故取更快的 flash
- **RAG 方案重排**：DeepSeek 不提供 embedding API（`POST /embeddings` 返回 404），向量化不能复用它——嵌入改为二选一：另配智谱 `embedding-3` 等 OpenAI 兼容嵌入服务（零本机资产），或本地 `BAAI/bge-small-zh-v1.5`（95MB，离线可用）。待抽 `Embedder` 接口后落实
- 确认卡片 `card_data` 对齐 API 规格第 10 节：`{type, title, data, actions, warning}`
- `pytest` 默认仅运行非集成用例（`-m "not integration and not e2e and not llm"`），集成用例按需显式选择
- 修正过期的健康检查用例：认证上线后 `/chat/send` 无 Token 应返回 401

### 文档
- **交接说明按 2026-09-20 环境重建同步**：项目路径由 `Z:\zcode\admin-ai-agent` 迁至 `D:\NF\Test\Kit\admin-ai-agent`；PostgreSQL 由 Windows 服务改为 `D:\NF\Tools\pgsql` 绿色二进制（`pg_ctl` 手动启停，数据目录 `D:\NF\Tools\pgsql\pgdata`，trust 认证）；Python 运行时改为 uv 隔离管理的 3.12.14（系统 3.8 保持不动）；Redis 迁至 `D:\NF\Redis`；新增两条踩坑速查（Node/pnpm 的 Windows PATH 陷阱、MSYS 把 `/d/xxx` 当盘符相对路径）
- 环境核验 7 项全绿记录：PG/Redis/开发桩/后端 healthy、`pytest` 91 passed 1 deselected、`e2e_smoke` 9/9、前端构建成功
- 本地 `.env` 已配好智谱 OpenAI 兼容端点（`open.bigmodel.cn/api/paas/v4/`、`glm-4-flash`），仅待填入有效 `OPENAI_API_KEY`（当前走规则回退）

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
