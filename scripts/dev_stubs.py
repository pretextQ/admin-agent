# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""下游微服务开发桩。

本地开发时在 8001/8002/8003 端口分别模拟 OA、财务、物资系统，
使工具链路无需真实下游即可端到端联调：

    python scripts/dev_stubs.py

所有工具均为 POST {base}/api/{service}/{action}，本桩按路径返回
仿真数据；calendar 的 query_available、material 的 check_stock、
expense 的 create_draft 等关键动作有专门仿真响应。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="Admin AI 下游服务开发桩")

# 关键动作的仿真响应，其余路径走通用回执
CANNED_RESPONSES: dict[str, dict[str, Any]] = {
    "calendar/query_available": {
        "available": [
            {"id": "room-001", "name": "A栋-301会议室", "capacity": 10},
            {"id": "room-002", "name": "B栋-502会议室", "capacity": 20},
        ],
    },
    "calendar/meeting_room/query_available": {
        "available": [
            {"id": "room-001", "name": "A栋-301会议室", "capacity": 10},
            {"id": "room-002", "name": "B栋-502会议室", "capacity": 20},
        ],
    },
    "calendar/meeting_room/book": {"booking_id": None, "status": "booked"},
    "calendar/vehicle/query_available": {
        "available": [
            {"id": "car-001", "name": "公务车-粤A12345", "seats": 5},
        ],
    },
    "calendar/vehicle/book": {"booking_id": None, "status": "booked"},
    "material/check_stock": {"in_stock": True, "quantity": 999},
    "expense/create_draft": {"draft_id": None, "status": "draft_created"},
    "hr/query_leave_balance": {
        "annual": 5.0, "compensatory": 1.0, "sick": 10.0, "personal": 3.0,
    },
}


@app.post("/api/{path:path}")
async def handle(path: str, request: Request) -> dict[str, Any]:
    """通用回执：回显动作与请求体，并附带仿真单号。"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    data = dict(CANNED_RESPONSES.get(path, {}))
    receipt_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
    for key, value in data.items():
        if value is None:
            data[key] = receipt_id

    return {
        "code": 0,
        "message": "success (dev stub)",
        "path": path,
        "data": {
            **data,
            "external_id": receipt_id,
            "received": body,
        },
        "operator": request.headers.get("X-User-Id"),
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "dev-stub"}


def _run(port: int) -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    import threading

    ports = {"OA": 8001, "Finance": 8002, "Material": 8003}
    threads = []
    for name, port in ports.items():
        thread = threading.Thread(target=_run, args=(port,), name=name, daemon=True)
        thread.start()
        threads.append(thread)
        print(f"[dev-stub] {name} 服务已启动: http://localhost:{port}")

    for thread in threads:
        thread.join()
