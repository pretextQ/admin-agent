# Admin AI Agent 项目代码 Review 报告

> 版本：V1.1　|　日期：2026-09-20（追加 Batch 5~8 进展；评审基线为 2026-09-17）
> 评审范围：后端 `app/`、前端 `frontend/`、`migrations/`、`tests/`、`scripts/`、`docs/`
> 评审方法：全量静态通读 + 实测（pytest / tsc / oxlint / vite build）+ 文档与实现交叉比对

---

## 一、结论摘要

项目工程骨架、目录分层、统一响应信封、错误码体系、配置 fail-fast、测试基建、文档体系都相当规范，**文档成熟度明显高于实现成熟度**。

评审时的初始状态存在多个「代码看起来通了、实际跑不通」的阻断问题：LLM 未接入、多轮对话状态不落库、任务/会话/审计不落库、高风险确认链路断裂、前端 OAuth 回调必然失败。

- **Batch 1（核心链路打通）已完成并提交**，主链路「对话 → 多轮补全 → 规则校验 → 高风险确认 → 工具执行」已可运行。
- **Batch 2（安全与持久化）、Batch 3（能力补齐）、Batch 4（审批闭环与端到端验证）已完成并提交**（328f730 / f824e75 / 1933b81），P0 全部关闭，P1 大部分关闭。
- **Batch 5~8 已完成并提交**（acef1be / b245cb0 / 063d0a9 / ae6aa89 / 802e3a8 / ce5ba7a）：
  转人工真实落地、环境一键重建与数据备份脚本、**LLM 接入 DeepSeek（意图/槽位/回复生成）**；
  测试基线升至 133 passed，E2E 冒烟 9/9 在真实 LLM 下通过。
- **Batch 9~13 已完成并提交**：文档全量同步、200 人企业级设计评审与两份设计补丁、
  需求文档 V1.4、**LLM 数据脱敏与合规（评审 B-1）**、**组织架构与审批路由（评审 B-2）**；
  测试基线升至 **192 passed, 7 deselected**（另有 7 个真实 PG 集成用例），
  E2E 冒烟 9/9（改为跨用户真实审批路由）。整改明细见文末附录。

### 问题分级统计（评审基线与当前状态）

| 级别 | 数量 | 说明 | 当前状态 |
|------|------|------|----------|
| P0 阻断 | 6 | 主流程无法完成 | ✅ 全部关闭 |
| P1 安全/正确性 | 14 | 越权、审计缺失、状态不一致 | 13 项已关闭（R-19 Prometheus 仍开放；R-10 部分） |
| P2 工程一致性 | 10 | 死代码、文档失真、缺部署文件 | 5 项已关闭（R-21 部分/R-25/R-26/R-27/R-29），其余待处理 |
| 新发现（评审未覆盖） | 3 | 真实环境才暴露 | 全部修复（PG 枚举、RESP3、提交竞态）+ Batch 13 另修 2 项（驳回悬挂待办、`/tasks/my` 集成用例） |

---

## 二、验证环境与实测结果

| 项 | 命令 | 初始结果 | 当前结果（2026-09-20） |
|----|------|----------|----------|
| 后端测试 | `python -m pytest tests/admin_ai -q` | 2 failed, 29 passed | **192 passed, 7 deselected** |
| 前端类型检查 | `pnpm -C frontend exec tsc -b` | 通过 | 通过 |
| 前端 lint | `pnpm -C frontend lint` | 0 error / 1 warning | 0 error / 1 warning |
| 前端构建 | `pnpm -C frontend build` | 通过 | 通过 |
| 端到端冒烟 | `PYTHONPATH=. python scripts/e2e_smoke.py` | 未实现 | **9/9 通过**（真实 DeepSeek + 跨用户审批路由） |
| 集成用例 | `pytest -m integration` | 需 asyncpg/DB | **7/7 通过**（真实 PostgreSQL） |
| lint/format | `ruff check app/ tests/` | 未执行 | 399 项待清（333 可自动修，详见交接文档 P2-14；Batch 13 新增文件零告警） |

