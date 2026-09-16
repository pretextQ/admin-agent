# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""插入 admin 测试账号。"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.db.database import get_session_factory
from app.admin_ai.db.models import UserModel


async def seed() -> None:
    """创建 admin001 测试账号（如不存在）。"""
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