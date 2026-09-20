# Copyright 2026  Admin AI Team, All rights reserved.
"""状态查询（场景 REQ-03）的真实 PostgreSQL 集成测试。

单测覆盖不到的部分在这里验证：**归属条件下推到 SQL**（本人数据隔离）、
审批状态与当前待审人的关联、时间窗口过滤、按单据号精确查询的越权拒绝。

默认跳过（`-m integration` 显式运行）：需要 PostgreSQL 与 `alembic upgrade head`。
用例自建随机用户与单据并在结束时回滚，不依赖也不污染开发库数据。
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.admin_ai.core.status_query import StatusQueryService
from app.admin_ai.db.database import get_session_factory
from app.admin_ai.db.models import (
    ApprovalModel,
    ApprovalStatus,
    TaskModel,
    TaskStatus,
    TaskType,
    UserModel,
    generate_uuid,
    utc_now,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _dispose_engine():
    """每个用例结束后释放连接池（与审批路由集成用例同因：事件循环重建）。"""
    yield
    from app.admin_ai.db import database

    if database._engine is not None:
        await database._engine.dispose()
        database._engine = None
        database._session_factory = None


async def _seed_users(db) -> dict[str, str]:
    """两位员工 + 一位主管；每次用随机工号，避免与开发库既有数据冲突。"""
    suffix = generate_uuid()[:8]
    ids = {name: generate_uuid() for name in ("owner", "other", "approver")}
    db.add_all(
        [
            UserModel(
                id=ids["owner"],
                employee_id=f"owner-{suffix}",
                name=f"本人-{suffix}",
                role="employee",
            ),
            UserModel(
                id=ids["other"],
                employee_id=f"other-{suffix}",
                name=f"他人-{suffix}",
                role="employee",
            ),
            UserModel(
                id=ids["approver"],
                employee_id=f"appr-{suffix}",
                name=f"主管-{suffix}",
                role="manager",
            ),
        ]
    )
    await db.flush()
    return ids


def _task(
    user_id: str,
    *,
    title: str,
    task_type: TaskType,
    status: TaskStatus = TaskStatus.COMPLETED,
    created_at=None,
    data: dict | None = None,
    external_id: str | None = None,
) -> TaskModel:
    return TaskModel(
        id=generate_uuid(),
        user_id=user_id,
        type=task_type,
        status=status,
        title=title,
        data=data or {},
        external_id=external_id,
        created_at=created_at or utc_now(),
    )


async def test_status_query_only_returns_own_tasks() -> None:
    """归属下推 SQL：本人查询看不到他人单据（场景 03 §2、§5.1）。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        db.add_all(
            [
                _task(ids["owner"], title="本人请假单", task_type=TaskType.LEAVE),
                _task(ids["owner"], title="本人报销单", task_type=TaskType.EXPENSE),
                _task(ids["other"], title="他人报销单", task_type=TaskType.EXPENSE),
            ]
        )
        await db.flush()

        service = StatusQueryService()
        outcome = await service.answer(
            db, user_id=ids["owner"], slots={}, message="我的任务进度如何"
        )

        assert outcome.result_count == 2
        assert "本人请假单" in outcome.content
        assert "他人报销单" not in outcome.content, "状态查询泄漏了他人单据（归属未下推 SQL）"
        await db.rollback()


async def test_expense_status_filters_by_type() -> None:
    """报销状态只统计报销单，不把请假单算进来。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        db.add_all(
            [
                _task(
                    ids["owner"],
                    title="报销（酒店）",
                    task_type=TaskType.EXPENSE,
                    data={"expense_type": "酒店", "amount": 500},
                ),
                _task(ids["owner"], title="请假（年假）", task_type=TaskType.LEAVE),
            ]
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message="我的报销到哪一步了"
        )

        assert outcome.query_type == "报销状态"
        assert outcome.result_count == 1
        assert "报销（酒店）" in outcome.content
        assert "请假（年假）" not in outcome.content
        assert "500.00" in outcome.content
        await db.rollback()


async def test_task_progress_narrows_to_named_business() -> None:
    """任务进度按消息点名的业务收窄：「我的请假批了吗」不该倒出报销单。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        db.add_all(
            [
                _task(ids["owner"], title="请假（年假）", task_type=TaskType.LEAVE),
                _task(ids["owner"], title="报销（酒店）", task_type=TaskType.EXPENSE),
            ]
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db,
            user_id=ids["owner"],
            slots={"query_type": "任务进度"},
            message="我的请假批了吗",
        )

        assert outcome.result_count == 1
        assert "请假（年假）" in outcome.content
        assert "报销（酒店）" not in outcome.content
        assert "1 条请假记录" in outcome.content
        await db.rollback()


