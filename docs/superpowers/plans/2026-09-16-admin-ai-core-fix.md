# Admin AI 核心模块修复 + 飞书登录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复核心链路（chat→orchestrator）、补漏编排器逻辑、首次 Alembic 迁移、审批多级链、知识库诚实化、接入飞书 OAuth 登录、同步文档。

**Architecture:** chat.py 调用 orchestrator.process() 获取结果，orchestrator 处理未知意图转人工，Alembic 生成全表迁移，审批按 step 检查 pending 记录，飞书 OAuth 授权码模式通过 httpx 调飞书 API。

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 async / Alembic / PostgreSQL / Redis / httpx / python-jose

## Global Constraints

- 会话存储以 PostgreSQL 为真相源，Redis 仅作 24h 缓存
- 外部审批引擎转发、/approvals/callback、Celery 轮询本轮不实现，留 TODO
- 工具的 httpx.AsyncClient 改为模块级复用实例
- 规则引擎补 _validate_meeting_room 校验器
- 飞书凭证用占位配置即可开发（测试全 mock）
- 分层依赖方向 api → services → core → db，禁止反向
- 每完成一项运行 pytest，需要数据库的测试标 @pytest.mark.integration

---

## Task 1: 把对话接口接上编排器 + 编排器构建

**Files:**
- Modify: `app/admin_ai/main.py`
- Modify: `app/admin_ai/api/chat.py`
- Modify: `app/admin_ai/api/schemas.py`
- Create: `tests/admin_ai/test_api/test_chat.py`

**Interfaces:**
- Produces: `app.state.orchestrator` (Orchestrator instance)
- Produces: `POST /chat/send` 调用 `orchestrator.process(user_message, context)`
- Produces: 所有 chat 路由挂 `get_current_user` 依赖

- [ ] **Step 1: 更新 main.py lifespan 构建完整编排链**

```python
# app/admin_ai/main.py - lifespan 函数内，在 tool_registry 和 rule_engine 之后添加：

from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.slot import SlotExtractor
from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.orchestrator import Orchestrator

# 在 lifespan 内：
intent_recognizer = IntentRecognizer()
slot_extractor = SlotExtractor()
dialog_manager = DialogManager()
orchestrator = Orchestrator(
    intent_recognizer=intent_recognizer,
    slot_extractor=slot_extractor,
    dialog_manager=dialog_manager,
    rule_engine=rule_engine,
    tool_registry=tool_registry,
)
app.state.orchestrator = orchestrator
logger.info("编排器初始化完成")
```

- [ ] **Step 2: 重写 chat.py 接入编排器**

```python
# app/admin_ai/api/chat.py

import uuid
from fastapi import APIRouter, Depends
from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import ChatRequest, ChatResponse, ConfirmRequest, TransferRequest
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.core.agent.orchestrator import AgentContext, AgentState

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("/send", response_model=ApiResponse[ChatResponse])
async def send_message(
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
    # orchestrator 从 request.app.state 获取
) -> ApiResponse[ChatResponse]:
    from fastapi import Request
    # 通过 Depends 注入 request 获取 app.state
    # 实际实现中用 request: Request 参数
    ...
```

完整实现：
- `/chat/send`: 从 `request.app.state.orchestrator` 获取编排器，构建 `AgentContext(user_id, conversation_id)`，调用 `orchestrator.process(message, context)`，将返回的 `content/card_data/requires_action` 包装到 `ChatResponse`
- `/chat/history/{conversation_id}`: 挂 `get_current_user`，从数据库查询会话历史
- `/chat/confirm/{task_id}`: 挂 `get_current_user`，根据 `confirmed` 标志驱动编排器继续执行或取消
- `/chat/transfer/{conversation_id}`: 挂 `get_current_user`

- [ ] **Step 3: 编写测试 test_chat.py**

```python
# tests/admin_ai/test_api/test_chat.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

@pytest.fixture
def mock_orchestrator():
    orch = AsyncMock()
    orch.process.return_value = {"content": "请问您要请什么假？", "requires_action": True}
    return orch

@pytest.fixture
def auth_headers():
    from app.admin_ai.core.auth.jwt_token import create_access_token
    token = create_access_token({"sub": "user1", "employee_id": "EMP001", "role": "employee"})
    return {"Authorization": f"Bearer {token}"}

def test_send_message_no_token_returns_401(client):
    """无 Token 访问 /chat/send 返回 401"""
    response = client.post("/api/v1/chat/send", json={"message": "你好"})
    assert response.status_code == 200  # BusinessError 被 handler 转为 401
    data = response.json()
    assert data["code"] == 40002

def test_send_message_with_token(client, auth_headers, mock_orchestrator):
    """有 Token 可正常发送消息"""
    client.app.state.orchestrator = mock_orchestrator
    response = client.post(
        "/api/v1/chat/send",
        json={"message": "你好"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "conversation_id" in data["data"]
```

