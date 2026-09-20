# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""状态查询（场景 REQ-03 综合查询）。

意图识别把「我的报销到哪一步了」「我还剩几天年假」归为 `status_query`，
本模块负责把它变成真实答案：解析查询类型与时间范围 → 按归属查库 → 格式化回复。

设计要点：
- **只读**：不写业务数据，不改状态（场景 03 §6 风险等级：低）。
- **归属下推 SQL**：一律带 `tasks.user_id = 当前用户`，绝不「先查全量再内存过滤」，
  也不接受调用方传入他人 user_id（SECURITY §4.3）。
- **降级诚实**：HR 余额取不到时回退本地默认额度，并在回复里说明来源，
  不把默认值当权威数据（硬约定 #11 的同一精神）。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.rules.engine import DEFAULT_LEAVE_BALANCE
from app.admin_ai.core.tools.base import parse_downstream_payload
from app.admin_ai.db.models import (
    ApprovalModel,
    ApprovalStatus,
    TaskModel,
    TaskStatus,
    TaskType,
    UserModel,
    utc_now,
)

logger = structlog.get_logger(__name__)

# 规范查询类型（场景 03 §3.2 query_type 枚举）
QUERY_TYPE_TASK_PROGRESS = "任务进度"
QUERY_TYPE_LEAVE_BALANCE = "假期余额"
QUERY_TYPE_EXPENSE_STATUS = "报销状态"
QUERY_TYPES = (
    QUERY_TYPE_TASK_PROGRESS,
    QUERY_TYPE_LEAVE_BALANCE,
    QUERY_TYPE_EXPENSE_STATUS,
)

# 未识别出查询类型时的追问（场景 03 §8.1 槽位缺失）
ASK_QUERY_TYPE = "请问您想查询哪方面的信息？（任务进度／假期余额／报销状态）"
# 兜底文案：API 层查询失败时用户不应看到空回复
QUERY_FAILED = "抱歉，查询暂时无法完成，请稍后重试，或联系行政专员协助。"

DEFAULT_LOOKBACK_DAYS = 30
# 时间范围上限：最早不超过 1 年（场景 03 §5.2）
MAX_LOOKBACK_DAYS = 365
# 单条回复最多展示的记录数，其余引导到任务列表
DISPLAY_LIMIT = 5
# 额度达到该值视为「不限额」（与规则引擎默认值一致）
UNLIMITED_QUOTA = 999

# 场景 03 §3.3 的意图规则：主体词 + 关注点同时命中才判定，避免「查询状态」这类
# 未指定类型的表述被随意归到某一类
_QUERY_TYPE_RULES: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    (
        QUERY_TYPE_EXPENSE_STATUS,
        re.compile(r"报销|费用|发票"),
        re.compile(r"状态|进度|哪一步|到哪|怎么样"),
    ),
    (
        QUERY_TYPE_LEAVE_BALANCE,
        re.compile(r"请假|年假|事假|病假|休假|调休"),
        re.compile(r"批|通过|剩余|余额|天数|还剩|几天"),
    ),
    (
        QUERY_TYPE_TASK_PROGRESS,
        re.compile(r"任务|采购|申请|流程|单据"),
        re.compile(r"进度|状态|哪一步|到哪|怎么样"),
    ),
)

# LLM 可能返回规范值、英文别名或裸业务词，统一映射
_QUERY_TYPE_ALIASES = {
    "任务进度": QUERY_TYPE_TASK_PROGRESS,
    "task_progress": QUERY_TYPE_TASK_PROGRESS,
    "task_status": QUERY_TYPE_TASK_PROGRESS,
    "假期余额": QUERY_TYPE_LEAVE_BALANCE,
    "leave_balance": QUERY_TYPE_LEAVE_BALANCE,
    "报销状态": QUERY_TYPE_EXPENSE_STATUS,
    "expense_status": QUERY_TYPE_EXPENSE_STATUS,
}

# 兜底关键词：只认明确的关注点或业务词，不认泛化的「状态」二字
_BALANCE_HINT_RE = re.compile(r"余额|剩余|还剩|几天|多少天|额度")
_EXPENSE_HINT_RE = re.compile(r"报销|费用|发票")
_TASK_HINT_RE = re.compile(r"任务|进度|申请|流程|采购|单据|办理")

# 单据号：MOCK-2046C424 / MOCK-F9D673BA / TK20240315001 / UUID。
# 注意受理号冒号后也是十六进制串，可能不以数字开头，不能要求分隔符后必须是数字。
_TASK_REF_RE = re.compile(
    r"\b(?:[A-Z]{2,6}-[A-Z0-9]{4,}"
    r"|[A-Z]{2}\d{6,}"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)