> 环境说明：开发机系统 Python 为 3.8.10，本项目**用 uv 隔离安装 Python 3.12** 并建 `.venv`
> （不干扰系统 3.8）。真实依赖（PostgreSQL 16 / Redis / 开发桩 / LLM Key）已配齐，
> 一键重建见 `scripts/setup_dev_env.sh`。

---

## 三、P0 阻断问题（Batch 1 已处理）

| ID | 问题 | 位置 | 处理方式 |
|----|------|------|----------|
| R-01 | 多轮对话状态完全丢失，槽位补全永远无法完成 | `api/chat.py`（原每次新建空 `AgentContext`） | 新增 `ConversationStateStore`，`/chat/send` 每轮读写会话状态 |
| R-02 | LLM 从未接入；`SlotExtractor` 传入 LLM 时反而直接返回不抽取 | `core/agent/intent.py`、`core/agent/slot.py` | 新增 `core/llm.py` 工厂并注入，修复抽取分支 |
| R-03 | 高风险确认链路不可用（`business_type` 丢失） | `api/chat.py`、`core/agent/orchestrator.py` | 确认接口从会话状态恢复业务类型与槽位 |
| R-04 | 任务/会话/消息/审计从未落库 | `db/models.py`（仅类定义，无任何实例化） | **部分解决**：会话状态已持久化到 store；DB 落库仍待 Batch 2 |
| R-05 | 前端 OAuth 回调先 `getMe()` 后 `login()`，token 尚未写入 → 必然 401 跳回登录页 | `frontend/src/pages/callback/index.tsx` | 改为先落 token 再取用户信息 |
| R-06 | 确认卡片字段前后端不一致（后端 `data` vs 前端 `slots`） | `orchestrator.py` / `ConfirmCard.tsx` | 统一为 API 规格第 10 节字段 |

---

## 四、P1 安全与正确性问题（待修复）

### R-07　`/admin/*` 全部端点无鉴权
- **位置**：`app/admin_ai/api/admin.py`（dashboard / audit-logs / tools / tools 配置 / metrics）
- **证据**：全项目仅 `knowledge.py` 使用 `Depends(get_admin_user)`；admin 路由无任何认证依赖。
- **影响**：任何匿名请求可访问后台接口；`PUT /admin/tools/{id}/config` 无鉴权接收任意 dict。与 `docs/api/api-spec.md` 第 8 节「均要求管理员角色，否则 40003」直接冲突。
- **建议**：全部端点加 `Depends(get_admin_user)`，并补权限测试。

### R-08　审计 / TraceId 中间件定义了但从未注册
- **位置**：`app/admin_ai/main.py:82`（仅注册 CORS）；`middleware/audit.py`、`middleware/logging.py` 只有类定义。
- **影响**：无 trace_id、无请求日志、审计表(`audit_logs`)永远为空；需求「审计覆盖率 100%」无法满足。
- **建议**：`app.add_middleware(TraceIdMiddleware)` 与 `AuditMiddleware`；在编排器/关键写操作处写入 `AuditLogModel`。

### R-09　全局异常处理器吞异常且不打日志
- **位置**：`app/admin_ai/api/response.py:70-73`
- **影响**：线上 500 无堆栈可查，排障困难；未区分 DEBUG/生产。
- **建议**：`logger.exception(...)`，生产返回通用信息、DEBUG 附带详情。

### R-10　飞书 OAuth state（CSRF）校验可被静默跳过
- **位置**：`app/admin_ai/api/auth.py:56-67`（Redis 异常时 `except Exception: pass`）
- **影响**：Redis 不可用即跳过 state 校验，CSRF 防护形同虚设（生产同逻辑）。
- **建议**：校验失败默认拒绝；开发环境用显式开关放行。