- [ ] **Step 4: 运行测试验证**

Run: `pytest tests/admin_ai/test_api/test_chat.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/admin_ai/main.py app/admin_ai/api/chat.py tests/admin_ai/test_api/test_chat.py
git commit -m "feat: 对话接口接上编排器，所有 chat 路由加认证"
```

---

## Task 2: 编排器逻辑补漏

**Files:**
- Modify: `app/admin_ai/core/agent/orchestrator.py`
- Modify: `app/admin_ai/core/rules/engine.py`
- Create: `tests/admin_ai/test_core/test_orchestrator.py`

**Interfaces:**
- `process()` 未知意图走转人工分支
- `context.confirmed=True` 且 `business_type` 存在时跳过意图识别
- 工具报错转人工时创建 PENDING 状态 TaskModel

- [ ] **Step 1: 修改 orchestrator.py 处理未知意图**

在 `process()` 方法中，意图识别后添加：
```python
# 未知意图走转人工
if context.intent == "other" or (
    context.business_type is None and context.intent not in ("greeting", "policy_query", "status_query")
):
    context.state = AgentState.TRANSFERRED
    return {
        "content": "抱歉，我暂时无法理解您的需求，正在为您转接人工客服。",
        "transfer_to_human": True,
    }
```

- [ ] **Step 2: 确认恢复路径**

在 `process()` 方法开头，意图识别之前添加：
```python
# 确认恢复：跳过意图识别直接从工具执行继续
if context.confirmed and context.business_type:
    context.state = AgentState.EXECUTING
    tool = self.tool_registry.get_tool(context.business_type)
    if tool:
        result = await tool.execute(context.slots, context.user_id)
        context.tool_calls.append({
            "tool": context.business_type,
            "input": context.slots,
            "output": result.content,
        })
        if result.is_error:
            context.state = AgentState.TRANSFERRED
            return {
                "content": f"系统暂时无法完成您的请求，已为您转接人工客服。错误：{result.content}",
                "transfer_to_human": True,
            }
    context.state = AgentState.COMPLETED
    return {
        "content": "操作已完成",
        "task_type": context.business_type,
        "slots": context.slots,
    }
```

- [ ] **Step 3: 工具报错转人工时创建 TaskModel**

修改 orchestrator 接收 db_session 参数（或通过回调），在工具报错时：
```python
# 工具报错时创建 PENDING 转人工任务
from app.admin_ai.db.models import TaskModel, TaskStatus, TaskType
task = TaskModel(
    user_id=context.user_id,
    conversation_id=context.conversation_id,
    type=TaskType(context.business_type) if context.business_type else TaskType.MATERIAL,
    status=TaskStatus.PENDING,
    title=f"转人工-{context.business_type}",
    data=context.slots,
    risk_level=context.risk_level,
)
# db.add(task) 需要 db session
```

注意：orchestrator 目前不持有 db session。方案：在 `process()` 参数中增加可选 `db_session`，或在返回结果中携带 `transfer_task_data` 由调用方创建。选择后者更解耦。

- [ ] **Step 4: 规则引擎补 _validate_meeting_room**

```python
# app/admin_ai/core/rules/engine.py - 在 validators dict 中添加 "meeting_room": self._validate_meeting_room

async def _validate_meeting_room(
    self, slots: dict[str, Any], user_id: str, result: ValidationResult
) -> None:
    """校验会议室预定规则。"""
    start_time = slots.get("start_time")
    end_time = slots.get("end_time")

    if not start_time or not end_time:
        result.errors.append("开始时间和结束时间为必填项")
        result.passed = False
        return

    try:
        from datetime import datetime as dt
        start = dt.fromisoformat(str(start_time))
        end = dt.fromisoformat(str(end_time))
        duration_hours = (end - start).total_seconds() / 3600

        if duration_hours <= 0:
            result.errors.append("结束时间必须晚于开始时间")
            result.passed = False
            return

        if duration_hours > 8:
            result.errors.append("会议室预定时长不能超过8小时")
            result.passed = False
            return

        if start.date() != end.date():
            result.errors.append("会议室预定必须在同一天内")
            result.passed = False
    except (ValueError, TypeError):
        result.errors.append("时间格式错误")
        result.passed = False
```

