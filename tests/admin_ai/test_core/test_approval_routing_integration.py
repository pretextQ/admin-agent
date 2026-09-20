# Copyright 2026  Admin AI Team, All rights reserved.
"""审批路由的真实 PostgreSQL 集成测试（评审 B-2，覆盖 T-1/T-2/T-3/T-4）。

默认跳过（`-m integration` 显式运行）：需要 PostgreSQL 与 `alembic upgrade head`。

用例自带独立业务类型与组织数据并在结束时回滚，因此不依赖开发库里的组织种子，
也不会污染现有数据。
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.admin_ai.core.approval.repository import route_approval
from app.admin_ai.core.approval.router import RoutingError
from app.admin_ai.db.database import get_session_factory
from app.admin_ai.db.models import (
    ApprovalDelegationModel,
    ApprovalMode,
    ApprovalRuleModel,
    ApproverType,
    DepartmentModel,
    UserModel,
    generate_uuid,
    utc_now,
)

pytestmark = pytest.mark.integration

# 独立业务类型，避免与迁移种子的 expense 规则相互干扰
BUSINESS = "expense_routing_integration"


@pytest.fixture(autouse=True)
async def _dispose_engine():
    """每个用例结束后释放连接池。

    pytest-asyncio 为每个用例新建事件循环，全局引擎里的连接会绑定到已关闭的循环
    （表现为 `Event loop is closed`），因此集成用例之间必须显式释放。
    """
    yield
    from app.admin_ai.db import database

    if database._engine is not None:
        await database._engine.dispose()
        database._engine = None
        database._session_factory = None


async def _seed_org(db) -> dict[str, str]:
    """公司 → 技术部，主管分别为 gm / mgr；emp 属技术部。返回 id 映射。"""
    suffix = generate_uuid()[:8]
    ids = {name: generate_uuid() for name in ("gm", "mgr", "emp", "company", "tech")}
    # 分步落库：部门的外键指向用户，同一次 flush 内顺序不可控
    db.add_all(
        [
            UserModel(
                id=ids["gm"],
                employee_id=f"gm-{suffix}",
                name=f"总经理-{suffix}",
                role="manager",
            ),
            UserModel(
                id=ids["mgr"],
                employee_id=f"mgr-{suffix}",
                name=f"主管-{suffix}",
                role="manager",
            ),
            UserModel(
                id=ids["emp"],
                employee_id=f"emp-{suffix}",
                name=f"员工-{suffix}",
                role="employee",
                department=None,
            ),
        ]
    )
    await db.flush()

    db.add_all(
        [
            DepartmentModel(
                id=ids["company"],
                name=f"公司-{suffix}",
                path=f"/公司-{suffix}",
                level=1,
                manager_id=ids["gm"],
                external_id=f"IT-{suffix}-C",
            ),
            DepartmentModel(
                id=ids["tech"],
                name=f"技术部-{suffix}",
                parent_id=ids["company"],
                path=f"/公司-{suffix}/技术部-{suffix}",
                level=2,
                manager_id=ids["mgr"],
                external_id=f"IT-{suffix}-T",
            ),
        ]
    )
    await db.flush()
    db.add_all(
        [
            ApprovalRuleModel(
                id=generate_uuid(),
                business_type=BUSINESS,
                amount_min=Decimal("0"),
                amount_max=Decimal("2000"),
                step_order=1,
                approver_type=ApproverType.SELF_DEPT_MANAGER,
                approval_mode=ApprovalMode.ANY_ONE,
            ),
            ApprovalRuleModel(
                id=generate_uuid(),
                business_type=BUSINESS,
                amount_min=Decimal("2000"),
                step_order=1,
                approver_type=ApproverType.PARENT_DEPT_MANAGER,
                approval_mode=ApprovalMode.ANY_ONE,
            ),
            ApprovalRuleModel(
                id=generate_uuid(),
                business_type=BUSINESS,
                amount_min=Decimal("2000"),
                step_order=2,
                approver_type=ApproverType.SELF_DEPT_MANAGER,
                approval_mode=ApprovalMode.ANY_ONE,
            ),
        ]
    )
    await db.flush()
    # 归属部门（部门行已存在，可安全引用）
    memberships = {"gm": ids["company"], "mgr": ids["tech"], "emp": ids["tech"]}
    for key, department_id in memberships.items():
        user = (await db.execute(select(UserModel).where(UserModel.id == ids[key]))).scalar_one()
        user.department_id = department_id
    await db.flush()
    return ids

async def test_routing_single_level_small_amount() -> None:
    """T-1 真实库：报销 1500 元 → 审批链 = [部门主管] 单级。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_org(db)
        outcome = await route_approval(
            db,
            business_type=BUSINESS,
            applicant_id=ids["emp"],
            slots={"amount": 1500},
        )
        assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, ids["mgr"])]
        await db.rollback()