_STATUS_LABELS = {
    TaskStatus.PENDING: "待处理",
    TaskStatus.PROCESSING: "处理中",
    TaskStatus.APPROVING: "审批中",
    TaskStatus.COMPLETED: "已完成",
    TaskStatus.FAILED: "已驳回",
    TaskStatus.CANCELLED: "已取消",
}

# 审批记录状态与任务状态是两套取值（approvals.status 为普通字符串），
# 不能复用任务的标签：审批的 pending 是「待审」，approve 是「已通过」
_APPROVAL_LABELS = {
    ApprovalStatus.PENDING.value: "待审",
    ApprovalStatus.APPROVE.value: "已通过",
    ApprovalStatus.REJECT.value: "已驳回",
    ApprovalStatus.DONE.value: "已处理",
    ApprovalStatus.SKIPPED.value: "已跳过",
}

# 消息中出现的业务词 → 业务类型（顺序即优先级：先具体后笼统）
_BUSINESS_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("leave", re.compile(r"请假|年假|事假|病假|休假|调休")),
    ("expense", re.compile(r"报销|费用|发票")),
    ("travel", re.compile(r"差旅|出差")),
    ("seal", re.compile(r"用印|盖章|印章")),
    ("certificate", re.compile(r"证明")),
    ("meeting_room", re.compile(r"会议室")),
    ("vehicle", re.compile(r"用车|车辆|派车")),
    ("material", re.compile(r"物资")),
    ("asset", re.compile(r"资产|设备")),
    ("onboarding", re.compile(r"入职|离职")),
)

_TASK_TYPES_BY_VALUE = {member.value: member for member in TaskType}

# HR 余额字段 → 假期类型（开发桩与 HR 接口共用此口径）
_HR_BALANCE_KEYS = (
    ("annual", "年假"),
    ("compensatory", "调休"),
    ("personal", "事假"),
    ("sick", "病假"),
)


# ------------------------------------------------------------------ 纯函数


