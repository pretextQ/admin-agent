# Copyright 2026  Admin AI Team, All rights reserved.
"""审批规则维护脚本（评审 B-2 / 决策 D-5：首期维护入口 = 脚本 + API）。

审批规则决定「按业务类型 + 金额把审批路由给谁」。首期不做管理后台 UI（评审 I-3 归属待定），
行政/财务用本脚本维护，同等的 HTTP 入口在 `/admin/approval-rules`。

用法：
    PYTHONPATH=. python scripts/manage_approval_rules.py list
    PYTHONPATH=. python scripts/manage_approval_rules.py add \\
        --business-type expense --approver-type parent_dept_manager \\
        --amount-min 2000 --step-order 1 --remark "APR-002 总监审批"
    PYTHONPATH=. python scripts/manage_approval_rules.py disable --id <rule_id>
    PYTHONPATH=. python scripts/manage_approval_rules.py export --out data/approval_rules.csv
    PYTHONPATH=. python scripts/manage_approval_rules.py import --file data/approval_rules.csv

`approver_type` 取值：self_dept_manager（本部门主管）/ parent_dept_manager（上级部门主管）/
top_dept_manager（顶层部门主管）/ role（需 --param，如 finance）/ user（需 --param，用户 ID）。
`--mode all_must` 表示会签（默认 any_one 任一人通过）。金额区间为「含 min、不含 max」，留空表示无界。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.approval.conditions import ConditionError, validate_conditions
from app.admin_ai.db.database import get_session_factory
from app.admin_ai.db.models import ApprovalMode, ApprovalRuleModel, ApproverType, generate_uuid

CSV_HEADERS = [
    "business_type",
    "condition",
    "amount_min",
    "amount_max",
    "step_order",
    "approver_type",
    "approver_param",
    "approval_mode",
    "required",
    "enabled",
    "remark",
]


def _decimal(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise SystemExit(f"金额格式非法：{value}") from exc


def _parse_condition(raw: str | None) -> list[dict] | None:
    """解析条件参数：JSON 字符串 → 条件列表；非法直接退出并说明用法。"""
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"条件不是合法 JSON：{exc}") from exc
    try:
        validate_conditions(parsed)
    except ConditionError as exc:
        raise SystemExit(f"条件非法：{exc}") from exc
    return parsed if isinstance(parsed, list) else [parsed]


def _format_condition(condition) -> str:
    """条件渲染成简短可读形式，如 days<=2、seal_type=合同章。"""
    if not condition:
        return "-"
    items = condition if isinstance(condition, list) else [condition]
    parts = []
    for item in items:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        symbol = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}.get(
            item.get("op"), str(item.get("op"))
        )
        parts.append(f"{item.get('slot')}{symbol}{item.get('value')}")
    return " 且 ".join(parts)


def _dump(rule: ApprovalRuleModel) -> dict[str, str]:
    return {
        "id": rule.id,
        "business_type": rule.business_type,
        "amount_min": "" if rule.amount_min is None else str(rule.amount_min),
        "amount_max": "" if rule.amount_max is None else str(rule.amount_max),
        "step_order": str(rule.step_order),
        "condition": json.dumps(rule.condition, ensure_ascii=False) if rule.condition else "",
        "approver_type": rule.approver_type.value,
        "approver_param": rule.approver_param or "",
        "approval_mode": rule.approval_mode.value,
        "required": "true" if rule.required else "false",
        "enabled": "true" if rule.enabled else "false",
        "remark": rule.remark or "",
    }


async def cmd_list(db: AsyncSession, args: argparse.Namespace) -> int:
    query = select(ApprovalRuleModel).order_by(
        ApprovalRuleModel.business_type, ApprovalRuleModel.step_order
    )
    if args.business_type:
        query = query.where(ApprovalRuleModel.business_type == args.business_type)
    rules = (await db.execute(query)).scalars().all()
    if not rules:
        print("暂无审批规则。")
        return 0
    print(
        f"{'ID':<38}{'业务':<10}{'金额区间':<20}{'步':<3}{'审批人':<22}{'条件':<24}{'状态':<6}备注"
    )
    for rule in rules:
        if rule.amount_min is None and rule.amount_max is None:
            amount = "无金额"
        else:
            low = "0" if rule.amount_min is None else str(rule.amount_min)
            high = "+∞" if rule.amount_max is None else str(rule.amount_max)
            amount = f"[{low}, {high})"
        approver = rule.approver_type.value + (
            f":{rule.approver_param}" if rule.approver_param else ""
        )
        state = "启用" if rule.enabled else "停用"
        condition = _format_condition(rule.condition)
        print(
            f"{rule.id:<38}{rule.business_type:<10}{amount:<20}{rule.step_order:<3}"
            f"{approver:<22}{condition:<24}{state:<6}{rule.remark or ''}"
        )
    return 0


async def cmd_add(db: AsyncSession, args: argparse.Namespace) -> int:
    condition = _parse_condition(args.condition)
    rule = ApprovalRuleModel(
        id=generate_uuid(),
        business_type=args.business_type,
        amount_min=_decimal(args.amount_min),
        amount_max=_decimal(args.amount_max),
        step_order=args.step_order,
        approver_type=ApproverType(args.approver_type),
        approver_param=args.param,
        approval_mode=ApprovalMode(args.mode),
        required=not args.optional,
        condition=condition,
        remark=args.remark,
    )
    db.add(rule)
    await db.commit()
    print(f"已新增规则 {rule.id}")
    print("提示：规则变更后新提交的单据即按新规则路由，在途审批仍按其生成时的链继续。")
    return 0


async def cmd_toggle(db: AsyncSession, args: argparse.Namespace, *, enabled: bool) -> int:
    rule = (
        await db.execute(select(ApprovalRuleModel).where(ApprovalRuleModel.id == args.id))
    ).scalar_one_or_none()
    if rule is None:
        print(f"规则不存在：{args.id}")
        return 1
    rule.enabled = enabled
    await db.commit()
    print(f"规则 {rule.id} 已{'启用' if enabled else '停用'}")
    return 0


async def cmd_delete(db: AsyncSession, args: argparse.Namespace) -> int:
    rule = (
        await db.execute(select(ApprovalRuleModel).where(ApprovalRuleModel.id == args.id))
    ).scalar_one_or_none()
    if rule is None:
        print(f"规则不存在：{args.id}")
        return 1
    await db.delete(rule)
    await db.commit()
    print(f"规则 {args.id} 已删除")
    return 0


async def cmd_export(db: AsyncSession, args: argparse.Namespace) -> int:
    rules = (
        await db.execute(
            select(ApprovalRuleModel).order_by(
                ApprovalRuleModel.business_type, ApprovalRuleModel.step_order
            )
        )
    ).scalars().all()
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS)
    writer.writeheader()
    for rule in rules:
        row = _dump(rule)
        writer.writerow({key: row[key] for key in CSV_HEADERS})
    text = buffer.getvalue()
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"已导出 {len(rules)} 条规则到 {path}")
    else:
        print(text)
    return 0


async def cmd_import(db: AsyncSession, args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"文件不存在：{path}")
        return 1
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    if not rows:
        print("文件为空，未做任何修改。")
        return 1

    # 按文件里出现的业务类型整体替换：让人能对着表格一眼看出「这类业务的审批链是什么」
    business_types = {(row.get("business_type") or "").strip() for row in rows}
    business_types.discard("")
    if not business_types:
        print("缺少 business_type 列，未做任何修改。")
        return 1

    existing = (
        await db.execute(
            select(ApprovalRuleModel).where(
                ApprovalRuleModel.business_type.in_(business_types)
            )
        )
    ).scalars().all()
    for rule in existing:
        await db.delete(rule)

    created = 0
    for row in rows:
        business_type = (row.get("business_type") or "").strip()
        approver_type = (row.get("approver_type") or "").strip()
        if not business_type or not approver_type:
            continue
        db.add(
            ApprovalRuleModel(
                id=generate_uuid(),
                business_type=business_type,
                amount_min=_decimal(row.get("amount_min")),
                amount_max=_decimal(row.get("amount_max")),
                step_order=int(row.get("step_order") or 1),
                approver_type=ApproverType(approver_type),
                approver_param=(row.get("approver_param") or "").strip() or None,
                condition=_parse_condition(row.get("condition")),
                approval_mode=ApprovalMode((row.get("approval_mode") or "any_one").strip()),
                required=(row.get("required") or "true").strip().lower() != "false",
                enabled=(row.get("enabled") or "true").strip().lower() != "false",
                remark=(row.get("remark") or "").strip() or None,
            )
        )
        created += 1
    await db.commit()
    print(
        f"已导入 {created} 条规则（{', '.join(sorted(business_types))}），"
        f"替换掉原有 {len(existing)} 条。"
    )
    return 0


async def main(args: argparse.Namespace) -> int:
    factory = get_session_factory()
    async with factory() as db:
        if args.command == "list":
            return await cmd_list(db, args)
        if args.command == "add":
            return await cmd_add(db, args)
        if args.command == "enable":
            return await cmd_toggle(db, args, enabled=True)
        if args.command == "disable":
            return await cmd_toggle(db, args, enabled=False)
        if args.command == "delete":
            return await cmd_delete(db, args)
        if args.command == "export":
            return await cmd_export(db, args)
        if args.command == "import":
            return await cmd_import(db, args)
        print(f"未知命令：{args.command}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="审批路由规则维护（脚本入口，API 见 /admin/approval-rules）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出规则")
    p_list.add_argument("--business-type", default=None)

    p_add = sub.add_parser("add", help="新增规则")
    p_add.add_argument("--business-type", required=True)
    p_add.add_argument(
        "--approver-type",
        required=True,
        choices=[t.value for t in ApproverType],
    )
    p_add.add_argument("--amount-min", default=None, help="区间下界（含），留空表示无界")
    p_add.add_argument("--amount-max", default=None, help="区间上界（不含），留空表示无界")
    p_add.add_argument("--step-order", type=int, default=1, help="审批顺序，从 1 开始")
    p_add.add_argument("--param", default=None, help="role 的角色名或 user 的用户 ID")
    p_add.add_argument("--mode", default=ApprovalMode.ANY_ONE.value, choices=[m.value for m in ApprovalMode])
    p_add.add_argument("--optional", action="store_true", help="标记为非必需步骤（解析不出时跳过）")
    p_add.add_argument(
        "--condition",
        default=None,
        help=(
            '按槽位分支的条件（JSON），例如 [{"slot":"days","op":"gt","value":2}]；'
            "算子支持 eq/ne/gt/gte/lt/lte/in/not_in"
        ),
    )
    p_add.add_argument("--remark", default=None)

    for name in ("enable", "disable", "delete"):
        p = sub.add_parser(name, help=f"{name} 规则")
        p.add_argument("--id", required=True)

    p_export = sub.add_parser("export", help="导出为 CSV")
    p_export.add_argument("--out", default=None, help="输出文件路径；留空打印到标准输出")

    p_import = sub.add_parser("import", help="从 CSV 导入（按业务类型整体替换）")
    p_import.add_argument("--file", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(build_parser().parse_args())))
