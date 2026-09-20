# Copyright 2026  Admin AI Team, All rights reserved.
"""组织架构同步（评审 B-2 / 设计 §3）。

以 HR 系统为权威源同步部门树与汇报线；上游没有接口时用 CSV 导入。
建议由定时任务每日调用一次（设计 §3.2），同步失败会沿用上次快照并告警，不影响业务。

用法：
    # 用配置里的来源（ORG_SYNC_PROVIDER=csv|http）
    PYTHONPATH=. python scripts/sync_org.py

    # 从仓库自带的样例 CSV 导入（开发/联调）
    PYTHONPATH=. python scripts/sync_org.py --provider csv --dir scripts/sample_org

    # 走 HR 组织接口（需 HR_ORG_BASE_URL / HR_ORG_TOKEN）
    PYTHONPATH=. python scripts/sync_org.py --provider http

CSV 格式见 scripts/sample_org/*.csv：部门 `external_id,name,parent_external_id,manager_employee_id`，
员工 `employee_id,name,department_external_id,is_active`。
"""

from __future__ import annotations

import argparse
import asyncio

from app.admin_ai.config import get_config
from app.admin_ai.core.approval.sync import sync_org
from app.admin_ai.db.database import get_session_factory


async def main(args: argparse.Namespace) -> int:
    config = get_config()
    provider = args.provider or config.ORG_SYNC_PROVIDER

    factory = get_session_factory()
    async with factory() as db:
        summary = await sync_org(
            db,
            provider=provider,
            csv_dir=args.dir or config.ORG_SYNC_CSV_DIR,
            base_url=args.base_url or config.HR_ORG_BASE_URL,
            token=config.HR_ORG_TOKEN,
            timeout=config.ORG_SYNC_TIMEOUT_SECONDS,
        )

    print(f"同步来源：{summary.provider}")
    if not summary.ok:
        print(f"[失败] {summary.error}")
        print("组织数据未被修改，系统继续使用上次成功的快照。")
        return 1

    print(f"  新建部门 {summary.departments_created}")
    print(f"  更新部门 {summary.departments_updated}")
    print(f"  停用部门 {summary.departments_deactivated}（上游已删除，软删保留历史）")
    print(f"  更新员工 {summary.employees_updated}")
    print(f"  未匹配员工 {summary.employees_unmatched}（本地无此工号，未自动建号）")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="同步组织架构（HR 为权威源，CSV 为降级方案）")
    parser.add_argument("--provider", choices=["csv", "http", "disabled"], default=None,
                        help="数据来源；默认取配置 ORG_SYNC_PROVIDER")
    parser.add_argument("--dir", default=None, help="CSV 目录（provider=csv 时必填）")
    parser.add_argument("--base-url", default=None, help="HR 组织接口地址（provider=http 时必填）")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
