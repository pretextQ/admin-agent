# Copyright 2026  Admin AI Team, All rights reserved.
"""端到端冒烟脚本：登录 → 聊天 → 工具（开发桩）→ 任务 → 审批路由 → 审批。

前置条件：
1. PostgreSQL / Redis 已启动，`alembic upgrade head`、`seed_admin`、`seed_org_demo` 已执行
2. 开发桩已启动：`python scripts/dev_stubs.py`
3. 后端已启动：`uvicorn app.admin_ai.main:app --port 8000`

覆盖 9 步；报销链路走**真实审批路由**（评审 B-2）：由普通员工 emp999 提交 →
路由到其部门主管 admin001（而非「首个管理员」）→ 主管审批通过。

用法：`PYTHONPATH=. python scripts/e2e_smoke.py`，全部通过退出码为 0。
"""

from __future__ import annotations

import asyncio

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
EMPLOYEE = "emp999"    # 技术部成员，主管为 admin001
APPROVER = "admin001"  # 技术部主管（由 seed_org_demo 设定）


async def _login(client: httpx.AsyncClient, employee_id: str) -> str:
    """开发登录并返回 access_token。"""
    resp = await client.get("/auth/dev-login", params={"employee_id": employee_id})
    return resp.json()["data"]["access_token"]


async def main() -> int:
    failures: list[str] = []
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # 1. 开发登录（admin001 由 seed_admin 创建；组织数据由 seed_org_demo 建立）
        approver_token = await _login(c, APPROVER)
        c.headers["Authorization"] = f"Bearer {approver_token}"
        me = (await c.get("/auth/me")).json()["data"]
        print(f"[1] 登录 OK: {me['employee_id']} ({me['role']})")

        # 2. 低风险：请假一条消息补全槽位并执行
        reply = (
            await c.post("/chat/send", json={
                "message": "我要请假：年假 2026-09-25 到 2026-09-26",
                "conversation_id": "e2e-leave",
            })
        ).json()["data"]
        print(f"[2] 请假回复: {reply['content'][:60]} requires_action={reply.get('requires_action')}")
        if reply.get("requires_action"):
            failures.append("请假不应需要确认或追问")

        # 3. 我的任务里应出现已完成的请假记录
        tasks = (await c.get("/tasks/my")).json()["data"]
        leave = next((t for t in tasks["items"] if t["type"] == "leave"), None)
        status = leave["status"] if leave else "缺失"
        print(f"[3] 我的任务: total={tasks['total']}, leave={status}")
        if not leave or leave["status"] != "completed":
            failures.append("请假任务未自动完成")

        # 4. 高风险：普通员工 emp999 提交报销 → 确认卡片（发票走附件槽位）
        employee_token = await _login(c, EMPLOYEE)
        c.headers["Authorization"] = f"Bearer {employee_token}"
        reply = (
            await c.post("/chat/send", json={
                "message": "我要报销酒店费用500元",
                "conversation_id": "e2e-expense",
                "attachments": ["INV-2026-001.pdf"],
            })
        ).json()["data"]
        print(f"[4] 报销回复: {reply['content'][:40]} requires_action={reply.get('requires_action')}")
        if not reply.get("requires_action"):
            failures.append("报销应返回确认卡片")

        # 5. 确认后执行 → 按审批规则路由出审批链（≤2000 元 = 部门主管单级）
        reply = (await c.post("/chat/confirm/e2e-expense", json={"confirmed": True})).json()["data"]
        print(f"[5] 确认后: {reply['content'][:40]}")

        # 6. 主管的待审批列表应包含该报销任务（证明路由到了真实主管，而非任意管理员）
        c.headers["Authorization"] = f"Bearer {approver_token}"
        pending = (await c.get("/tasks/pending-approval")).json()["data"]
        expense = next((t for t in pending["items"] if t["type"] == "expense"), None)
        print(f"[6] 待我审批: total={pending['total']}, expense={'有' if expense else '缺失'}")
        if not expense:
            failures.append("主管的待审批列表缺少报销任务（审批路由可能未生效）")
        else:
            # 7. 审批人查看详情：可审批，且审批链为单级（≤2000 元按 APR-001）
            detail = (await c.get(f"/tasks/{expense['id']}")).json()["data"]
            chain = detail.get("approvals") or []
            print(
                f"[7] 详情: can_approve={detail.get('can_approve')}, "
                f"审批链={[(a['step'], a['status']) for a in chain]}"
            )
            if not detail.get("can_approve"):
                failures.append("主管应看到 can_approve=true")
            if len(chain) != 1:
                failures.append(f"≤2000 元报销应为单级审批，实际 {len(chain)} 级")

            # 8. 同意审批 → 任务完成
            approved = (
                await c.post(f"/tasks/{expense['id']}/approve", json={"action": "approve"})
            ).json()["data"]
            print(f"[8] 审批后状态: {approved['status']}")
            if approved["status"] != "completed":
                failures.append("审批通过后任务应为 completed")

        # 9. 会话历史已落库
        history = (await c.get("/chat/history/e2e-leave")).json()["data"]
        print(f"[9] 会话历史: total={history['total']}")
        if history["total"] < 2:
            failures.append("会话消息未落库")

    print()
    if failures:
        print("E2E 冒烟失败：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("E2E 冒烟全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