- [ ] **Step 5: 编写测试**

```python
# tests/admin_ai/test_core/test_orchestrator.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.admin_ai.core.agent.orchestrator import Orchestrator, AgentContext, AgentState

@pytest.fixture
def orchestrator():
    return Orchestrator(
        intent_recognizer=AsyncMock(),
        slot_extractor=AsyncMock(),
        dialog_manager=AsyncMock(),
        rule_engine=AsyncMock(),
        tool_registry=MagicMock(),
    )

@pytest.mark.asyncio
async def test_unknown_intent_transfers_to_human(orchestrator):
    """未知意图走转人工分支"""
    orchestrator.intent_recognizer.recognize.return_value = {"intent": "other", "confidence": 0.5}
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("一些随机文本", context)
    assert result.get("transfer_to_human") is True
    assert context.state == AgentState.TRANSFERRED

@pytest.mark.asyncio
async def test_confirmed_resumes_execution(orchestrator):
    """确认恢复路径：跳过意图识别直接执行工具"""
    mock_tool = AsyncMock()
    mock_tool.execute.return_value = MagicMock(content=[{"type": "text", "text": "ok"}], is_error=False)
    orchestrator.tool_registry.get_tool.return_value = mock_tool

    context = AgentContext(
        user_id="u1", conversation_id="c1",
        confirmed=True, business_type="leave",
        slots={"leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )
    result = await orchestrator.process("", context)
    assert context.state == AgentState.COMPLETED
    assert "操作已完成" in result["content"]
```

- [ ] **Step 6: 运行测试**

Run: `pytest tests/admin_ai/test_core/test_orchestrator.py -v`

- [ ] **Step 7: Commit**

```bash
git add app/admin_ai/core/agent/orchestrator.py app/admin_ai/core/rules/engine.py tests/admin_ai/test_core/test_orchestrator.py
git commit -m "feat: 编排器逻辑补漏-未知意图转人工、确认恢复、会议室校验"
```

---

## Task 3: Alembic 首次迁移

**Files:**
- Create: `migrations/versions/001_initial_tables.py`
- Modify: `app/admin_ai/db/models.py` (如需添加 open_id 字段)

**Interfaces:**
- 包含 users/conversations/messages/tasks/approvals/audit_logs/knowledge_docs 全部表

- [ ] **Step 1: 检查 models.py 是否需要补充字段**

飞书登录需要 `open_id` 字段，在 UserModel 中添加：
```python
open_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
```