async def test_routing_two_levels_large_amount() -> None:
    """T-2 真实库：报销 3000 元 → [上级部门主管(总监), 部门主管] 两级且顺序正确。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_org(db)
        outcome = await route_approval(
            db,
            business_type=BUSINESS,
            applicant_id=ids["emp"],
            slots={"amount": 3000},
        )
        assert [(s.step, s.approver_id) for s in outcome.steps] == [
            (1, ids["gm"]),
            (2, ids["mgr"]),
        ]
        await db.rollback()


async def test_routing_blocks_self_approval_by_ascending() -> None:
    """T-3 真实库：主管本人提交 → 上溯到上级，绝不出现自审。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_org(db)
        outcome = await route_approval(
            db,
            business_type=BUSINESS,
            applicant_id=ids["mgr"],
            slots={"amount": 1500},
        )
        assert [s.approver_id for s in outcome.steps] == [ids["gm"]]
        await db.rollback()


async def test_routing_fails_at_root_for_top_manager() -> None:
    """T-4 真实库：顶层负责人提交 → 上溯无路，RoutingError（转人工指派）。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_org(db)
        with pytest.raises(RoutingError) as exc:
            await route_approval(
                db,
                business_type=BUSINESS,
                applicant_id=ids["gm"],
                slots={"amount": 1500},
            )
        assert exc.value.reason == "self_approval"
        await db.rollback()


async def test_routing_fails_without_rules() -> None:
    """T-7 真实库：未配置规则的业务类型 → RoutingError（不猜测审批人）。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_org(db)
        with pytest.raises(RoutingError) as exc:
            await route_approval(
                db,
                business_type="business_without_rules",
                applicant_id=ids["emp"],
                slots={"amount": 100},
            )
        assert exc.value.reason == "no_rule"
        await db.rollback()


async def test_routing_substitutes_active_delegation() -> None:
    """T-5 真实库：主管休假且有生效委派 → 换成被委托人并记录 delegated_from。"""
    factory = get_session_factory()
    async with factory() as db:
        ids = await _seed_org(db)
        deputy_id = generate_uuid()
        db.add(
            UserModel(
                id=deputy_id,
                employee_id=f"deputy-{generate_uuid()[:8]}",
                name="代理人",
                role="manager",
                department_id=ids["tech"],
            )
        )
        await db.flush()  # 委派的外键指向用户，先落库

        now = utc_now()
        db.add(
            ApprovalDelegationModel(
                id=generate_uuid(),
                delegator_id=ids["mgr"],
                delegate_id=deputy_id,
                start_at=now - timedelta(days=1),
                end_at=now + timedelta(days=1),
                business_types=[BUSINESS],
            )
        )
        await db.flush()

        outcome = await route_approval(
            db,
            business_type=BUSINESS,
            applicant_id=ids["emp"],
            slots={"amount": 1500},
        )
        assert [(s.approver_id, s.delegated_from) for s in outcome.steps] == [
            (deputy_id, ids["mgr"])
        ]
        await db.rollback()
