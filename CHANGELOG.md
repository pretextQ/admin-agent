# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 与
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。

---

## [Unreleased]

### 新增
- **审批覆盖面补齐：规则支持按槽位条件分支 + 四个业务类型接入审批**
  - `core/approval/conditions.py`：条件求值器（算子受限 eq/ne/gt/gte/lt/lte/in/not_in，不做表达式解析）
    与派生上下文（`days` 由起止日期算出，含首含尾）；**槽位缺失即条件不成立**，绝不猜测
  - `approval_rules.condition`（JSON，可空）+ 迁移 `003`：按场景文档导入默认规则并拆分支
    - 用印：`seal_type = 合同章` → 法务（`role:legal`）；其余 → 部门主管（场景 10）
    - 请假：`days ≤ 2` → 主管；`days > 2` → 主管 + HR 复核（`role:hr`）；天数算不出走兜底（场景 05）
    - 差旅：`days ≤ 5` → 主管；`days > 5` → 总监 + 主管两级（场景 08）
    - 资产：价值 ≥5000 → 总监；≤5000 或价值未知 → 主管（场景 09）
    - 物资：单价 ≥100 → 主管；兜底 → 主管（场景 04，分级待接入库存单价）
  - **兜底规则**（金额区间与条件都为空）在同一步骤内让位于条件/区间规则，避免分支被稀释成多人并行
  - **审批清单与二次确认解耦**：`APPROVAL_REQUIRED_BUSINESS_TYPES`（默认 6 类）决定是否走审批，
    `HIGH_RISK_BUSINESS` 仍只管二次确认卡片；请假/差旅等审批类任务风险级别为 `medium`
  - **三种结果语义明确**：匹配→建链；该业务无规则（配置缺失）→转人工指派并告警；配了规则但本次不匹配
    →无需审批、任务直接完成（不再一律报错转人工）
  - 管理端与脚本支持 `condition` 字段（含 `validate_conditions` 校验）：`/admin/approval-rules`、
    `manage_approval_rules.py`（新增 `--condition`、列表渲染条件、导入导出）
  - 新增 32 个用例（条件求值 20、匹配与语义 10、管理端 2）+ 10 个真实 PG 集成用例
    （直接验证迁移导入的默认规则）；E2E 冒烟扩展为「请假 + 报销」双链路跨用户审批
- **组织架构与审批路由落地（评审 B-2，唯一未完成的阻断项）**：审批人不再取「首个管理员」，改按「业务类型 + 金额 + 申请人部门」路由，使审批链具备公司内部授权效力
  - `core/approval/router.py`：**纯函数**路由算法——规则匹配（含 min、不含 max；无金额业务只匹配区间为 NULL 的规则）、逐级解析（self/parent/top 部门主管、role、user）、**自审拦截与上溯**、停用/离职上溯、链内去重、委派替换
  - `core/approval/repository.py`：组织快照装载（含已停用用户，否则无法判断"审批人已停用"）、规则与委派装载、审批链落库、路由失败原因记录
  - 三张新表（迁移 `002`，Expand 阶段）：`departments`（物化路径树 + 上游 `external_id`）、`approval_rules`（金额区间 × 审批人类型）、`approval_delegations`（代理审批）；`users` 加 `department_id`（兼容期与旧 `department` 双写）；`approvals` 加 `approver_source` / `mode` / `delegated_from`
  - 迁移回填：按旧 `users.department` 生成扁平部门（旧模型无层级信息）并导入默认规则（APR-001/002 + 用印默认）；**不回填主管**——组织数据不完整时走人工指派，不猜审批人
  - 审批流转支持**任一人通过**（默认，同步骤其他待办自动关闭）与**会签**（全部通过才算该步完成）；驳回时其余待审记录一并关闭，已出结论的记录不改写
  - 路由失败兜底：任务置 `processing` + 记录原因（`task.data._routing`）+ 通知行政专员，绝不猜测审批人
  - 新增 65 个用例（算法 24 + 流转 4 + 归属 8 + 同步 12 + 管理端 9 + 聊天 2 + 真实 PG 集成 6）；E2E 冒烟改为**跨用户真实路由**（员工 emp999 提交 → 主管 admin001 审批）