### R-11　审批状态取值前后端不一致
- **位置**：后端 `app/admin_ai/api/task.py:220` 写入 `approval.status = payload.action`（`approve`/`reject`）；前端 `frontend/src/pages/tasks/TaskDetail.tsx:113` 判断 `a.status === "approved"`。
- **影响**：审批结果永远显示为错误颜色/文案。
- **建议**：统一状态枚举（建议后端存 `approved`/`rejected` 或前端同时兼容两者），前后端共用一份定义。

### R-12　加签（add_sign）实现不完整
- **位置**：`app/admin_ai/api/task.py:199-216`
- **问题**：未写入 `ApprovalModel.add_sign_user_id`（字段存在但未用）、未更新原审批记录状态、`step` 可能与现有步骤冲突。

### R-13　规则引擎类型健壮性不足
- **位置**：`core/rules/engine.py:153` `Decimal(str(amount))`、`:230` `quantity <= 0`
- **影响**：上游传入字符串/非数字时抛异常，仅被编排器兜底为「处理过程中出现错误」。
- **建议**：`validate()` 内逐条 try/except 并返回可读错误。

### R-14　会话/消息/任务/审计未落库（承接 R-04）
- **证据**：grep `ConversationModel(`、`MessageModel(`、`TaskModel(`、`AuditLogModel(` 全项目仅有类定义与 `__repr__`，无实例化。
- **影响**：`/tasks/my`、`/tasks/pending-approval` 永远返回空；无任务可跟踪，无审计可追溯。
- **建议**：在 chat/confirm 链路注入 DB 会话，落 `ConversationModel`/`MessageModel`；高风险操作落 `TaskModel`（同时解决 R-25 的 task_id 决策）。

### R-15　RAG 检索未接入编排器
- **位置**：`core/rag/retriever.py` 无任何调用；`orchestrator.py` 的 `policy_query` 仅返回「正在为您查询相关制度...」占位。
- **建议**：RAG 接入编排器并回填引用来源。

### R-16　`status_query` 为占位实现
- **位置**：`orchestrator.py` 返回 `needs_status_query` 占位，无实际查询。

### R-17　`vehicle` 工具不可达
- **位置**：`orchestrator.py` 的 `INTENT_TO_BUSINESS` 无 `vehicle`；`core/tools/registry.py` 注册了 `vehicle`。
- **建议**：补「车辆预定」意图映射或合并到会议室意图。

### R-18　知识库搜索 tags 过滤逻辑无效
- **位置**：`api/knowledge.py`（搜索分支）
- **问题**：SQL 已按 ILIKE 过滤 title/content，Python 端再用精确成员判断 `request.query in d.tags`，属死逻辑；RAG 向量检索仍为 TODO。

### R-19　可观测性指标未接入
- **位置**：`api/admin.py` 的 dashboard/metrics 返回硬编码 0；`pyproject.toml` 声明 `prometheus-fastapi-instrumentator` 但 0 引用。

### R-20　对话历史接口未实现
- **位置**：`api/chat.py` 的 `/chat/history/{conversation_id}` 返回空 `messages`，且缺 `page/page_size` 与归属校验，与 `docs/api/api-spec.md` §4.2 不符。

---

## 五、P2 工程一致性问题（待修复）

