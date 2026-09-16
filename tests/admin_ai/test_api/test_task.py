# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务/审批接口测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import ApprovalModel, TaskModel, TaskStatus
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


def _make_approval(approval_id: str, task_id: str, approver_id: str, step: int = 1, status: str = "pending") -> MagicMock:
    approval = MagicMock(spec=ApprovalModel)
    approval.id = approval_id
    approval.task_id = task_id
    approval.approver_id = approver_id
    approval.step = step
    approval.status = status
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


def _make_mock_db(task=None, approval=None, approvals=None, next_pending=None):
    """创建 mock AsyncSession，按调用顺序返回不同结果。"""
    db = AsyncMock()

    results = []
    # 第1次 execute: 查 task
    results.append(_MockScalarOneOrNone(task))
    # 第2次 execute: 查 approval (pending)
    results.append(_MockScalarOneOrNone(approval))
    # 第3次 execute: 查 next_pending (for approve action)
    results.append(_MockScalarOneOrNone(next_pending))

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
    db = _make_mock_db(task=task, approval=approval, next_pending=other_pending)

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
    db = _make_mock_db(task=task, approval=approval, next_pending=None)

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