- **数据归属与查询范围（SECURITY §4.3 / 设计 §5）**：`/tasks/my?scope=my|dept|all`——本人 / 本部门及子部门（部门主管）/ 全量（admin·finance·hr）；归属条件下推到 SQL（不做"先查全量再过滤"），`dept`/`all` 范围每次访问写审计（`action=task_scope_query`，只记范围不记单据内容）
- **组织架构上游同步（HR 为权威源，决策 D-3）**：`core/approval/sync.py` + `scripts/sync_org.py`
  - provider：`http`（HR 组织接口，约定见设计 §3.3）/ `csv`（HR 导出文件，格式样例 `scripts/sample_org/*.csv`）/ `disabled`
  - 幂等 upsert（上游 `external_id`）、全量对账软删（上游已删除的部门置 `is_active=false`，无 `external_id` 的本地部门不动）、员工调动与离职同步（本地查无此人不自动建号）
  - **失败降级**：同步失败沿用上次快照、绝不清空组织数据，连续失败达 3 次升级告警；失败计数走 Redis 且 Redis 不可用时不阻断
- **管理端与脚本维护入口（决策 D-5：首期脚本 + API，不做 UI）**：`/admin/departments`、`/admin/approval-rules`（增删查，含取值校验）、`/admin/approval-delegations`（增查）、`/admin/org/sync`；`scripts/manage_approval_rules.py`（list/add/enable/disable/delete/export/import）
- **开发环境组织种子** `scripts/seed_org_demo.py`：公司(gm001) → 技术部(admin001)，成员 admin001/emp999；`external_id` 与样例 CSV 对齐，同步演练是更新而非重复建部门；已接入 `setup_dev_env.sh`
- **LLM 数据脱敏与合规落地（评审 B-1）**：外部大模型调用改走统一出入口，实现「拦截 → 脱敏 → 调用 → 回填 → 审计」全链路
  - `core/llm_redaction.py`：按类别脱敏（手机号/邮箱/工号/姓名/金额可配）、L4 命中即中止（身份证/银行卡绝不外送）、占位符**会话内一致映射**（同一人始终同一占位符，避免多轮语义错乱）、回复占位符回填（未登记的保留不猜测）
  - `core/llm_gateway.py`：统一出入口 `LLMGateway.chat()`，含 fail-closed（脱敏异常时拒绝调用而非直发原文）、涉密业务排除（证明开具/用印默认不走外部 LLM）、调用审计（只记脱敏类别与词元用量，不记原文）
  - `core/llm.py` 工厂改返回网关；`intent`/`slot`/`orchestrator` 三处调用方接入并传递会话上下文；启动时从 `users` 表加载姓名供精确匹配
  - 配置项：`LLM_REDACTION_ENABLED`（生产 fail-fast 禁止关闭）、`LLM_AUDIT_ENABLED`、`REDACT_AMOUNT`、`LLM_EXCLUDED_BUSINESS_TYPES`、`LLM_EMPLOYEE_ID_PATTERN`
  - 真实环境验证：含手机号对话脱敏后正常完成（审计 `categories=['phone']`）；含身份证消息被拦截并回退规则路径（审计 `blocked=true, reason=id_card`）；证明开具不走外部 LLM；E2E 冒烟 9/9 无回归
- **修复应用日志泄漏用户原文**：`Orchestrator` 曾把用户消息前 50 字写入日志（违反 SECURITY §6.2「日志禁止写入 L3 明文」），改为只记长度；按 TDD 补回归用例。另新增生产禁止 `DEBUG=true` 的 fail-fast（其 SQL echo 会把含数据的 SQL 打进日志）
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
- **修复一直挂着的集成用例**：`test_health.py` 的 `/tasks/my` 集成用例因全局审计打桩把会话工厂替换成 MagicMock，被 `-m integration` 选中时必然报 `object MagicMock can't be used in 'await' expression`（默认跳过所以从未暴露）；改为自建引擎并覆盖 `get_db_session` 依赖后，集成套件 7/7
- **审批只覆盖两类业务**：此前仅 expense/seal 会发起审批，请假/物资/差旅/资产虽在场景中要求审批却「提交即完成」；
  现按场景规则全部接入（物资暂未分级），清单由配置驱动