| ID | 问题 | 位置 | 说明 |
|----|------|------|------|
| R-21 | 死代码/未用模块 | `services/`、`middleware/`、`api/deps_context.py`、`core/rag/retriever.py` | 均为类定义，无调用方 |
| R-22 | 前端模板残留 | `frontend/src/App.css`、`frontend/src/index.css` | Vite/React 模板样式，`main.tsx` 未 import |
| R-23 | 部署文件缺失 | 仓库根 | 无 Dockerfile / docker-compose.yml / nginx.conf，但 README 教 `docker compose up -d` |
| R-24 | 依赖声明未使用 | `pyproject.toml` | `langchain`、`langchain-openai`、`chromadb`、`sentence-transformers`、`celery` |
| R-25 | 文档与实现不一致 | `README.md` | React 18/Vite 5/ESLint、Swagger 默认可用等与 `package.json`、`DEBUG=false` 不符 |
| R-26 | `frontend/README.md` 为模板原文 | `frontend/README.md` | 与项目无关 |
| R-27 | `.env.example` 注释过期 | `.env.example` | 注释称 `CELERY_*` 不在 Settings，实际 `config.py` 已定义 |
| R-28 | `requirements*.txt` 生成方式说明不实 | `requirements.txt` | 自称 `uv pip compile` 产物，实为手写范围约束（无 pin、无 `# via`） |
| R-29 | 时间处理 naive/aware 混用 | `db/models.py`（`datetime.utcnow`） vs `api/task.py`（`datetime.now(timezone.utc)`） | 潜在比较/序列化问题 |
| R-30 | mypy 严格模式未验证 | `pyproject.toml`、`db/database.py:24` | `disallow_untyped_defs=true` 下 `get_engine()` 缺返回类型等会报错 |
| R-31 | 覆盖率门槛与现状不符 | `pyproject.toml` | 声明 `--cov-fail-under=80`，实际 rules/tools/services 多数无测试 |

---

## 六、Batch 1 已完成内容（DONE）

### 6.1 提交记录

| 提交 | 说明 |
|------|------|
| `0790f03` | docs: 新增 Batch1 核心链路打通实施计划 |
| `bbd4b6d` | feat: 接入 LLM 客户端并按配置注入意图/槽位模块 |
| `af597f7` | feat: 新增会话状态存储(内存/Redis)并接入应用生命周期 |
| `12ac5c3` | feat: 编排器支持槽位续填，确认卡片对齐 API 规格 |
| `8819a01` | feat: 对话接口读写会话状态，打通多轮槽位补全 |
| `19f7a3b` | feat: 高风险操作确认/取消基于会话状态恢复，取消不执行工具 |
| `a5557f6` | fix: 前端先落 token 再取用户信息，确认卡片字段对齐 API 规格 |
| `851d327` | test: 修正过期的对话健康用例，默认仅运行非集成用例 |
| `a00b88c` | docs: 补充 Batch1 核心链路修复的更新日志 |

### 6.2 新增/变更的核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| LLM 客户端工厂 | `app/admin_ai/core/llm.py` | `build_llm_client(config)`；无 Key/无依赖时降级为规则回退 |
| 会话状态存储 | `app/admin_ai/core/agent/state_store.py` | `ConversationState` + 内存/Redis 实现 + `build_state_store` |
| 编排器 | `app/admin_ai/core/agent/orchestrator.py` | `AgentContext.awaiting_slots`；续填跳过意图识别；规格化确认卡片 |
| 槽位抽取 | `app/admin_ai/core/agent/slot.py` | 真正调用 LLM 抽取；增强规则回退（假别/数量/金额） |
| 对话接口 | `app/admin_ai/api/chat.py` | `/chat/send` 读写会话状态；`/chat/confirm/{conversation_id}` 恢复执行 |
| 应用入口 | `app/admin_ai/main.py` | 注入 LLM 客户端与状态存储 |
| 前端回调 | `frontend/src/pages/callback/index.tsx` | 先落 token 再取用户信息 |
| 前端确认卡片 | `frontend/src/pages/chat/ConfirmCard.tsx` | 读 `title/data/actions` |

### 6.3 新增/调整的测试

- `tests/admin_ai/test_core/test_llm.py`（新增 3 条）
- `tests/admin_ai/test_core/test_slot.py`（新增 LLM 抽取与回退用例）
- `tests/admin_ai/test_core/test_state_store.py`（新增 8 条）
- `tests/admin_ai/test_core/test_orchestrator.py`（新增续填/缺槽/确认卡片 3 条）
- `tests/admin_ai/test_api/test_chat.py`（新增多轮补全、确认、取消 3 条）

### 6.4 行为约定（后续开发需遵守）