知识库需要 `content` 字段，在 KnowledgeDocModel 中添加：
```python
content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: 生成迁移**

```bash
alembic revision --autogenerate -m "initial_tables"
```

- [ ] **Step 3: 检查生成的迁移文件**

确认包含所有表：users, conversations, messages, tasks, approvals, audit_logs, knowledge_docs

- [ ] **Step 4: 运行迁移**

```bash
alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
git add app/admin_ai/db/models.py migrations/versions/
git commit -m "feat: Alembic 首次迁移-全表创建"
```

---

## Task 4: 审批多级链修复

**Files:**
- Modify: `app/admin_ai/api/task.py`
- Create: `tests/admin_ai/test_api/test_task.py`

**Interfaces:**
- `payload.action` 只能是 approve/reject/add_sign，非法值返回 40001
- 校验任务状态必须为 APPROVING
- approve 后按 step 检查是否还有下一步 pending 的 ApprovalModel
- 实现 add_sign：插入新的 pending ApprovalModel 记录

- [ ] **Step 1: 修改 approve_task 实现**

```python
@router.post("/{task_id}/approve", response_model=ApiResponse[dict])
async def approve_task(
    task_id: str,
    payload: ApprovalRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    # 校验 action
    valid_actions = {"approve", "reject", "add_sign"}
    if payload.action not in valid_actions:
        raise BusinessError(code=40001, message=f"非法操作: {payload.action}，仅支持 {valid_actions}")

    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise BusinessError(code=40004, message="任务不存在")

    # 校验任务状态
    if task.status != TaskStatus.APPROVING:
        raise BusinessError(code=40001, message=f"任务状态为 {task.status.value}，无法审批")

    # 查找当前审批人待审批记录
    approval_result = await db.execute(
        select(ApprovalModel).where(
            ApprovalModel.task_id == task_id,
            ApprovalModel.approver_id == current_user["user_id"],
            ApprovalModel.status == "pending",
        )
    )
    approval = approval_result.scalar_one_or_none()
    if not approval:
        raise BusinessError(code=40003, message="您不是当前审批人")

    if payload.action == "add_sign":
        # 加签：插入新的 pending ApprovalModel
        if not payload.add_sign_user_id:
            raise BusinessError(code=40001, message="加签必须指定 add_sign_user_id")
        new_approval = ApprovalModel(
            task_id=task_id,
            approver_id=payload.add_sign_user_id,
            step=approval.step + 1,
            status="pending",
        )
        db.add(new_approval)
        await db.commit()
        return ApiResponse(data={
            "id": task_id,
            "action": "add_sign",
            "status": task.status.value,
            "new_approver_id": payload.add_sign_user_id,
        })

    # 更新审批状态
    approval.action = ApprovalAction(payload.action)
    approval.status = payload.action
    approval.comment = payload.comment
    approval.decided_at = datetime.now(timezone.utc)

    if payload.action == "reject":
        task.status = TaskStatus.FAILED
    elif payload.action == "approve":
        # 检查是否还有下一步 pending 的审批
        next_pending = await db.execute(
            select(ApprovalModel).where(
                ApprovalModel.task_id == task_id,
                ApprovalModel.status == "pending",
                ApprovalModel.id != approval.id,
            )
        )
        if next_pending.scalar_one_or_none():
            # 还有下一步审批，保持 APPROVING
            pass
        else:
            # 所有审批完成
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return ApiResponse(data={
        "id": task_id,
        "action": payload.action,
        "status": task.status.value,
    })
```

- [ ] **Step 2: timeline 接口补 ownership 检查**

```python
# 在 get_task_timeline 中，查询到 task 后添加：
if task.user_id != current_user["user_id"]:
    raise BusinessError(code=40003, message="无权访问该任务")
```

- [ ] **Step 3: 编写测试**

```python
# tests/admin_ai/test_api/test_task.py

def test_approve_invalid_action_returns_40001(client, auth_headers):
    """非法 action 返回 40001"""
    response = client.post(
        "/api/v1/tasks/fake-id/approve",
        json={"action": "invalid_action"},
        headers=auth_headers,
    )
    assert response.json()["code"] == 40001

def test_approve_task_not_approving_returns_40001(client, auth_headers):
    """非 APPROVING 状态任务无法审批"""
    # 需要先创建一个 PENDING 状态的任务
    ...
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/admin_ai/test_api/test_task.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/admin_ai/api/task.py tests/admin_ai/test_api/test_task.py
git commit -m "feat: 审批多级链修复-校验action/状态、多步审批、加签、timeline ownership"
```

---

## Task 5: 知识库接口诚实化

**Files:**
- Modify: `app/admin_ai/api/knowledge.py`
- Modify: `app/admin_ai/db/models.py` (已在 Task 3 添加 content 字段)

**Interfaces:**
- upload 返回 `status: "pending_index"` 而非 "indexed"
- search 基于 title/tags/content 做 ILIKE 关键词匹配

- [ ] **Step 1: 修改 upload 接口**

```python
@router.post("/upload", response_model=ApiResponse[dict])
async def upload_knowledge(
    request: KnowledgeUploadRequest,
    current_user: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    doc = KnowledgeDocModel(
        title=request.title,
        category=request.category,
        tags=request.tags,
        content=request.content,
        created_by=current_user.get("user_id"),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return ApiResponse(data={
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "status": "pending_index",
    })
```

- [ ] **Step 2: 修改 search 接口**

```python
@router.post("/search", response_model=ApiResponse[dict])
async def search_knowledge(
    request: KnowledgeSearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    # TODO: 接入 RAG 向量检索，当前使用 ILIKE 关键词匹配作为占位
    query = select(KnowledgeDocModel).where(KnowledgeDocModel.is_active == True)

    if request.query:
        search_pattern = f"%{request.query}%"
        query = query.where(
            KnowledgeDocModel.title.ilike(search_pattern)
            | KnowledgeDocModel.content.ilike(search_pattern)
        )

    if request.category:
        query = query.where(KnowledgeDocModel.category == request.category)

    query = query.limit(request.top_k)
    result = await db.execute(query)
    docs = result.scalars().all()

    # 过滤 tags 匹配
    filtered = []
    for d in docs:
        if request.query and request.query not in (d.title or "") and request.query not in (d.content or ""):
            if d.tags and request.query in d.tags:
                filtered.append(d)
        else:
            filtered.append(d)

    return ApiResponse(data={
        "query": request.query,
        "results": [
            {
                "id": d.id,
                "title": d.title,
                "category": d.category,
                "tags": d.tags,
            }
            for d in filtered
        ],
        "total": len(filtered),
    })
```

- [ ] **Step 3: Commit**

```bash
git add app/admin_ai/api/knowledge.py
git commit -m "feat: 知识库接口诚实化-upload返回pending_index、search用ILIKE占位"
```

---

## Task 6: 认证改造 - 接入飞书登录

**Files:**
- Create: `app/admin_ai/core/auth/sso.py`
- Modify: `app/admin_ai/api/auth.py`
- Modify: `app/admin_ai/config.py`
- Modify: `.env.example`
- Create: `scripts/seed_admin.py`
- Create: `tests/admin_ai/test_api/test_auth.py`

**Interfaces:**
- `GET /auth/feishu/login-url` → 返回授权跳转地址
- `GET /auth/feishu/callback?code=xxx&state=xxx` → 换 token + 拉用户 + upsert + 签发 JWT
- `GET /auth/dev-login?employee_id=xxx` → 仅 development 环境
- `GET /auth/me` → 保留
- 删除 `/auth/login`、`/auth/refresh`

- [ ] **Step 1: config.py 添加飞书配置项**

```python
# 在 Settings 类中添加：
FEISHU_APP_ID: str = ""
FEISHU_APP_SECRET: str = ""
FEISHU_REDIRECT_URI: str = ""

@model_validator(mode="after")
def _check_secrets(self) -> Settings:
    if self.ENVIRONMENT is Environment.PRODUCTION:
        # ... 现有校验 ...
        if not self.FEISHU_APP_ID:
            raise ValueError("生产环境必须配置 FEISHU_APP_ID")
        if not self.FEISHU_APP_SECRET:
            raise ValueError("生产环境必须配置 FEISHU_APP_SECRET")
        if not self.FEISHU_REDIRECT_URI:
            raise ValueError("生产环境必须配置 FEISHU_REDIRECT_URI")
    return self
```

- [ ] **Step 2: .env.example 添加飞书配置**

```
# ============ 飞书 OAuth 配置 ============
FEISHU_APP_ID=your-feishu-app-id
FEISHU_APP_SECRET=your-feishu-app-secret
FEISHU_REDIRECT_URI=http://localhost:8000/api/v1/auth/feishu/callback
```

- [ ] **Step 3: 创建 sso.py 飞书 OAuth 模块**

```python
# app/admin_ai/core/auth/sso.py

import secrets
from typing import Any
import httpx
import structlog
from app.admin_ai.config import get_config

logger = structlog.get_logger(__name__)

FEISHU_AUTH_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def generate_login_url(state: str) -> str:
    """生成飞书授权跳转地址。"""
    config = get_config()
    return (
        f"{FEISHU_AUTH_URL}"
        f"?app_id={config.FEISHU_APP_ID}"
        f"&redirect_uri={config.FEISHU_REDIRECT_URI}"
        f"&state={state}"
    )


def generate_state() -> str:
    """生成随机 state 用于 CSRF 防护。"""
    return secrets.token_urlsafe(32)


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """用授权码换取 user_access_token。"""
    config = get_config()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            FEISHU_TOKEN_URL,
            json={
                "app_id": config.FEISHU_APP_ID,
                "app_secret": config.FEISHU_APP_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"飞书换取 token 失败: {data.get('msg')}")
        return data.get("data", {})


async def get_user_info(user_access_token: str) -> dict[str, Any]:
    """用 user_access_token 获取用户信息。"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            FEISHU_USER_INFO_URL,
            headers={"Authorization": f"Bearer {user_access_token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"飞书获取用户信息失败: {data.get('msg')}")
        return data.get("data", {})
```

- [ ] **Step 4: 重写 auth.py**

```python
# app/admin_ai/api/auth.py

import uuid
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import TokenResponse
from app.admin_ai.config import get_config, Environment
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.auth.sso import generate_login_url, generate_state, exchange_code_for_token, get_user_info
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import UserModel

router = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/feishu/login-url", response_model=ApiResponse[dict])
async def feishu_login_url(request: Request) -> ApiResponse[dict]:
    """生成飞书授权跳转地址。"""
    import redis.asyncio as redis
    config = get_config()
    state = generate_state()
    # 将 state 存入 Redis，5 分钟有效
    try:
        redis_client = redis.from_url(config.REDIS_URL)
        await redis_client.set(f"feishu_state:{state}", "1", ex=300)
        await redis_client.close()
    except Exception:
        pass  # Redis 不可用时仍返回 state（开发环境）
    url = generate_login_url(state)
    return ApiResponse(data={"login_url": url, "state": state})


@router.get("/feishu/callback", response_model=ApiResponse[TokenResponse])
async def feishu_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TokenResponse]:
    """飞书 OAuth 回调。"""
    import redis.asyncio as redis
    config = get_config()

    # 1. 校验 state
    try:
        redis_client = redis.from_url(config.REDIS_URL)
        stored = await redis_client.get(f"feishu_state:{state}")
        await redis_client.delete(f"feishu_state:{state}")
        await redis_client.close()
        if not stored:
            raise BusinessError(code=40001, message="无效的 state 参数")
    except BusinessError:
        raise
    except Exception:
        pass  # Redis 不可用时跳过校验（开发环境）

    # 2. 换取 token
    try:
        token_data = await exchange_code_for_token(code)
    except Exception as e:
        raise BusinessError(code=50002, message=f"换取飞书 token 失败: {e}")

    user_access_token = token_data.get("access_token")
    if not user_access_token:
        raise BusinessError(code=50002, message="飞书未返回 access_token")

    # 3. 获取用户信息
    try:
        user_info = await get_user_info(user_access_token)
    except Exception as e:
        raise BusinessError(code=50002, message=f"获取飞书用户信息失败: {e}")

    open_id = user_info.get("open_id")
    name = user_info.get("name", "未知用户")
    employee_number = user_info.get("employee_number", open_id)

    if not open_id:
        raise BusinessError(code=50002, message="飞书未返回 open_id")

    # 4. upsert 本地 users 表
    result = await db.execute(select(UserModel).where(UserModel.open_id == open_id))
    user = result.scalar_one_or_none()
    if not user:
        user = UserModel(
            employee_id=employee_number,
            name=name,
            open_id=open_id,
            role="employee",
        )
        db.add(user)
        await db.flush()

    # 5. 签发本地 JWT
    jwt_token = create_access_token(data={
        "sub": user.id,
        "employee_id": user.employee_id,
        "role": user.role,
    })

    return ApiResponse(data=TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        expires_in=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ))


@router.get("/dev-login", response_model=ApiResponse[TokenResponse])
async def dev_login(
    employee_id: str = Query("admin001"),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TokenResponse]:
    """开发环境登录（仅 development 可用）。"""
    config = get_config()
    if config.ENVIRONMENT != Environment.DEVELOPMENT:
        raise BusinessError(code=40003, message="dev-login 仅开发环境可用")

    # 查询或创建用户
    result = await db.execute(select(UserModel).where(UserModel.employee_id == employee_id))
    user = result.scalar_one_or_none()
    if not user:
        user = UserModel(
            employee_id=employee_id,
            name=f"开发用户-{employee_id}",
            role="admin" if employee_id == "admin001" else "employee",
        )
        db.add(user)
        await db.flush()

    token = create_access_token(data={
        "sub": user.id,
        "employee_id": user.employee_id,
        "role": user.role,
    })
    return ApiResponse(data=TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ))


@router.get("/me", response_model=ApiResponse[dict])
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[dict]:
    """获取当前登录用户信息。"""
    return ApiResponse(data=current_user)
```

- [ ] **Step 5: 创建 scripts/seed_admin.py**

```python
# scripts/seed_admin.py

"""插入 admin 测试账号。"""

import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.admin_ai.db.database import get_session_factory
from app.admin_ai.db.models import UserModel


async def seed():
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(UserModel).where(UserModel.employee_id == "admin001")
        )
        if result.scalar_one_or_none():
            print("admin001 已存在，跳过")
            return
        user = UserModel(
            employee_id="admin001",
            name="管理员",
            role="admin",
        )
        db.add(user)
        await db.commit()
        print("admin001 创建成功")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 6: routes.py 确保 auth router 正确注册**

检查 `app/admin_ai/api/routes.py` 中 `auth.router` 已正确引入。

- [ ] **Step 7: 编写测试**

```python
# tests/admin_ai/test_api/test_auth.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

def test_dev_login_works_in_development(client):
    """dev-login 在开发环境可用"""
    response = client.get("/api/v1/auth/dev-login?employee_id=test001")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "access_token" in data["data"]

def test_feishu_callback_full_flow(client):
    """飞书回调全链路（mock）"""
    with patch("app.admin_ai.core.auth.sso.exchange_code_for_token") as mock_exchange, \
         patch("app.admin_ai.core.auth.sso.get_user_info") as mock_user_info:
        mock_exchange.return_value = {"access_token": "test_token"}
        mock_user_info.return_value = {
            "open_id": "ou_test123",
            "name": "测试用户",
            "employee_number": "EMP999",
        }
        # 需要先设置 state 到 Redis（或跳过校验）
        response = client.get("/api/v1/auth/feishu/callback?code=test_code&state=test_state")
        # 在 Redis 不可用时可能跳过校验
        assert response.status_code == 200

def test_no_token_returns_401():
    """无 Token 访问 /chat/send 返回 401"""
    from app.admin_ai.main import create_app
    app = create_app()
    client = TestClient(app)
    response = client.post("/api/v1/chat/send", json={"message": "你好"})
    assert response.json()["code"] == 40002
```

- [ ] **Step 8: 运行测试**

Run: `pytest tests/admin_ai/test_api/test_auth.py -v`

- [ ] **Step 9: Commit**

```bash
git add app/admin_ai/core/auth/sso.py app/admin_ai/api/auth.py app/admin_ai/config.py .env.example scripts/seed_admin.py tests/admin_ai/test_api/test_auth.py
git commit -m "feat: 接入飞书OAuth登录、dev-login、删除旧login/refresh"
```

---

## Task 7: 文档同步

**Files:**
- Modify: `docs/行政智能系统需求文档.md`
- Modify: `docs/api/api-spec.md`
- Modify: `docs/architecture/行政智能系统-技术方案设计.md`
- Modify: `docs/guides/部署与运维.md`
- Modify: `docs/guides/测试计划.md`

- [ ] **Step 1: 需求文档 - 2.2 前置条件**

将"员工需通过企业身份认证登录系统"改为"员工需通过飞书授权登录系统"。

- [ ] **Step 2: 需求文档 - 6.4 认证方式**

改为"通过飞书授权登录（企业 SSO）"。

- [ ] **Step 3: 需求文档 - 版本号 +1**

版本从 V1.2 → V1.3，更新修订记录。

- [ ] **Step 4: api-spec.md - 认证接口组替换**

删除 `/auth/login`、`/auth/refresh`，添加：
- `GET /auth/feishu/login-url`
- `GET /auth/feishu/callback`
- `GET /auth/dev-login`（注明仅 development）
- `GET /auth/me`

补全请求/响应/错误码示例。

- [ ] **Step 5: api-spec.md - 版本号 +1**

版本从 V1.2 → V1.3。

- [ ] **Step 6: 技术方案设计 - 认证模块补飞书 OAuth 时序图**

添加浏览器→授权页→回调→换token→拉用户→upsert→签发本地JWT 时序图。

- [ ] **Step 7: 技术方案设计 - §8 认证接口清单同步**

- [ ] **Step 8: 技术方案设计 - 配置项表补 FEISHU_* 三项**

- [ ] **Step 9: 技术方案设计 - 版本号 +1**

版本从 V1.3 → V1.4。

- [ ] **Step 10: 部署与运维 - 配置管理补飞书配置项**

补三个飞书配置项及生产非空校验说明。

- [ ] **Step 11: 测试计划 - 认证用例改为飞书回调链路**

改为飞书回调链路（mock），保留"无 Token 返回 401"用例。

- [ ] **Step 12: Commit**

```bash
git add docs/
git commit -m "docs: 文档同步-认证方案改为飞书登录"
```

---

## Verification Checklist

- [ ] `python --version` 为 3.11+
- [ ] `pytest` 全部通过
- [ ] 新增测试：未知意图转人工、多级审批两步链、无 Token 访问 /chat/send 返回 401
- [ ] 分层依赖方向 api → services → core → db，无反向
- [ ] alembic upgrade head 通过
- [ ] 每项独立 commit