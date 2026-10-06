# Batch 1 核心链路打通 Implementation Plan

> **历史归档（2026-10-06 整理）**：保留原始方案、评审和交接记录供追溯。文中的机器路径、服务运行状态、测试结果、预算与进度只代表记录当时；提交号来自历史重写前，可能无法在当前仓库解析。后续开发请以 [文档导航](../../README.md)、[当前状态](../../guides/当前状态.md) 和 [开发计划](../../planning/开发计划.md) 为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让"对话 → 多轮补全 → 规则校验 → 高风险确认 → 工具执行"这条主链路真正可用：接入真实 LLM、持久化会话状态、修复前后端确认与登录链路。

**Architecture:** 后端引入两个可替换边界——（1）LLM 客户端工厂，无密钥/无依赖时降级为规则回退；（2）`ConversationStateStore`（内存 / Redis 双实现），按 `conversation_id` 保存 intent/business_type/slots/awaiting_slots/pending_confirmation。`/chat/send` 与 `/chat/confirm` 从 store 读写状态，编排器据此支持槽位续填与确认恢复。前端改成"先落 token 再取用户信息"，卡片字段对齐 API 规格第 10 节。

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic v2 / SQLAlchemy 2 async / pytest-asyncio；前端 React 19 + TypeScript + Zustand + axios。

## Global Constraints

- Python `>=3.11`；类型注解完整（mypy `disallow_untyped_defs=true`）。
- 统一响应信封 `{code, message, data}`；错误码沿用 `api/response.py` 的 `ERROR_TO_HTTP`。
- 先写失败测试，再写最小实现，最后重构；每个任务独立可测。
- 可选依赖（openai / redis）必须惰性导入，缺失时优雅降级，不得在模块顶层 import。
- 卡片结构须符合 `docs/api/api-spec.md` 第 10 节：`{type, title, data, actions, warning}`。

---

### Task 1: LLM 客户端工厂 + 注入意图/槽位

**Files:**
- Create: `app/admin_ai/core/llm.py`
- Modify: `app/admin_ai/core/agent/intent.py`
- Modify: `app/admin_ai/core/agent/slot.py`
- Modify: `app/admin_ai/main.py`
- Test: `tests/admin_ai/test_core/test_llm.py`, `tests/admin_ai/test_core/test_slot.py`

**Interfaces:**
- Produces: `build_llm_client(config: Settings) -> Any | None`；`IntentRecognizer(llm_client=None, model="gpt-4o-mini")`；`SlotExtractor(llm_client=None, model="gpt-4o-mini")`。
- `SlotExtractor.extract(...)` 在 LLM 可用时真正抽取并合并；LLM 失败或未配置时回退 `_fallback_extract`。

- [ ] Step 1: 写失败测试 `test_llm.py`：无 KEY 返回 None；注入 stub `openai` 且有 KEY 时返回实例。
- [ ] Step 2: 运行确认 FAIL（模块不存在）。
- [ ] Step 3: 实现 `core/llm.py`（惰性 import）。
- [ ] Step 4: 运行确认 PASS。
- [ ] Step 5: 失败测试：`SlotExtractor(llm_client=mock_llm).extract(...)` 返回 LLM 抽到的 slots；回退模式能抽 leave_type/数量/金额。
- [ ] Step 6: 实现 `_llm_extract`，修复现在"有 LLM 就原样返回"的 bug。
- [ ] Step 7: `main.py` 用 `build_llm_client(config)` 注入两个模块，模型取 `config.LLM_MODEL`。
- [ ] Step 8: 全量测试 + commit。

### Task 2: 会话状态存储

**Files:**
- Create: `app/admin_ai/core/agent/state_store.py`
- Test: `tests/admin_ai/test_core/test_state_store.py`

**Interfaces:**
- Produces: `@dataclass ConversationState(intent, business_type, slots, awaiting_slots, pending_confirmation)` + `to_dict()/from_dict()`。
- `InMemoryConversationStateStore.get/save/clear`；`RedisConversationStateStore(client, ttl=86400, prefix="conversation_state:")`。
- `build_state_store(redis_url, ttl=86400) -> ConversationStateStore`；`get_default_state_store()` 模块级单例（测试兜底）。