async def test_approving_task_shows_current_approver() -> None:
    """在途单据要带出当前待审人——用户问的「哪一步」指的就是这个。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        task = _task(
            ids["owner"],
            title="报销（酒店）",
            task_type=TaskType.EXPENSE,
            status=TaskStatus.APPROVING,
        )
        db.add(task)
        await db.flush()
        db.add(
            ApprovalModel(
                id=generate_uuid(),
                task_id=task.id,
                approver_id=ids["approver"],
                step=1,
                status=ApprovalStatus.PENDING.value,
                approver_source="self_dept_manager",
            )
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message="我的报销到哪一步了"
        )

        assert "审批中" in outcome.content
        assert "主管-" in outcome.content
        await db.rollback()


async def test_time_range_defaults_to_recent_30_days() -> None:
    """默认时间范围 30 天：更早的单据不计入（场景 03 §5.2）。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        db.add_all(
            [
                _task(ids["owner"], title="new-recent", task_type=TaskType.LEAVE),
                _task(
                    ids["owner"],
                    title="older-than-window",
                    task_type=TaskType.LEAVE,
                    created_at=utc_now() - timedelta(days=90),
                ),
            ]
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message="我的任务进度如何"
        )

        assert outcome.result_count == 1
        assert "older-than-window" not in outcome.content
        await db.rollback()


async def test_time_range_last_month_window() -> None:
    """「上个月」按自然月限定：本月单据不计入。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        now = utc_now()
        last_month = now.replace(day=1, hour=12, minute=0, second=0, microsecond=0) - timedelta(
            days=1
        )
        db.add_all(
            [
                _task(
                    ids["owner"],
                    title="last-month-task",
                    task_type=TaskType.EXPENSE,
                    created_at=last_month,
                ),
                _task(ids["owner"], title="this-month-task", task_type=TaskType.EXPENSE),
            ]
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message="我上个月的报销到哪一步了"
        )

        assert outcome.result_count == 1
        assert "last-month-task" in outcome.content
        assert "this-month-task" not in outcome.content
        await db.rollback()


async def test_leave_balance_sums_completed_leave() -> None:
    """假期余额：额度取自降级来源，本年已用由已完成的请假单汇总（含首含尾）。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        today = utc_now().date()
        start = today.replace(month=1, day=1) if today.month > 1 else today
        db.add(
            _task(
                ids["owner"],
                title="请假（年假）",
                task_type=TaskType.LEAVE,
                status=TaskStatus.COMPLETED,
                data={
                    "leave_type": "年假",
                    "start_date": start.isoformat(),
                    "end_date": (start + timedelta(days=2)).isoformat(),
                },
            )
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message="我还剩几天年假"
        )

        assert outcome.query_type == "假期余额"
        assert "年假" in outcome.content
        # 默认额度 10 天 - 已用 3 天 = 剩余 7 天
        assert "剩余 7 天" in outcome.content
        # 未接 HR 工具时必须如实标注来源，不能把默认值当权威数据
        assert "本地默认额度" in outcome.content
        await db.rollback()


async def test_leave_balance_lists_pending_request() -> None:
    """在途请假单要出现在余额回复里，否则「我的请假批了吗」得不到回答。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        task = _task(
            ids["owner"],
            title="请假（年假）",
            task_type=TaskType.LEAVE,
            status=TaskStatus.APPROVING,
            data={"leave_type": "年假", "start_date": "2026-09-25", "end_date": "2026-09-26"},
        )
        db.add(task)
        await db.flush()
        db.add(
            ApprovalModel(
                id=generate_uuid(),
                task_id=task.id,
                approver_id=ids["approver"],
                step=1,
                status=ApprovalStatus.PENDING.value,
                approver_source="self_dept_manager",
            )
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message="我还剩几天年假"
        )

        assert "在途" in outcome.content
        assert "主管-" in outcome.content
        await db.rollback()


async def test_task_detail_by_external_id() -> None:
    """按单据号精确查询返回详情与审批链。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        external_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
        task = _task(
            ids["owner"],
            title="报销（酒店）",
            task_type=TaskType.EXPENSE,
            status=TaskStatus.APPROVING,
            data={"expense_type": "酒店", "amount": 500},
            external_id=external_id,
        )
        db.add(task)
        await db.flush()
        db.add(
            ApprovalModel(
                id=generate_uuid(),
                task_id=task.id,
                approver_id=ids["approver"],
                step=1,
                status=ApprovalStatus.PENDING.value,
                approver_source="self_dept_manager",
            )
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message=f"查询任务 {external_id} 的状态"
        )

        assert external_id in outcome.content
        assert "500.00" in outcome.content
        assert "第1步" in outcome.content
        await db.rollback()


async def test_task_detail_rejects_other_owners_task() -> None:
    """越权查询他人单据：明确拒绝且不泄漏任何单据内容（场景 03 TC010）。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_users(db)
        external_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
        db.add(
            _task(
                ids["other"],
                title="他人报销单",
                task_type=TaskType.EXPENSE,
                status=TaskStatus.APPROVING,
                external_id=external_id,
            )
        )
        await db.flush()

        outcome = await StatusQueryService().answer(
            db, user_id=ids["owner"], slots={}, message=f"查询任务 {external_id} 的状态"
        )

        assert "没有权限" in outcome.content
        assert "他人报销单" not in outcome.content
        await db.rollback()
