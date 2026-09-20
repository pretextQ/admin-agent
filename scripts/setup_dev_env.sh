#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
#
# Admin AI Agent 开发环境一键重建（Windows + Git Bash）
#
# 用途：换一台机器后，clone 仓库并执行本脚本即可恢复到可开发/可测试状态。
#      幂等设计——已就绪的步骤会跳过，可反复执行。
#
# 用法：
#   bash scripts/setup_dev_env.sh              # 完整重建（缺什么装什么）
#   bash scripts/setup_dev_env.sh --check      # 只做体检，不安装
#   TOOLS_DIR=E:/Tools bash scripts/setup_dev_env.sh   # 换工具目录
#
# 依赖的本机资产（均可用 TOOLS_DIR 覆盖，默认 D:/NF/Tools 与 D:/NF/Redis）：
#   $TOOLS_DIR/uv.exe                 uv（Python 包管理，独立二进制）
#   $TOOLS_DIR/pgsql/pgsql/bin        PostgreSQL 16 绿色二进制
#   $TOOLS_DIR/pgsql/pgdata           PG 数据目录
#   $REDIS_DIR/redis-server.exe       Redis for Windows
#
# 说明：PostgreSQL / Redis 均为绿色版（非 Windows 服务），重启机器后需重新拉起；
#      本脚本会检测并拉起。详细踩坑见 docs/项目当前状况与交接说明.md §2/§6。

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-D:/NF/Tools}"
REDIS_DIR="${REDIS_DIR:-D:/NF/Redis}"
UV_EXE="$TOOLS_DIR/uv.exe"
PG_BIN="$TOOLS_DIR/pgsql/pgsql/bin"
PG_DATA="$TOOLS_DIR/pgsql/pgdata"
PG_ZIP_URL="https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip"
PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
GH_PROXY="https://ghfast.top/"
UV_VERSION="0.8.4"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# Windows 原生命令需要禁用 MSYS 路径转换，且路径用 D:/xxx 形式
export MSYS_NO_PATHCONV=1