- 会话状态：`ConversationState{intent, business_type, slots, awaiting_slots, pending_confirmation}`，按 `conversation_id` 存取。
- 槽位续填：当 `business_type` 存在且 `awaiting_slots=True` 时，编排器**跳过意图识别**，直接在既有业务上继续抽取。
- 高风险确认：编排器返回 `card_data.type == "confirmation"` 时，调用方持久化 `pending_confirmation=True`；确认接口据此恢复 `business_type/slots` 执行，取消则清理且不执行工具。
- 卡片字段：严格遵循 `{type, title, data, actions, warning}`。

---

## 七、遗留决策点

### D-01　确认接口的参数语义（Batch 1 引入的偏差）
- 现状：`/chat/confirm/{conversation_id}`，前端原本即传会话 id。
- 规格：`docs/api/api-spec.md` §4.3 写的是 `/chat/confirm/{task_id}`。
- 方案 A（成本低）：维持会话 id，改文档与前端注释。
- 方案 B（更贴合规格）：发起高风险操作时落 `TaskModel`，用真实的 `task_id` 确认；需给 chat 层引入 DB 会话，同时解决 R-14 落库。**推荐方案 B**。

### D-02　LLM 供应商与密钥
- 现状：仅支持 OpenAI 兼容接口，模型取 `config.LLM_MODEL`。
- 待确认：生产使用的模型、超时与重试策略、Token 成本统计口径。

---

## 八、后续修复路线图

### Batch 2：安全与数据落库（建议优先）

| 序号 | 任务 | 对应问题 | 验收标准 |
|------|------|----------|----------|
| 1 | `/admin/*` 加管理员鉴权 | R-07 | 匿名访问返回 40003；补测试 |
| 2 | 注册 TraceId/Audit 中间件并写审计 | R-08 | 请求带 `X-Request-Id`；`audit_logs` 有记录 |
| 3 | 全局异常日志化 | R-09 | 异常触发时输出堆栈 |
| 4 | 飞书 state 失败默认拒绝 | R-10 | state 无效返回 40001；开发开关可控 |
| 5 | 会话/消息落库 | R-14、R-20 | `/chat/history` 返回真实历史与分页 |
| 6 | 高风险操作落 `TaskModel`，确认改用 task_id | R-14、D-01 | 确认链路走 task_id；`/tasks/my` 有数据 |
| 7 | 统一审批状态枚举 + 完善加签 | R-11、R-12 | 前端状态显示正确；加签字段落库 |

### Batch 3：正确性与工程收口

| 序号 | 任务 | 对应问题 |
|------|------|----------|
| 1 | RAG 接入编排器，制度问答返回引用 | R-15 |
| 2 | 实现 `status_query` 综合查询 | R-16 |
| 3 | 补车辆意图映射 | R-17 |
| 4 | 修复知识库搜索逻辑 | R-18 |
| 5 | 接入 Prometheus 指标 | R-19 |
| 6 | 清理死代码与未用依赖 | R-21、R-24 |
| 7 | 补 Docker/nginx 部署文件 | R-23 |
| 8 | 对齐 README/前端 README/.env 注释/requirements 说明 | R-25~R-28 |
| 9 | 统一时间处理；补齐类型注解通过 mypy | R-29、R-30 |
| 10 | 补 rules/tools/services 单测，使覆盖率达标 | R-31 |

---

## 九、附录

### A. 复现命令

```bash
# 后端测试（默认排除集成/端到端/真实 LLM）
python -m pytest tests/admin_ai -q

# 集成用例（需 PostgreSQL/Redis 及 asyncpg）
python -m pytest -m integration -q

# 前端类型检查 / lint / 构建
pnpm -C frontend exec tsc -b --force
pnpm -C frontend lint
pnpm -C frontend build
```

### B. 沙箱环境说明

- 本机 `vite build` 在受限沙箱下会因 Vite 的 `windowsSafeRealPathSync` 触发 `spawn EPERM`（命名管道限制），属环境边界而非代码缺陷；放宽权限后构建通过。
- 本机 Python 3.8.10，低于项目要求的 3.11+；集成用例因缺 `asyncpg` 默认不跑。