- [ ] Step 1: 失败测试：存取往返、未知 id 返回 None、clear 生效、可 JSON 序列化。
- [ ] Step 2: 运行确认 FAIL。
- [ ] Step 3: 实现（redis 惰性 import，失败回退内存）。
- [ ] Step 4: 运行确认 PASS，commit。

### Task 3: 编排器支持槽位续填

**Files:**
- Modify: `app/admin_ai/core/agent/orchestrator.py`
- Test: `tests/admin_ai/test_core/test_orchestrator.py`

**Interfaces:**
- `AgentContext` 新增 `awaiting_slots: bool = False`。
- 行为：当 `context.business_type and context.awaiting_slots` 时跳过意图识别直接续填；缺槽位时置 `awaiting_slots=True`；补齐后置 False；确认卡片改为 spec 字段。

- [ ] Step 1: 失败测试：续填时不调用 `intent_recognizer.recognize`，且最终执行工具。
- [ ] Step 2: 失败测试：缺槽位返回 `requires_action` 且 `context.awaiting_slots is True`。
- [ ] Step 3: 失败测试：确认卡片含 `type/title/data/actions` 且 `data == slots`。
- [ ] Step 4: 运行确认 FAIL。
- [ ] Step 5: 实现；运行 PASS，commit。

### Task 4: /chat/send 接入会话状态

**Files:**
- Modify: `app/admin_ai/api/chat.py`
- Test: `tests/admin_ai/test_api/test_chat.py`

**Interfaces:**
- 从 `request.app.state.state_store`（缺失时 `get_default_state_store()`）读取并写回 `ConversationState`。

- [ ] Step 1: 失败测试（真实编排器）：同一 conversation_id 先"我要请假"，再"年假 2026-09-20 到 2026-09-21"，第二次应执行工具且不转人工。
- [ ] Step 2: 运行确认 FAIL。
- [ ] Step 3: 实现读写状态。
- [ ] Step 4: 运行 PASS，commit。

### Task 5: 高风险确认持久化与恢复

**Files:**
- Modify: `app/admin_ai/api/chat.py`
- Test: `tests/admin_ai/test_api/test_chat.py`

**Interfaces:**
- `/chat/confirm/{conversation_id}`：从 store 取 `pending_confirmation`，用保存的 `business_type/slots` 构造 `AgentContext(confirmed=...)` 调 `process`；确认后清 pending，取消则返回"已取消"。

- [ ] Step 1: 失败测试：高风险发送后状态含 `pending_confirmation`；confirm(true) 时编排器收到 `confirmed=True` 且 slots 完整；confirm(false) 不执行工具。
- [ ] Step 2: 运行确认 FAIL。
- [ ] Step 3: 实现；运行 PASS，commit。

### Task 6: 前端登录顺序与卡片字段

**Files:**
- Modify: `frontend/src/pages/callback/index.tsx`
- Modify: `frontend/src/pages/chat/ConfirmCard.tsx`
- Modify: `frontend/src/pages/chat/index.tsx`

- [ ] Step 1: callback 先 `login(token, 占位)` 再 `getMe()` 覆盖；取用户信息失败不影响已登录。
- [ ] Step 2: ConfirmCard 读 `cardData.title/data/actions`（spec 第 10 节）。
- [ ] Step 3: handleConfirm 无 conversationId 时直接返回。
- [ ] Step 4: `pnpm -C frontend build` 通过。

### Task 7: 测试回归与过期用例修正

**Files:**
- Modify: `tests/admin_ai/test_api/test_health.py`
- Modify: `pyproject.toml`

- [ ] Step 1: `test_chat_send_endpoint` 改为断言 401（认证已上线）。
- [ ] Step 2: 默认 addopts 排除 integration/e2e/llm 标记。
- [ ] Step 3: `python -m pytest tests/admin_ai -q` 全绿；前端 build 通过。
