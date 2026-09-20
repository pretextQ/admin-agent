# Copyright 2026  Admin AI Team, All rights reserved.
"""端到端冒烟脚本：登录 → 聊天 → 工具（开发桩）→ 任务 → 审批路由 → 审批。

前置条件：
1. PostgreSQL / Redis 已启动，`alembic upgrade head`、`seed_admin`、`seed_org_demo` 已执行
2. 开发桩已启动：`python scripts/dev_stubs.py`
3. 后端已启动：`uvicorn app.admin_ai.main:app --port 8000`

覆盖 9 步，两条主链路都走**真实审批路由**（评审 B-2）：
- 请假（≤2 天）→ 审批链：部门主管单级（无需二次确认卡片）
- 报销（≤2000 元）→ 二次确认卡片 → 审批链：部门主管单级
两者都由普通员工 emp999 提交、路由到其部门主管 admin001（而非「首个管理员」）并审批通过。

用法：`PYTHONPATH=. python scripts/e2e_smoke.py`，全部通过退出码为 0。
"""

from __future__ import annotations

import asyncio
import uuid

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
    # 会话 ID 每次运行唯一：会话状态在 Redis 里带属主（TTL 24h），沿用固定 ID 会与上一轮的属主冲突
    run_id = uuid.uuid4().hex[:8]
    leave_conv = f"e2e-leave-{run_id}"
    expense_conv = f"e2e-expense-{run_id}"
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # 1. 开发登录：员工 emp999 办事，主管 admin001 审批
        approver_token = await _login(c, APPROVER)
        employee_token = await _login(c, EMPLOYEE)
        c.headers["Authorization"] = f"Bearer {employee_token}"
        me = (await c.get("/auth/me")).json()["data"]
        print(f"[1] 登录 OK: 员工={me['employee_id']}，主管={APPROVER}")

        # 2. 请假（年假 9/25~9/26 = 2 天 ≤2）→ 直接提交，生成单级审批链（无需确认卡片）
        reply = (
            await c.post("/chat/send", json={
                "message": "我要请假：年假 2026-09-25 到 2026-09-26",
                "conversation_id": leave_conv,
            })
        ).json()["data"]
        print(f"[2] 请假回复: {reply['content'][:60]} requires_action={reply.get('requires_action')}")
        if reply.get("requires_action"):
            failures.append("请假不应需要二次确认")

        # 3. 员工自己的任务列表里，请假应为「审批中」（需审批但不需要二次确认）
        mine = (await c.get("/tasks/my")).json()["data"]
        leave = next((t for t in mine["items"] if t["type"] == "leave"), None)
        print(
            f"[3] 我的任务: total={mine['total']}, leave={leave['status'] if leave else '缺失'}, "
            f"risk={leave['risk_level'] if leave else '-'}"
        )
        if not leave or leave["status"] != "approving":
            failures.append("≤2 天请假应生成审批链并处于 approving")

        # 4. 报销 500 元 → 高风险二次确认卡片
        reply = (
            await c.post("/chat/send", json={
                "message": "我要报销酒店费用500元",
                "conversation_id": expense_conv,
                "attachments": ["INV-2026-001.pdf"],
            })
        ).json()["data"]
        print(f"[4] 报销回复: {reply['content'][:40]} requires_action={reply.get('requires_action')}")
        if not reply.get("requires_action"):
            failures.append("报销应返回确认卡片")

        # 5. 确认后执行 → 按审批规则路由（≤2000 元 = 部门主管单级）
        reply = (
            await c.post(f"/chat/confirm/{expense_conv}", json={"confirmed": True})
        ).json()["data"]
        print(f"[5] 确认后: {reply['content'][:40]}")

        # 6. 主管的待审批列表应同时包含请假与报销（证明路由到了真实主管）
        c.headers["Authorization"] = f"Bearer {approver_token}"
        pending = (await c.get("/tasks/pending-approval")).json()["data"]
        by_type = {t["type"]: t for t in pending["items"]}
        print(f"[6] 待我审批: total={pending['total']}, types={sorted(by_type)}")
        for wanted in ("leave", "expense"):
            if wanted not in by_type:
                failures.append(f"主管的待审批列表缺少 {wanted}（审批路由可能未生效）")

        # 7. 查看详情：审批链形态符合规则（请假/报销均为单级，且可审批）
        for wanted in ("leave", "expense"):
            task = by_type.get(wanted)
            if not task:
                continue
            detail = (await c.get(f"/tasks/{task['id']}")).json()["data"]
            chain = detail.get("approvals") or []
            print(
                f"[7] {wanted} 详情: can_approve={detail.get('can_approve')}, "
                f"审批链={[(a['step'], a['status']) for a in chain]}"
            )
            if not detail.get("can_approve"):
                failures.append(f"{wanted} 主管应看到 can_approve=true")
            if len(chain) != 1:
                failures.append(f"{wanted} 应为单级审批，实际 {len(chain)} 级")

        # 8. 主管逐单审批 → 均完成
        for wanted in ("leave", "expense"):
            task = by_type.get(wanted)
            if not task:
                continue
            approved = (
                await c.post(f"/tasks/{task['id']}/approve", json={"action": "approve"})
            ).json()["data"]
            print(f"[8] {wanted} 审批后状态: {approved['status']}")
            if approved["status"] != "completed":
                failures.append(f"{wanted} 审批通过后应为 completed")

        # 9. 会话历史已落库（会话属主是员工本人，需切回员工 Token 查询）
        c.headers["Authorization"] = f"Bearer {employee_token}"
        history = (await c.get(f"/chat/history/{leave_conv}")).json()["data"]
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