- **审批人硬编码**：`api/chat.py` 原取「首个 admin」作为审批人（与场景文档 APR-001/002 相差一整个审批层级体系），现改为按规则路由
- **审批驳回留下悬挂待办**：驳回后其余 `pending` 记录未关闭，任务已失败却仍出现在他人的待审批列表
- **加签记录缺少步骤模式**：加签生成的新审批记录补 `mode` 与 `approver_source`，与原步骤保持一致
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
- **E2E 冒烟改为跨用户路由验证**：报销由普通员工 `emp999` 提交、部门主管 `admin001` 审批，并断言 ≤2000 元为单级审批链——原脚本用 admin001 既申请又审批，恰好掩盖了「首个管理员」的缺陷（即设计 T-3 自审场景）
- `/tasks/my` 返回新增 `scope` 字段；`/admin/*` 新增 5 个端点（全部走 `get_admin_user`）
- 测试基线：**pytest 223 passed, 17 deselected**（集成用例需显式 `-m integration`，真实 PG 上 17/17 通过）；E2E 冒烟 9/9
- **接入 DeepSeek 作为 LLM**（`OPENAI_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`）：意图识别与槽位抽取改走真实 LLM；实测发不含规则关键词的消息可识别为 `leave_request` 并追问槽位。`pytest` 95 passed、`e2e_smoke` 9/9 无回归。该 Key 可用模型为 `deepseek-flash` 与 `deepseek-v4-pro`（`deepseek-chat` 等旧名会被路由到 flash），5 条典型消息两模型均 5/5 命中，故取更快的 flash
- **RAG 方案重排**：DeepSeek 不提供 embedding API（`POST /embeddings` 返回 404），向量化不能复用它——嵌入改为二选一：另配智谱 `embedding-3` 等 OpenAI 兼容嵌入服务（零本机资产），或本地 `BAAI/bge-small-zh-v1.5`（95MB，离线可用）。待抽 `Embedder` 接口后落实
- 确认卡片 `card_data` 对齐 API 规格第 10 节：`{type, title, data, actions, warning}`
- `pytest` 默认仅运行非集成用例（`-m "not integration and not e2e and not llm"`），集成用例按需显式选择
- 修正过期的健康检查用例：认证上线后 `/chat/send` 无 Token 应返回 401

