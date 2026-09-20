# Copyright 2026  Admin AI Team, All rights reserved.
"""组织架构与审批路由（评审 B-2）。

- `router`：纯算法（规则匹配 + 审批人解析 + 自审上溯 + 去重 + 委派替换）
- `repository`：数据库装载与落库
- `sync`：组织架构上游同步（HR 接口 / CSV 降级）
"""

from app.admin_ai.core.approval.router import (
    ApprovalStep,
    DelegationInfo,
    DepartmentInfo,
    OrgSnapshot,
    RoutingError,
    RoutingOutcome,
    RuleInfo,
    UserInfo,
    match_rules,
    resolve_chain,
)

__all__ = [
    "ApprovalStep",
    "DelegationInfo",
    "DepartmentInfo",
    "OrgSnapshot",
    "RoutingError",
    "RoutingOutcome",
    "RuleInfo",
    "UserInfo",
    "match_rules",
    "resolve_chain",
]