### C. 相关文档

- 实施计划：`docs/superpowers/plans/2026-09-17-admin-ai-core-loop-batch1.md`
- API 规格：`docs/api/api-spec.md`
- 上线指南：`docs/项目完善与上线指南.md`
- 变更日志：`CHANGELOG.md`

---

## 附录：整改进展（2026-09-19 更新）

评审后按 Batch 2 → 3 → 4 三批完成整改，全部改动经单元测试（51 → 91 通过）与端到端冒烟（`scripts/e2e_smoke.py`，9 步全通过）验证。

### 已关闭项

| ID | 问题 | 修复方式 | 提交 |
|----|------|----------|------|
| R-07 | `/admin/*` 无鉴权 | 全部端点挂 `get_admin_user`；dashboard/audit-logs/metrics 改为真实查询 | 328f730 |
| R-08 | 中间件未注册 | TraceId/Audit 注册进 `main.py`；审计中间件对写操作落 `audit_logs` | 328f730 |
| R-09 | 异常处理器吞异常 | 补 `logger.error(..., exc_info=exc)` | 328f730 |
| R-12 | 加签不完整 | 原审批记录关闭（`status=done`）、生成被加签人 pending 记录、禁止自加签 | 1933b81 |
| R-14 | 会话/消息/任务/审计未落库 | chat 接口写 conversations/messages/tasks；工具成功执行创建任务记录 | 328f730 / f824e75 |
| R-15 | RAG 未接入编排器 | policy_query 检索 + 带引用回答；上传分片向量化；搜索向量优先；超时降级 | f824e75 |
| R-17 | vehicle 工具不可达 | 工具注册齐全 + 开发桩覆盖 calendar 路径，冒烟验证通过 | f824e75 |
| R-18 | tags 过滤死逻辑 | 候选窗口放大 + 独立 tags 扫描去重 | f824e75 |
| R-20 | history 未实现 | 返回真实落库消息（含卡片还原），仅属主可查 | 328f730 |
| R-21 | 死代码 | 部分解决：retriever / audit 中间件已接线；services 层仍待处理 | f824e75 |
| R-25 | README 文档失真 | 版本/状态/快速开始已按实现校正（本次提交） | 本次 |
| R-26 | frontend/README 模板原文 | 已重写为真实说明（本次提交） | 本次 |
| R-29 | datetime 混用 | 统一 `utc_now()`（jwt 签发除外） | 1933b81 |

### 端到端冒烟新发现并修复（评审未覆盖）

| 问题 | 修复方式 | 提交 |
|------|----------|------|
| 原生 PG 枚举绑定不匹配（SAEnum 绑 name，迁移按 value 创建），任务写入真实 PG 必失败 | 模型列补 `values_callable` | 1933b81 |
| redis-py 8 RESP3 握手被 Windows Redis 5 拒绝 | 所有 `from_url` 显式 `protocol=2` | 1933b81 |
| teardown 提交在响应之后造成读写竞态 | 对话接口端点内显式 commit | 1933b81 |

### Batch 5~8 关闭项（2026-09-20）

