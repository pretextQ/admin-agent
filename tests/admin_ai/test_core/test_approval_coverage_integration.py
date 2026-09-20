# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""审批覆盖面的真实 PostgreSQL 集成测试（场景 04/05/08/09/10）。

与 `test_approval_routing_integration.py` 的区别：这里**直接使用迁移 `003` 导入的默认规则**
（不看测试自造的规则），因此验证的是「上线时那套配置」是否真的按场景文档分支。

默认跳过（`-m integration` 显式运行）：需要 PostgreSQL 与 `alembic upgrade head`。
用例自带组织数据并在结束时回滚，不污染现有数据。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin_ai.config import get_config
from app.admin_ai.core.approval.repository import route_approval
from app.admin_ai.core.approval.router import RoutingError
from app.admin_ai.db.models import DepartmentModel, UserModel, generate_uuid

pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    """独立引擎 + 事务内组织数据（用例结束回滚）。

    集成用例需自建引擎：pytest-asyncio 每个用例新建事件循环，全局引擎的连接池会绑定到
    已关闭的循环（`Event loop is closed`）——与本目录另一份集成用例同样的处理。
    """
    engine = create_async_engine(get_config().DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _seed_org(db, *, extra_roles: dict[str, list[str]] | None = None) -> dict[str, str]:
    """公司(主管 gm) → 技术部(主管 mgr)，emp 属技术部；可追加角色成员（hr / legal）。"""
    suffix = generate_uuid()[:8]
    ids = {name: generate_uuid() for name in ("gm", "mgr", "emp", "company", "tech")}

    users = [
        UserModel(id=ids["gm"], employee_id=f"gm-{suffix}", name=f"总经理-{suffix}", role="manager"),
        UserModel(id=ids["mgr"], employee_id=f"mgr-{suffix}", name=f"主管-{suffix}", role="manager"),
        UserModel(id=ids["emp"], employee_id=f"emp-{suffix}", name=f"员工-{suffix}", role="employee"),
    ]
    for role, members in (extra_roles or {}).items():
        for index, _ in enumerate(members):
            user_id = generate_uuid()
            users.append(
                UserModel(
                    id=user_id,
                    employee_id=f"{role}{index}-{suffix}",
                    name=f"{role}-{suffix}",
                    role=role,
                )
            )
            ids[f"{role}{index}"] = user_id
    db.add_all(users)
    await db.flush()  # 部门外键指向用户，先落库

    db.add_all(
        [
            DepartmentModel(
                id=ids["company"],
                name=f"公司-{suffix}",
                path=f"/公司-{suffix}",
                level=1,
                manager_id=ids["gm"],
                external_id=f"CV-{suffix}-C",
            ),
            DepartmentModel(
                id=ids["tech"],
                name=f"技术部-{suffix}",
                parent_id=ids["company"],
                path=f"/公司-{suffix}/技术部-{suffix}",
                level=2,
                manager_id=ids["mgr"],
                external_id=f"CV-{suffix}-T",
            ),
        ]
    )
    await db.flush()

    for user in users:
        if user.id in (ids["emp"], ids["mgr"]):
            user.department_id = ids["tech"]
        elif user.id == ids["gm"]:
            user.department_id = ids["company"]
    await db.flush()
    return ids


async def _chain(db, ids: dict[str, str], business_type: str, slots: dict) -> list[str]:
    """按默认规则求解审批链，返回审批人 ID 列表。"""
    outcome = await route_approval(
        db, business_type=business_type, applicant_id=ids["emp"], slots=slots
    )
    assert outcome.requires_approval is True, "该请求应需要审批"
    return [step.approver_id for step in outcome.steps]


# ---------------------------------------------------------------- 05 请假

async def test_leave_short_leave_single_level(db) -> None:
    """场景 05：≤2 天 → 直属主管单级审批。"""
    ids = await _seed_org(db, extra_roles={"hr": ["hr01"]})
    chain = await _chain(
        db, ids, "leave", {"leave_type": "年假", "start_date": "2026-09-25", "end_date": "2026-09-26"}
    )
    assert chain == [ids["mgr"]]


async def test_leave_long_leave_adds_hr_step(db) -> None:
    """场景 05：>2 天 → 主管 + HR 复核两级。"""
    ids = await _seed_org(db, extra_roles={"hr": ["hr01"]})
    chain = await _chain(
        db, ids, "leave", {"leave_type": "年假", "start_date": "2026-09-21", "end_date": "2026-09-23"}
    )
    assert chain == [ids["mgr"], ids["hr0"]]


async def test_leave_without_hr_member_falls_to_manual(db) -> None:
    """>2 天但 HR 角色无人 → 人工指派（不静默降级为单级）。"""
    ids = await _seed_org(db)  # 不建 hr 成员
    with pytest.raises(RoutingError) as exc:
        await _chain(
            db, ids, "leave",
            {"leave_type": "年假", "start_date": "2026-09-21", "end_date": "2026-09-23"},
        )
    assert exc.value.reason == "no_role_member"


# ---------------------------------------------------------------- 10 用印

async def test_seal_contract_goes_to_legal(db) -> None:
    """场景 10：合同章 → 法务审核（默认规则首条带条件）。"""
    ids = await _seed_org(db, extra_roles={"legal": ["legal01"]})
    chain = await _chain(db, ids, "seal", {"document_name": "采购合同", "seal_type": "合同章"})
    assert chain == [ids["legal0"]]


async def test_seal_other_types_go_to_manager(db) -> None:
    """场景 10：其他印章 → 部门负责人（兜底规则）。"""
    ids = await _seed_org(db, extra_roles={"legal": ["legal01"]})
    chain = await _chain(db, ids, "seal", {"document_name": "证明文件", "seal_type": "公章"})
    assert chain == [ids["mgr"]]


# ---------------------------------------------------------------- 08 差旅 / 09 资产 / 04 物资

async def test_travel_long_trip_adds_director_step(db) -> None:
    """场景 08：出差 >5 天 → 总监 + 主管两级。"""
    ids = await _seed_org(db)
    chain = await _chain(
        db, ids, "travel",
        {"destination": "上海", "start_date": "2026-09-21", "end_date": "2026-09-28"},
    )
    assert chain == [ids["gm"], ids["mgr"]]


async def test_travel_short_trip_single_level(db) -> None:
    """场景 08：出差 ≤5 天 → 主管单级。"""
    ids = await _seed_org(db)
    chain = await _chain(
        db, ids, "travel",
        {"destination": "上海", "start_date": "2026-09-21", "end_date": "2026-09-23"},
    )
    assert chain == [ids["mgr"]]


async def test_asset_value_threshold(db) -> None:
    """场景 09：资产价值 >5000 → 总监；≤5000 或未知 → 主管。"""
    ids = await _seed_org(db)
    assert await _chain(db, ids, "asset", {"asset_name": "笔记本", "amount": 6000}) == [ids["gm"]]
    assert await _chain(db, ids, "asset", {"asset_name": "显示器", "amount": 3000}) == [ids["mgr"]]
    assert await _chain(db, ids, "asset", {"asset_name": "显示器"}) == [ids["mgr"]]


async def test_material_always_requires_manager_today(db) -> None:
    """场景 04：物资当前一律主管审批（单价未知时无法分级，兜底规则保证不静默放行）。"""
    ids = await _seed_org(db)
    assert await _chain(db, ids, "material", {"item_name": "A4纸", "quantity": 2}) == [ids["mgr"]]
    assert await _chain(db, ids, "material", {"item_name": "显示器", "amount": 300}) == [ids["mgr"]]


# ---------------------------------------------------------------- 无需审批的语义

async def test_unmatched_request_needs_no_approval(db) -> None:
    """规则存在但本次不匹配 → 无需审批（以物资为例：把兜底规则停用后单价 50 元走完成）。"""
    from sqlalchemy import select, update

    from app.admin_ai.db.models import ApprovalRuleModel

    ids = await _seed_org(db)
    # 停用物资的兜底规则，只留「单价 ≥100」的分支
    await db.execute(
        update(ApprovalRuleModel)
        .where(ApprovalRuleModel.business_type == "material")
        .where(ApprovalRuleModel.amount_min.is_(None))
        .values(enabled=False)
    )
    await db.flush()

    outcome = await route_approval(
        db, business_type="material", applicant_id=ids["emp"], slots={"item_name": "A4纸", "amount": 50}
    )
    assert outcome.requires_approval is False
    assert outcome.steps == ()

    # 恢复规则（本用例在同一事务内，恢复后不影响其他用例；rollback 也会兜底）
    await db.execute(
        update(ApprovalRuleModel)
        .where(ApprovalRuleModel.business_type == "material")
        .where(ApprovalRuleModel.amount_min.is_(None))
        .values(enabled=True)
    )
    await db.flush()
    assert (
        await db.execute(select(ApprovalRuleModel).where(ApprovalRuleModel.business_type == "material"))
    ).scalars().all()