### 文档
- **全量文档按 B-2 落地状态同步（Batch 13）**：交接说明（状态/基线 192/代码地图/硬约定第 13 条/踩坑新增 4 条/待办与接手路径/提示词）、设计补丁（§11 五项决策结果 + §12 实现状态与偏离 + 场景审批覆盖现状）、评审报告（B-2 关闭 + 优先级表）、CHANGELOG、README（状态清单/脚本/环境变量/文档索引）、SECURITY §4.3（数据归属与审批链实现说明）、api-spec（`/tasks/my` 的 `scope` 参数 + 管理端 5 个新端点）、开发规范 §3.1（新增 4 条约定 + commit scope 增 `approval`）、测试计划（当前进展）、上线指南（已完成/未完成/常用运维命令 + 组织同步运维）、部署与运维（新增配置项 + §8.4 组织架构同步 + 故障处理 2 条 + 缓存策略澄清）、设计计划与里程碑／技术方案设计／前端技术方案设计（表数、审批路由与执行的关系、`skipped` 状态与 `scope` 待接）
- **补充记录一项真实的功能覆盖差距（逐场景核对发现）**：11 个场景中 6 个要求审批，但只有报销（APR-001/002）与实际走通的用印会发起审批链——请假/物资/差旅/资产仍是「提交即完成」，且用印的合同章法务审核因规则只按「业务类型 + 金额」匹配而无法分支。已写入交接说明 §7、组织架构与审批路由设计 §12 与场景 04/05/08/09/10 各自的实现状态，避免验收时误判为"已具备审批效力"
- **需求文档 V1.4（按 200 人企业级评审补需求缺口）**：新增 §3.1 角色与组织架构关系（部门树/汇报线/数据归属/审批路由/兜底原则）、§5.6 审批规则配置与知识库运营要求（责任人/更新时效/双人复核/有效期/命中率）、§6.4 LLM 数据外发约束与供应商合规、§7.5~7.6 两项风险（LLM 供应商依赖、数据出域合规）；§6.1 性能指标按 200 人基线重写并拆分为响应时间分级（纯检索 ≤1.5s / 含生成 ≤5s / 含工具 ≤10s）与峰值场景；§6.3 补运营指标（引用准确率/知识库命中率/满意度）；§2.2 前置条件补组织架构数据与 DPA；附录 B 补非功能需求编号 REQ-12~16
- **性能口径三处统一（评审 B-3 关闭）**：以需求文档 §6.1 为基准，`部署与运维.md` §8.1 容量基线改为「当前 200 人 / 扩展 1000 人」双列并补峰值场景，§8.2 补按 600 轮/日的成本代入与「合并意图+槽位调用可省约 1/3 成本」提示；`测试计划.md` §6.1 同步分级目标并补 LLM 相关建议指标
- **新增两份设计补丁**（对应评审阻断级问题，含实现清单与验收标准）：
  - `docs/architecture/LLM数据脱敏与合规设计.md`（B-1）：送出白名单（按数据类别定义可否送外部 LLM）、
    `LLMGateway` 统一出入口、脱敏规则与占位符会话内映射、回复回填、调用审计（仅记类别不记值）、
    L4 命中即拦截、涉密业务本地化、供应商 DPA 三要素、T-1~T-9 测试要点与关闭标准
  - `docs/architecture/组织架构与审批路由设计.md`（B-2）：`departments`（物化路径树）/
    `approval_rules`（金额区间×审批人类型）/ `approval_delegations`（代理审批）三表、
    审批路由算法（含自审拦截与上溯）、上游同步与失败降级、部门维度数据归属注入、
    Expand/Contract 迁移五阶段、约 7 人日的实现清单
- **新增设计评审报告** `docs/项目设计评审报告（200人企业级）.md`：从 200 人企业生产上线视角评审全部设计文档，输出阻断级问题（L3 数据进外部 LLM 缺脱敏与合规设计、组织架构与审批路由模型不足以支撑真实审批、性能口径三处不一致且与 LLM 调用次数冲突）、重要改进（知识库运营、供应商可替换性、管理后台归属、外部系统降级矩阵、会话与成本策略）、6 项优化建议与 5 处文档间不一致清单
- **全量文档按 Batch 5~8 状态同步（12 个文件）**：
  README（项目状态清单、测试基线 99、脚本清单、DeepSeek 接入示例与密钥提醒、快速开始指向一键脚本）；
  CONTRIBUTING（一键重建脚本、国内镜像、冒烟命令与提交前基线）；
  api-spec（`/chat/transfer` 补充实现说明：校验/状态变更/消息落库/通知/错误码，并标注自动转人工路径缺口）；
  Review 报告（版本与统计、实测结果表、追加 Batch 5~8 关闭项与最新开放清单）；
  完善与上线指南（模块状态表重排、P0 遗留清单更新为嵌入模型/密钥治理/lint 债）；
  设计计划与里程碑（第 5~10 周周计划状态按实际校对、向量化模块标注嵌入模型选型约束）；
  部署与运维（本地开发实录改为一键脚本优先 + 手工方式，移除旧路径 `Z:\zcode`，补备份恢复与 nodejs PATH 提示）；
  测试计划（基线 99、环境自检脚本、lint 债缺口）；开发规范（新增四条硬约定：shell 行尾 LF / MSYS 路径 / psql UTF8 / 密钥不入库）；
  前端技术方案（审批操作由「待开发」更正为已实现）；架构与需求文档（顶部加实现状态指引，避免与实现进度混淆）
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
