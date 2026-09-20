# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务/审批接口测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import ApprovalAction, ApprovalModel, TaskModel, TaskStatus
from app.admin_ai.main import create_app


def _make_auth_headers(user_id: str = "user1") -> dict[str, str]:
    token = create_access_token({"sub": user_id, "employee_id": "EMP001", "role": "employee"})
    return {"Authorization": f"Bearer {token}"}


def _make_task(task_id: str, user_id: str = "user1", status: TaskStatus = TaskStatus.APPROVING) -> MagicMock:
    task = MagicMock(spec=TaskModel)
    task.id = task_id
    task.user_id = user_id
    task.status = status
    task.type = MagicMock(value="leave")
    task.title = "测试任务"
    task.risk_level = "low"
    task.created_at = datetime.now(timezone.utc)
    task.completed_at = None
    task.data = {}
    task.external_id = None
    return task


def _make_approval(
    approval_id: str,
    task_id: str,
    approver_id: str,
    step: int = 1,
    status: str = "pending",
    mode: str = "any_one",
) -> MagicMock:
    approval = MagicMock(spec=ApprovalModel)
    approval.id = approval_id
    approval.task_id = task_id
    approval.approver_id = approver_id
    approval.step = step
    approval.status = status
    approval.mode = mode
    approval.action = None
    approval.comment = None
    approval.created_at = datetime.now(timezone.utc)
    approval.decided_at = None
    return approval


class _MockScalarOneOrNone:
    """模拟 SQLAlchemy scalar_one_or_none 结果。"""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _MockScalars:
    """模拟 SQLAlchemy scalars().all() 结果。"""

    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


def _make_mock_db(task=None, approval=None, other_pending=None, extra_results=None):
    """创建 mock AsyncSession，按调用顺序返回不同结果。

    `other_pending` 为同任务其他待审记录（单条或列表），用于审批流转判断
    「任一人通过则同步骤其他待办关闭」与「是否已全部审完」。
    """
    db = AsyncMock()

    if other_pending is None:
        pending_rows: list[Any] = []
    elif isinstance(other_pending, list):
        pending_rows = other_pending
    else:
        pending_rows = [other_pending]

    results = []
    # 第1次 execute: 查 task
    results.append(_MockScalarOneOrNone(task))
    # 第2次 execute: 查 approval (pending)
    results.append(_MockScalarOneOrNone(approval))
    # 第3次 execute: 查该任务其他待审记录
    results.append(_MockScalars(pending_rows))
    results.extend(extra_results or [])

    db.execute = AsyncMock(side_effect=results)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


async def test_approve_invalid_action() -> None:
    """非法 action 返回 40001。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id)
    approval = _make_approval("a1", task_id, "user1")
    db = _make_mock_db(task=task, approval=approval)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "invalid_action"},
            headers=headers,
        )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 40001
    app.dependency_overrides.clear()


async def test_approve_task_not_approving() -> None:
    """非 APPROVING 状态任务无法审批。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.PENDING)
    db = _make_mock_db(task=task)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "approve"},
            headers=headers,
        )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 40001
    app.dependency_overrides.clear()


async def test_approve_multi_step() -> None:
    """两个审批人，审批第一个 → 任务状态保持 APPROVING。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1)
    # 还有另一个 pending 审批
    other_pending = _make_approval("a2", task_id, "user2", step=2)
    db = _make_mock_db(task=task, approval=approval, other_pending=other_pending)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "approve"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "approving"
    app.dependency_overrides.clear()


async def test_approve_final_step() -> None:
    """审批最后一个 pending → 任务状态变为 COMPLETED。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1)
    # 没有其他 pending 审批
    db = _make_mock_db(task=task, approval=approval)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "approve"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "completed"
    app.dependency_overrides.clear()


async def test_timeline_ownership() -> None:
    """不同用户访问 timeline 返回 40003。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, user_id="owner_user")

    db = AsyncMock()

    db.execute = AsyncMock(return_value=_MockScalarOneOrNone(task))

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    # 用不同用户请求
    headers = _make_auth_headers(user_id="other_user")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/tasks/{task_id}/timeline",
            headers=headers,
        )

    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 40003
    app.dependency_overrides.clear()


async def test_cancel_completed_task_rejected() -> None:
    """已完成/已取消的任务不可再取消，返回 40001。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.COMPLETED)
    db = _make_mock_db(task=task)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            headers=headers,
        )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 40001
    assert "不可取消" in data["message"]
    app.dependency_overrides.clear()


async def test_cancel_pending_task_success() -> None:
    """pending 状态的任务可被属主取消。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.PENDING)
    db = _make_mock_db(task=task)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert data["data"]["status"] == "cancelled"
    assert task.status == TaskStatus.CANCELLED
    app.dependency_overrides.clear()


async def test_cancel_rejects_non_owner() -> None:
    """非任务属主取消任务返回 40003。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, user_id="owner_user", status=TaskStatus.PENDING)
    db = _make_mock_db(task=task)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="other_user")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            headers=headers,
        )

    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 40003
    app.dependency_overrides.clear()