pass=0; fail=0; skipped=0
ok()   { echo "  [OK]   $1"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $1"; fail=$((fail+1)); }
skip() { echo "  [SKIP] $1"; skipped=$((skipped+1)); }
step() { echo; echo "== $1 =="; }

# ---------------------------------------------------------------- 1. uv
step "1/7 uv（Python 运行时管理）"
if [ -x "$UV_EXE" ]; then
    ok "uv 已就绪：$("$UV_EXE" --version 2>&1 | head -1)"
elif [ "$CHECK_ONLY" = "1" ]; then
    bad "uv 缺失：$UV_EXE（重跑不加 --check 可自动下载）"
else
    echo "  下载 uv $UV_VERSION ..."
    mkdir -p "$TOOLS_DIR"
    if curl -sL -m 120 -o "$TOOLS_DIR/uv.zip" \
        "${GH_PROXY}https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-pc-windows-msvc.zip" \
        && (cd "$TOOLS_DIR" && unzip -o -q uv.zip) ; then
        ok "uv 安装完成：$("$UV_EXE" --version 2>&1 | head -1)"
    else
        bad "uv 下载失败（检查 ghfast.top 可达性）"
    fi
fi

# ------------------------------------------------------- 2. venv 与依赖
step "2/7 Python 虚拟环境与依赖"
if [ ! -x "$UV_EXE" ]; then
    bad "跳过：uv 不可用"
elif [ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    ver="$("$PROJECT_ROOT/.venv/Scripts/python.exe" --version 2>&1)"
    ok "venv 已存在：$ver"
else
    if [ "$CHECK_ONLY" = "1" ]; then
        bad ".venv 缺失（重跑不加 --check 可自动创建）"
    else
        echo "  创建 venv（Python 3.12）+ 安装依赖 ..."
        (cd "$PROJECT_ROOT" \
            && "$UV_EXE" venv --python 3.12 \
            && "$UV_EXE" pip install -r requirements-dev.txt --index-url "$PYPI_MIRROR") \
            && ok "依赖安装完成" || bad "依赖安装失败"
    fi
fi

# ---------------------------------------------------------- 3. .env 配置
step "3/7 .env 配置"
if [ -f "$PROJECT_ROOT/.env" ]; then
    ok ".env 已存在"
elif [ "$CHECK_ONLY" = "1" ]; then
    bad ".env 缺失（可从 .env.example 复制，并填 OPENAI_API_KEY）"
else
    sec="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    sed "s/^SECRET_KEY=.*/SECRET_KEY=$sec/" "$PROJECT_ROOT/.env.example" > "$PROJECT_ROOT/.env"
    ok ".env 已从模板生成（SECRET_KEY 已随机化；OPENAI_API_KEY 留空则走规则回退）"
fi

# ------------------------------------------------------- 4. PostgreSQL
step "4/7 PostgreSQL"
if [ -x "$PG_BIN/pg_isready.exe" ] && "$PG_BIN/pg_isready.exe" -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    ok "PG 运行中（127.0.0.1:5432）"
elif [ ! -x "$PG_BIN/pg_ctl.exe" ]; then
    if [ "$CHECK_ONLY" = "1" ]; then
        bad "PG 二进制缺失：$PG_BIN（重跑不加 --check 可自动下载并初始化）"
    else
        echo "  下载 PostgreSQL 16.4 绿色二进制（约 340MB）..."
        mkdir -p "$TOOLS_DIR/pgsql"
        if curl -sL -m 590 -o "$TOOLS_DIR/pgsql.zip" "$PG_ZIP_URL" \
            && unzip -o -q "$TOOLS_DIR/pgsql.zip" -d "$TOOLS_DIR/pgsql" ; then
            "$PG_BIN/initdb.exe" -D "$PG_DATA" -U postgres --auth=trust -E UTF8 --locale=C >/dev/null \
                && ok "PG 初始化完成（数据目录 $PG_DATA）" || bad "initdb 失败"
        else
            bad "PG 下载失败（检查 get.enterprisedb.com 可达性）"
        fi
    fi
elif [ "$CHECK_ONLY" = "1" ]; then
    bad "PG 未运行（拉起：$PG_BIN/pg_ctl.exe -D \"$PG_DATA\" -l \"$TOOLS_DIR/pgsql/pg.log\" start）"
else
    echo "  拉起 PG ..."
    "$PG_BIN/pg_ctl.exe" -D "$PG_DATA" -l "$TOOLS_DIR/pgsql/pg.log" start >/dev/null 2>&1
    sleep 3
    "$PG_BIN/pg_isready.exe" -h 127.0.0.1 -p 5432 >/dev/null 2>&1 \
        && ok "PG 已拉起" || bad "PG 启动失败（看 $TOOLS_DIR/pgsql/pg.log）"
fi

# ------------------------------------------------------------ 5. Redis
step "5/7 Redis"
if [ -x "$REDIS_DIR/redis-cli.exe" ] && "$REDIS_DIR/redis-cli.exe" ping >/dev/null 2>&1; then
    ok "Redis 运行中（127.0.0.1:6379）"
elif [ ! -x "$REDIS_DIR/redis-server.exe" ]; then
    bad "Redis 缺失：$REDIS_DIR（下载 tporadowski/redis 的 Windows 版后置于该目录）"
elif [ "$CHECK_ONLY" = "1" ]; then
    bad "Redis 未运行（拉起：cd $REDIS_DIR && ./redis-server.exe --bind 127.0.0.1 --port 6379 --save \"\" --appendonly no）"
else
    echo "  拉起 Redis ..."
    ( cd "$REDIS_DIR" && ./redis-server.exe --bind 127.0.0.1 --port 6379 --save "" --appendonly no >/dev/null 2>&1 & )
    sleep 2
    "$REDIS_DIR/redis-cli.exe" ping >/dev/null 2>&1 && ok "Redis 已拉起" || bad "Redis 启动失败"
fi

# --------------------------------------------------- 6. 建库 / 迁移 / 种子
step "6/7 数据库表结构与种子数据"
if [ ! -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    bad "跳过：venv 不可用"
elif ! "$PG_BIN/pg_isready.exe" -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
    bad "跳过：PG 未运行"
else
    "$PG_BIN/psql.exe" -h 127.0.0.1 -U postgres -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw admin_ai \
        || "$PG_BIN/createdb.exe" -h 127.0.0.1 -U postgres admin_ai 2>/dev/null
    if [ "$CHECK_ONLY" = "1" ]; then
        "$PG_BIN/psql.exe" -h 127.0.0.1 -U postgres -d admin_ai -tAc \
            "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null \
            | grep -q '[1-9]' && ok "库表已存在" || bad "库表缺失（执行：.venv/Scripts/python.exe -m alembic upgrade head）"
    elif ( cd "$PROJECT_ROOT" \
            && PYTHONPATH=. .venv/Scripts/python.exe -m alembic upgrade head >/dev/null 2>&1 \
            && PYTHONPATH=. .venv/Scripts/python.exe scripts/seed_admin.py >/dev/null 2>&1 \
            && PYTHONPATH=. .venv/Scripts/python.exe scripts/seed_org_demo.py >/dev/null 2>&1 ) ; then
        ok "迁移与种子数据就绪（admin001 + 演示组织：公司/技术部）"
    else
        bad "迁移或种子失败——手动执行排查：.venv/Scripts/python.exe -m alembic upgrade head"
    fi
fi

# ------------------------------------------------------------- 7. 核验
step "7/7 核验"
if [ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    ( cd "$PROJECT_ROOT" && .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -1 )
    echo "  提示：端到端冒烟需先起开发桩与后端（README 快速开始），再跑 scripts/e2e_smoke.py"
else
    bad "跳过：venv 不可用"
fi

# ------------------------------------------------------------- 汇总
echo
echo "================================================"
echo " 就绪 $pass 项 | 失败 $fail 项 | 跳过 $skipped 项"
if [ "$fail" -gt 0 ]; then
    echo " 有未就绪项，按上面 [FAIL] 提示处理后重跑本脚本（幂等）。"
    exit 1
fi
echo " 环境就绪。起服务见 docs/项目当前状况与交接说明.md §2。"
echo "================================================"