def normalize_query_type(*candidates: Optional[str]) -> Optional[str]:
    """把用户表述或 LLM 返回值归一为规范查询类型；无法判定返回 None。

    传入多个候选时按顺序优先：LLM 明确给出的类型优先于对用户原话的关键词推断——
    用户说「我的报销到哪一步了」而模型判定为任务进度时，以模型为准。
    """
    texts = [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
    if not texts:
        return None

    for text in texts:
        alias = _QUERY_TYPE_ALIASES.get(text.lower())
        if alias:
            return alias

    blob = " ".join(texts)
    for canonical in QUERY_TYPES:
        if canonical in blob:
            return canonical

    for canonical, subject_re, aspect_re in _QUERY_TYPE_RULES:
        if subject_re.search(blob) and aspect_re.search(blob):
            return canonical

    if _BALANCE_HINT_RE.search(blob):
        return QUERY_TYPE_LEAVE_BALANCE
    if _EXPENSE_HINT_RE.search(blob):
        return QUERY_TYPE_EXPENSE_STATUS
    if _TASK_HINT_RE.search(blob):
        return QUERY_TYPE_TASK_PROGRESS
    return None


def extract_task_ref(message: str) -> Optional[str]:
    """从消息里取出单据编号（受理号/任务号/UUID），用于精确查询。"""
    match = _TASK_REF_RE.search(message or "")
    return match.group(0) if match else None


def infer_business_type(message: str) -> Optional[str]:
    """从消息里识别用户关心的具体业务类型（业务值，与 TaskType 一致）。

    「我的请假批了吗」关心的只是请假，不该把报销单一起倒出来。
    """
    text = message or ""
    for business_type, pattern in _BUSINESS_KEYWORDS:
        if pattern.search(text):
            return business_type
    return None


@dataclass(frozen=True)
class TimeRange:
    """查询时间窗口。"""
    start: datetime
    end: datetime
    label: str


def resolve_time_range(message: str, *, now: Optional[datetime] = None) -> TimeRange:
    """解析自然语言时间范围；未提及则默认最近 30 天。

    只做「够用且可测」的解析：最近 N 天/月、上个月、本月、本周、今年、YYYY年M月。
    """
    now = now or utc_now()
    text = message or ""

    match = re.search(r"(?:最近|近|过去)\s*(\d{1,3})\s*天", text)
    if match:
        days = _clamp_days(int(match.group(1)))
        return _span(now, days, f"最近{days}天")

    match = re.search(r"(?:最近|近|过去)\s*(\d{1,2})\s*个?月", text)
    if match:
        days = _clamp_days(int(match.group(1)) * 30)
        return _span(now, days, f"最近{int(match.group(1))}个月")

    if re.search(r"上个?月|上月", text):
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = month_start - timedelta(seconds=1)
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return _clamp(TimeRange(start=start, end=end, label="上个月"), now)

    if re.search(r"本月|这个月|当月", text):
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return TimeRange(start=start, end=now, label="本月")

    if re.search(r"本周|这周|这一周", text):
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return TimeRange(start=start, end=now, label="本周")

    if re.search(r"今年|本年度|本年", text):
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return TimeRange(start=start, end=now, label="今年")

    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if not match:
        match = re.search(r"(\d{4})[-/](\d{1,2})(?![\d-])", text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            start = datetime(year, month, 1)
            end = (start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            return _clamp(TimeRange(start=start, end=end, label=f"{year}年{month}月"), now)

    return _span(now, DEFAULT_LOOKBACK_DAYS, f"最近{DEFAULT_LOOKBACK_DAYS}天")


def _clamp_days(days: int) -> int:
    return max(1, min(days, MAX_LOOKBACK_DAYS))


def _span(now: datetime, days: int, label: str) -> TimeRange:
    return TimeRange(start=now - timedelta(days=days), end=now, label=label)


def _clamp(span: TimeRange, now: datetime) -> TimeRange:
    """把窗口起点截断到 1 年内，并在标签里说明，避免用户误以为查了更早的数据。"""
    earliest = now - timedelta(days=MAX_LOOKBACK_DAYS)
    if span.start >= earliest:
        return span
    return TimeRange(
        start=earliest, end=span.end, label=f"{span.label}（最早只能查到 1 年前）"
    )


@dataclass(frozen=True)
class TaskView:
    """一条任务记录的展示视图（与 ORM 解耦，便于单测格式化逻辑）。"""
    title: str
    task_type: str
    status: str
    created_at: datetime
    amount: Optional[Decimal] = None
    pending_approvers: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeaveBalanceEntry:
    """一种假期的余额。"""
    leave_type: str
    quota: float
    used: float


def _format_moment(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def _format_amount(amount: Optional[Decimal]) -> str:
    return f"　￥{amount:.2f}" if amount is not None else ""


def _format_approvers(approvers: Sequence[str]) -> str:
    return f"（当前待 {'、'.join(approvers)} 审批）" if approvers else ""


def format_task_list(
    views: Sequence[TaskView], *, time_range: TimeRange, total: int, subject: str = ""
) -> str:
    """格式化任务列表回复；`subject` 为按业务收窄时的业务名（如「请假」）。"""
    if not views:
        scope = f"{subject}记录" if subject else "相关记录"
        return f"未找到{time_range.label}内的{scope}，请检查查询条件或换一个时间范围。"

    lines = [
        f"为您查询到本人{time_range.label}内的 {total} 条{subject}记录（按时间倒序）："
    ]
    for index, view in enumerate(views[:DISPLAY_LIMIT], 1):
        lines.append(
            f"{index}. {view.title}{_format_amount(view.amount)}｜{view.status}"
            f"{_format_approvers(view.pending_approvers)}｜提交于 {_format_moment(view.created_at)}"
        )
    if total > len(views[:DISPLAY_LIMIT]):
        lines.append(f"（仅显示最近 {min(DISPLAY_LIMIT, len(views))} 条，其余请到「我的任务」查看）")
    return "\n".join(lines)


def format_task_detail(
    view: TaskView, *, external_id: Optional[str], approvals: Sequence[tuple[int, str, str]]
) -> str:
    """格式化单个单据的详情（按单据编号精确查询）。"""
    lines = [f"任务「{view.title}」当前状态：{view.status}"]
    if external_id:
        lines.append(f"- 单据编号：{external_id}")
    if view.amount is not None:
        lines.append(f"- 金额：￥{view.amount:.2f}")
    lines.append(f"- 提交时间：{_format_moment(view.created_at)}")
    if approvals:
        chain = "；".join(f"第{step}步 {name}（{status}）" for step, name, status in approvals)
        lines.append(f"- 审批链：{chain}")
    return "\n".join(lines)


def format_leave_balance(
    entries: Sequence[LeaveBalanceEntry],
    *,
    pending: Sequence[TaskView],
    as_of: datetime,
    source: str,
) -> str:
    """格式化假期余额回复；在途请假单一并列出，否则「批了吗」得不到回答。"""
    lines = [f"您的假期余额（截至 {as_of:%Y-%m-%d}）："]
    for entry in entries:
        if entry.quota >= UNLIMITED_QUOTA:
            lines.append(f"- {entry.leave_type}：不限额度（本年已用 {_trim(entry.used)} 天）")
            continue
        remaining = max(entry.quota - entry.used, 0)
        lines.append(
            f"- {entry.leave_type}：剩余 {_trim(remaining)} 天"
            f"（额度 {_trim(entry.quota)} 天，本年已用 {_trim(entry.used)} 天）"
        )

    if pending:
        lines.append(f"另有 {len(pending)} 笔请假在途：")
        for view in pending[:DISPLAY_LIMIT]:
            lines.append(
                f"　· {view.title}{_format_approvers(view.pending_approvers)}"
                f"｜{view.status}｜提交于 {_format_moment(view.created_at)}"
            )

    lines.append(f"数据来源：{source}")
    return "\n".join(lines)


def _trim(value: float) -> str:
    """天数去掉无意义的小数尾巴（2.0 → 2，2.5 → 2.5）。"""
    text = f"{float(value):.1f}".rstrip("0").rstrip(".")
    return text or "0"


# ------------------------------------------------------------------ 服务


@dataclass(frozen=True)
class StatusQueryOutcome:
    """一次状态查询的结果信封（供 API 层落审计，不含用户内容）。"""
    content: str
    query_type: str
    result_count: int = 0


class StatusQueryService:
    """状态查询服务：按归属查库并生成自然语言答复。

    `tool_registry` 用于取假期余额（HR 工具）；为空或调用失败时回退本地默认额度。
    """

    def __init__(self, tool_registry: Any = None) -> None:
        self._tool_registry = tool_registry

    async def answer(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        slots: Optional[dict[str, Any]] = None,
        message: str = "",
        now: Optional[datetime] = None,
    ) -> StatusQueryOutcome:
        """执行一次状态查询。归属条件一律为当前用户本人（场景 03 §2）。"""
        now = now or utc_now()
        slots = slots or {}
        query_type = normalize_query_type(slots.get("query_type"), message)
        if query_type is None:
            return StatusQueryOutcome(content=ASK_QUERY_TYPE, query_type="")

        span = resolve_time_range(message, now=now)
        task_ref = slots.get("task_id") or extract_task_ref(message)
        if task_ref:
            return await self._answer_task_detail(db, user_id=user_id, task_ref=str(task_ref))

        if query_type == QUERY_TYPE_LEAVE_BALANCE:
            return await self._answer_leave_balance(db, user_id=user_id, now=now, span=span)

        # 报销状态固定看报销单；任务进度则按消息里点名的业务收窄（不点名才看全部）
        if query_type == QUERY_TYPE_EXPENSE_STATUS:
            task_type = TaskType.EXPENSE
        else:
            task_type = _TASK_TYPES_BY_VALUE.get(infer_business_type(message) or "")
        return await self._answer_task_list(
            db,
            user_id=user_id,
            span=span,
            task_type=task_type,
            subject=_TASK_TITLES.get(task_type.value, "") if task_type else "",
        )

    # -------------------------------------------------- 各查询类型

    async def _answer_task_list(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        span: TimeRange,
        task_type: Optional[TaskType],
        subject: str = "",
    ) -> StatusQueryOutcome:
        query = select(TaskModel).where(
            TaskModel.user_id == user_id,
            TaskModel.created_at >= span.start,
            TaskModel.created_at <= span.end,
        )
        if task_type is not None:
            query = query.where(TaskModel.type == task_type)

        total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (
            await db.execute(
                query.order_by(TaskModel.created_at.desc()).limit(DISPLAY_LIMIT)
            )
        ).scalars().all()

        approvers = await self._pending_approvers(db, [row.id for row in rows])
        views = [self._to_view(row, approvers.get(row.id, ())) for row in rows]
        label = QUERY_TYPE_EXPENSE_STATUS if task_type else QUERY_TYPE_TASK_PROGRESS
        return StatusQueryOutcome(
            content=format_task_list(views, time_range=span, total=total, subject=subject),
            query_type=label,
            result_count=total,
        )

    async def _answer_task_detail(
        self, db: AsyncSession, *, user_id: str, task_ref: str
    ) -> StatusQueryOutcome:
        """按单据编号精确查询；非本人单据一律拒绝（场景 03 TC010）。"""
        row = (
            await db.execute(
                select(TaskModel).where(
                    or_(TaskModel.id == task_ref, TaskModel.external_id == task_ref)
                )
            )
        ).scalars().first()

        if row is None:
            return StatusQueryOutcome(
                content="未找到该单据，请核对单据编号后重试。", query_type="", result_count=0
            )
        if row.user_id != user_id:
            logger.warning(
                "状态查询越权尝试", user_id=user_id, task_id=row.id
            )
            return StatusQueryOutcome(
                content="您没有权限查询此信息。", query_type="", result_count=0
            )

        approvals = (
            await db.execute(
                select(ApprovalModel, TaskModel)
                .join(TaskModel, TaskModel.id == ApprovalModel.task_id)
                .where(ApprovalModel.task_id == row.id)
                .order_by(ApprovalModel.step)
            )
        ).all()
        names = await self._approver_names(db, [a[0].approver_id for a in approvals])
        chain = [
            (item.step, names.get(item.approver_id, "审批人"), approval_status_label(item.status))
            for item, _ in approvals
        ]
        return StatusQueryOutcome(
            content=format_task_detail(
                self._to_view(row, ()), external_id=row.external_id, approvals=chain
            ),
            query_type=QUERY_TYPE_TASK_PROGRESS,
            result_count=1,
        )

    async def _answer_leave_balance(
        self, db: AsyncSession, *, user_id: str, now: datetime, span: TimeRange
    ) -> StatusQueryOutcome:
        entries, source = await self._leave_quota(user_id)
        year_span = TimeRange(
            start=now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
            end=now,
            label="今年",
        )
        used = await self._used_leave_days(db, user_id=user_id, span=year_span)
        merged = [
            LeaveBalanceEntry(
                leave_type=entry.leave_type,
                quota=entry.quota,
                used=used.get(entry.leave_type, entry.used),
            )
            for entry in entries
        ]

        pending = await self._pending_leave_tasks(db, user_id=user_id, span=span)
        return StatusQueryOutcome(
            content=format_leave_balance(
                merged, pending=pending, as_of=now, source=source
            ),
            query_type=QUERY_TYPE_LEAVE_BALANCE,
            result_count=len(pending),
        )

    # -------------------------------------------------- 数据访问

    async def _leave_quota(self, user_id: str) -> tuple[list[LeaveBalanceEntry], str]:
        """假期额度：优先 HR 系统，失败回退本地默认额度并如实标注来源。"""
        tool = self._tool_registry.get_tool("leave") if self._tool_registry else None
        if tool is not None:
            try:
                result = await tool.execute({"action": "query_leave_balance"}, user_id)
                if not result.is_error:
                    entries = _balance_entries(_parse_tool_payload(result))
                    if entries:
                        return entries, "HR 系统"
            except Exception as exc:  # noqa: BLE001 - HR 不可用不得阻断查询
                logger.warning("HR 假期余额查询失败，回退本地默认额度", error=str(exc))

        fallback = [
            LeaveBalanceEntry(leave_type=leave_type, quota=float(quota), used=0.0)
            for leave_type, quota in DEFAULT_LEAVE_BALANCE.items()
        ]
        return fallback, "本地默认额度（HR 系统暂时不可用，数据可能不是最新）"

    async def _used_leave_days(
        self, db: AsyncSession, *, user_id: str, span: TimeRange
    ) -> dict[str, float]:
        """本年已用天数：按已完成的请假单汇总（含首含尾，与规则引擎口径一致）。"""
        rows = (
            await db.execute(
                select(TaskModel).where(
                    TaskModel.user_id == user_id,
                    TaskModel.type == TaskType.LEAVE,
                    TaskModel.status == TaskStatus.COMPLETED,
                    TaskModel.created_at >= span.start,
                    TaskModel.created_at <= span.end,
                )
            )
        ).scalars().all()

        used: dict[str, float] = {}
        for row in rows:
            data = row.data or {}
            leave_type = data.get("leave_type")
            days = _leave_days(data)
            if leave_type and days:
                used[str(leave_type)] = used.get(str(leave_type), 0.0) + days
        return used

    async def _pending_leave_tasks(
        self, db: AsyncSession, *, user_id: str, span: TimeRange
    ) -> list[TaskView]:
        rows = (
            await db.execute(
                select(TaskModel)
                .where(
                    TaskModel.user_id == user_id,
                    TaskModel.type == TaskType.LEAVE,
                    TaskModel.status.in_((TaskStatus.APPROVING, TaskStatus.PROCESSING)),
                    TaskModel.created_at >= span.start,
                    TaskModel.created_at <= span.end,
                )
                .order_by(TaskModel.created_at.desc())
                .limit(DISPLAY_LIMIT)
            )
        ).scalars().all()

        approvers = await self._pending_approvers(db, [row.id for row in rows])
        return [self._to_view(row, approvers.get(row.id, ())) for row in rows]

    async def _pending_approvers(
        self, db: AsyncSession, task_ids: Iterable[str]
    ) -> dict[str, tuple[str, ...]]:
        """在途单据当前待审人姓名（用户问「到哪一步了」，指向的就是他们）。"""
        ids = [task_id for task_id in task_ids if task_id]
        if not ids:
            return {}
        rows = (
            await db.execute(
                select(ApprovalModel.task_id, UserModel.name)
                .join(UserModel, UserModel.id == ApprovalModel.approver_id)
                .where(
                    ApprovalModel.task_id.in_(ids),
                    ApprovalModel.status == ApprovalStatus.PENDING.value,
                )
                .order_by(ApprovalModel.step)
            )
        ).all()

        grouped: dict[str, list[str]] = {}
        for task_id, name in rows:
            grouped.setdefault(task_id, []).append(name or "审批人")
        return {task_id: tuple(names) for task_id, names in grouped.items()}

    async def _approver_names(
        self, db: AsyncSession, user_ids: Iterable[str]
    ) -> dict[str, str]:
        ids = [user_id for user_id in user_ids if user_id]
        if not ids:
            return {}
        rows = (
            await db.execute(
                select(UserModel.id, UserModel.name).where(UserModel.id.in_(ids))
            )
        ).all()
        return {user_id: name or "审批人" for user_id, name in rows}

    @staticmethod
    def _to_view(row: TaskModel, approvers: tuple[str, ...]) -> TaskView:
        data = row.data or {}
        amount = data.get("amount")
        title = row.title or _TASK_TITLES.get(_enum_value(row.type), "行政事务")
        return TaskView(
            title=title,
            task_type=_enum_value(row.type) or "",
            status=_label(_enum_value(row.status)),
            created_at=row.created_at,
            amount=_to_decimal(amount),
            pending_approvers=approvers,
        )


_TASK_TITLES = {
    "leave": "请假",
    "expense": "报销",
    "travel": "差旅",
    "meeting_room": "会议室预定",
    "vehicle": "车辆预定",
    "material": "物资领用",
    "asset": "资产领用/归还",
    "seal": "用印",
    "certificate": "证明开具",
    "onboarding": "入离职办理",
}


def _enum_value(value: Any) -> Optional[str]:
    return value.value if hasattr(value, "value") else (str(value) if value else None)


def _label(status: Optional[str]) -> str:
    """任务状态转中文；未知取值原样返回，不吞掉信息。"""
    for member, label in _STATUS_LABELS.items():
        if member.value == status:
            return label
    return status or "未知"


def approval_status_label(status: Optional[str]) -> str:
    """审批记录状态转中文（与任务状态取值不同，见 `_APPROVAL_LABELS`）。"""
    if not status:
        return "未知"
    return _APPROVAL_LABELS.get(status, status)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _leave_days(data: dict[str, Any]) -> float:
    """请假天数（含首含尾）；显式给了 days 就优先用它。"""
    days = data.get("days")
    if isinstance(days, (int, float)) and days > 0:
        return float(days)
    try:
        start = datetime.strptime(str(data.get("start_date")), "%Y-%m-%d")
        end = datetime.strptime(str(data.get("end_date")), "%Y-%m-%d")
    except (TypeError, ValueError):
        return 0.0
    span = (end - start).days + 1
    return float(span) if span > 0 else 0.0


def _parse_tool_payload(result: Any) -> dict[str, Any]:
    """把工具返回的文本解析为响应体（解析不出时返回空字典，由调用方走降级）。"""
    return parse_downstream_payload(getattr(result, "text_content", "") or "")


def _balance_entries(payload: dict[str, Any]) -> list[LeaveBalanceEntry]:
    """从 HR 响应里取各假期额度；全部缺失时返回空列表以触发降级。"""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    entries: list[LeaveBalanceEntry] = []
    for key, leave_type in _HR_BALANCE_KEYS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            continue
        entries.append(
            LeaveBalanceEntry(leave_type=leave_type, quota=float(value), used=0.0)
        )
    return entries