async def test_add_sign_closes_original_approval() -> None:
    """加签后原审批记录应关闭（不再是 pending），并生成被加签人的新记录。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1)
    db = _make_mock_db(task=task, approval=approval)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="user1")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "add_sign", "add_sign_user_id": "user2"},
            headers=headers,
        )

    assert response.status_code == 200
    assert approval.status == "done"
    assert approval.action == ApprovalAction.ADD_SIGN
    assert approval.add_sign_user_id == "user2"
    assert approval.decided_at is not None
    added = [c.args[0] for c in db.add.call_args_list]
    assert any(
        isinstance(a, ApprovalModel) and a.approver_id == "user2" and a.status == "pending"
        for a in added
    )
    app.dependency_overrides.clear()


async def test_add_sign_rejects_self() -> None:
    """不能加签给自己。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1)
    db = _make_mock_db(task=task, approval=approval)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="user1")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": "add_sign", "add_sign_user_id": "user1"},
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["code"] == 40001
    app.dependency_overrides.clear()


async def test_detail_visible_to_current_approver() -> None:
    """当前审批人可以查看任务详情并拿到 can_approve 标记。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, user_id="owner_user", status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "admin-1", step=1)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _MockScalarOneOrNone(task),
        _MockScalars([approval]),
    ])

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="admin-1")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/tasks/{task_id}",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["can_approve"] is True
    app.dependency_overrides.clear()


async def test_detail_rejects_unrelated_user() -> None:
    """既非属主也非审批人的用户访问详情返回 40003。"""
    app = create_app()
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, user_id="owner_user", status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "admin-1", step=1)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _MockScalarOneOrNone(task),
        _MockScalars([approval]),
    ])

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="random_user")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/tasks/{task_id}",
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json()["code"] == 40003
    app.dependency_overrides.clear()


# ---------------------------------------------------------------- 审批流转模式
# 设计 §4.3：任一人通过（默认）时同步骤其他待办自动关闭；会签需全部通过才算该步完成。


async def _approve(task_id: str, db, *, action: str = "approve", user_id: str = "user1"):
    """调用审批端点并返回响应。"""
    app = create_app()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id=user_id)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/tasks/{task_id}/approve",
            json={"action": action},
            headers=headers,
        )
    app.dependency_overrides.clear()
    return response


async def test_any_one_closes_same_step_siblings_and_advances() -> None:
    """任一人通过：同步骤其他待办自动关闭，仍有后续步骤时任务保持 APPROVING。"""
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1, mode="any_one")
    sibling = _make_approval("a2", task_id, "user2", step=1, mode="any_one")
    next_step = _make_approval("a3", task_id, "user3", step=2, mode="any_one")
    db = _make_mock_db(task=task, approval=approval, other_pending=[sibling, next_step])

    response = await _approve(task_id, db)

    assert response.json()["data"]["status"] == "approving"
    assert approval.status == "approve"
    assert sibling.status == "skipped"
    assert next_step.status == "pending"


async def test_all_must_waits_for_every_member() -> None:
    """会签：其他成员仍待审时任务保持 APPROVING，不关闭同步骤记录。"""
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1, mode="all_must")
    sibling = _make_approval("a2", task_id, "user2", step=1, mode="all_must")
    db = _make_mock_db(task=task, approval=approval, other_pending=[sibling])

    response = await _approve(task_id, db)

    assert response.json()["data"]["status"] == "approving"
    assert sibling.status == "pending"


async def test_all_must_completes_when_all_members_approved() -> None:
    """会签：最后一名成员通过后任务完成。"""
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=1, mode="all_must")
    db = _make_mock_db(task=task, approval=approval)

    response = await _approve(task_id, db)

    assert response.json()["data"]["status"] == "completed"
    assert task.status == TaskStatus.COMPLETED


async def test_reject_closes_remaining_pending() -> None:
    """驳回：任务置 FAILED，其余待审记录一并关闭，不留悬挂待办。"""
    task_id = str(uuid.uuid4())
    task = _make_task(task_id, status=TaskStatus.APPROVING)
    approval = _make_approval("a1", task_id, "user1", step=2)
    previous = _make_approval("a0", task_id, "user0", step=1, status="approve")
    next_step = _make_approval("a2", task_id, "user3", step=3, status="pending")
    db = _make_mock_db(task=task, approval=approval, other_pending=[previous, next_step])

    response = await _approve(task_id, db, action="reject")

    assert response.json()["data"]["status"] == "failed"
    assert approval.status == "reject"
    assert next_step.status == "skipped"
    assert previous.status == "approve"  # 历史审批结论不被改写