| 项 | 问题 | 处理方式 | 提交 |
|----|------|----------|------|
| 转人工 | `/chat/transfer` 为假话术、无校验、不落库，任何登录用户可对他人会话发起 | 校验会话存在（40004）与属主（40003）；置 `conversations.status=transferred`、写历史消息（meta 含 reason）、清除待确认状态、调用通知服务；真实 PG 端到端验证 | acef1be |
| R-02 | LLM 从未接入（仅规则回退） | 接入 DeepSeek：意图识别 + 槽位抽取 + **回复生成**（`Orchestrator._compose_reply`）；未配 Key 或调用失败自动回退，不阻断流程 | ae6aa89 / ce5ba7a |
| R-27 | `.env.example` 注释与 Settings 不符 | 已修正（现说明与 `config.py` 定义一致） | 随批次 |
| 新增 | 环境不可迁移：本机资产（PG/Redis/.venv）不入库，换机器需重踩全部坑 | `scripts/setup_dev_env.sh` 一键重建（幂等）+ `scripts/db_backup.sh` 数据备份恢复（含恢复前快照）；修掉 psql 的 MSYS 路径与 UTF8 编码两个真实 bug | b245cb0 |
| 新增 | `.sh` 在 `core.autocrlf=true` 下检出为 CRLF，换机器后脚本无法执行 | 新增 `.gitattributes` 锁定 `*.sh text eol=lf`，并 clone 实测验证 | 063d0a9 |

### Batch 13 关闭项（2026-09-20，评审 B-2）

| 项 | 问题 | 处理方式 | 提交 |
|----|------|----------|------|
| 设计评审 C-5 / B-2 | 审批人硬编码为「首个管理员」，与场景文档 APR-001/002 的金额分级相差一整个层级体系 | 新增 `departments`/`approval_rules`/`approval_delegations` 三表（迁移 `002`）与纯函数路由算法（自审拦截与上溯、停用上溯、链内去重、委派替换）；`chat.py` 确认路径改为按规则路由，解析不出则转人工指派并记录原因（`task.data._routing`）；审批流转支持任一人/会签 | 本次提交 |
| 设计评审 §5 / SECURITY §4.3 | 「每次调用按角色 + 数据归属 + 金额/范围判定权限」「查询强制注入本部门归属」未落地 | `/tasks/my?scope=my\|dept\|all`：归属条件下推 SQL，`dept`/`all` 每次访问写审计（`action=task_scope_query`） | 本次提交 |
| 新增 | 审批驳回后其余 `pending` 记录未关闭，任务已失败仍出现在他人待审批列表 | 驳回时关闭其余待审记录为 `skipped`；已出结论的记录不改写（保留审计追溯） | 本次提交 |
| 新增 | 组织架构无来源、无降级：部门/汇报线缺失时审批人无从谈起 | HR 组织同步（http 接口 + CSV 降级）+ 失败沿用上次快照、连续失败升级告警；开发环境 `seed_org_demo.py` | 本次提交 |
| 新增 | E2E 冒烟用同一账号既申请又审批，掩盖了「自审」缺陷 | E2E 改为跨用户：员工 emp999 提交 → 部门主管 admin001 审批，并断言 ≤2000 元为单级链 | 本次提交 |

### 仍然开放

**P1 级**：R-10（OAuth state 校验失败时静默跳过，开发环境可接受但生产需收紧）、
R-11（审批状态取值前后端不一致；**审批链本身已按 B-2 落地**，状态取值口径待前端一并统一）、
R-13（规则引擎类型健壮性）、R-16（`status_query` 仍为占位，意图已识别无消费方）、
R-19（Prometheus 指标未接入）。

**P2 级**：R-21（services 层仍为死代码，`notification_service` 已被转人工与审批路由失败通知调用）、
R-22（前端模板残留样式）、R-23（Docker/nginx 部署文件缺失）、R-24（`langchain*`/`celery` 声明未使用）、
R-28（requirements 生成方式说明）、R-30（mypy 严格模式未验证）、R-31（覆盖率未达声明门槛）。

**新开放**：ruff lint/format 债（2026-09-20 实测 360 项、64 个文件待重排，含 FastAPI `B008` 误报需配置豁免，
做法见交接文档 P2-14）；RAG 嵌入模型未定（DeepSeek 无 embedding API）；编排器自动转人工路径未通知人工客服；
审批路由的 T-10 双读校验期未安排、`users.department` 旧列 Contract 阶段另排（见设计补丁 §12）。

**开放决策**：D-01（`/chat/confirm` 规范用 `task_id`、实现用 `conversation_id`）、D-02（LLM 供应商/超时/成本口径）。
