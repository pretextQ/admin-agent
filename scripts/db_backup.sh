#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
#
# 数据库备份 / 恢复（PostgreSQL）
#
# 用途：把 admin_ai 库（用户、会话、任务、审批、审计、知识库文档）导出为
#      纯 SQL 文件，换机器后重新导入，避免本机数据随机器一起丢掉。
#
# 用法：
#   bash scripts/db_backup.sh                     # 备份到 backups/ 带时间戳
#   bash scripts/db_backup.sh list                # 列出已有备份
#   bash scripts/db_backup.sh restore <文件名>     # 从备份恢复（覆盖现有数据）
#
# 换机迁移建议顺序：本机 backup → 把 backups/*.sql 拷到新机 →
#   新机执行 bash scripts/setup_dev_env.sh → 再 restore。
# 注意：向量库（data/chroma）与嵌入模型不在本备份内，需重建索引。

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-D:/NF/Tools}"
PG_BIN="$TOOLS_DIR/pgsql/pgsql/bin"
BACKUP_DIR="$PROJECT_ROOT/backups"
DB_NAME="admin_ai"
PG_HOST="127.0.0.1"

export MSYS_NO_PATHCONV=1
# 库内含中文数据：客户端编码必须是 UTF8，否则导入报 "invalid byte sequence for encoding UTF8"（有前科）
export PGCLIENTENCODING=UTF8

if [ ! -x "$PG_BIN/pg_dump.exe" ]; then
    echo "[FAIL] 找不到 pg_dump：$PG_BIN/pg_dump.exe（可设 TOOLS_DIR 覆盖）"
    exit 1
fi

if ! "$PG_BIN/pg_isready.exe" -h "$PG_HOST" -p 5432 >/dev/null 2>&1; then
    echo "[FAIL] PostgreSQL 未运行。先执行 bash scripts/setup_dev_env.sh"
    exit 1
fi

case "${1:-backup}" in
    backup)
        mkdir -p "$BACKUP_DIR"
        stamp="$(date +%Y%m%d_%H%M%S)"
        file="$BACKUP_DIR/${DB_NAME}_${stamp}.sql"
        if "$PG_BIN/pg_dump.exe" -h "$PG_HOST" -U postgres -d "$DB_NAME" \
                --no-owner --no-privileges > "$file" 2>/dev/null; then
            size="$(du -h "$file" | cut -f1)"
            echo "[OK] 已备份：$file（$size）"
            echo "     换机器时把该文件带走，新机执行：bash scripts/db_backup.sh restore ${DB_NAME}_${stamp}.sql"
        else
            echo "[FAIL] 备份失败（确认库名 $DB_NAME 存在）"
            exit 1
        fi
        ;;

    list)
        if [ -d "$BACKUP_DIR" ]; then
            ls -lh "$BACKUP_DIR"/*.sql 2>/dev/null || echo "（暂无备份）"
        else
            echo "（暂无备份）"
        fi
        ;;

    restore)
        file="${2:-}"
        [ -z "$file" ] && { echo "用法：bash scripts/db_backup.sh restore <文件名>"; exit 1; }
        # 允许传相对 backups/ 的文件名或完整路径
        [ -f "$file" ] || file="$BACKUP_DIR/$file"
        if [ ! -f "$file" ]; then
            echo "[FAIL] 备份文件不存在：$file"
            exit 1
        fi

        # 恢复前自动快照当前数据：DROP 后若导入失败可回滚（有前科）
        table_count="$("$PG_BIN/psql.exe" -h "$PG_HOST" -U postgres -d "$DB_NAME" -tAc \
            "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null)"
        if [ "${table_count:-0}" -gt 0 ]; then
            mkdir -p "$BACKUP_DIR"
            snapshot="$BACKUP_DIR/pre-restore_$(date +%Y%m%d_%H%M%S).sql"
            "$PG_BIN/pg_dump.exe" -h "$PG_HOST" -U postgres -d "$DB_NAME" \
                --no-owner --no-privileges > "$snapshot" 2>/dev/null \
                && echo "[OK] 已生成恢复前快照：$snapshot"
        fi

        echo "  清空现有表并导入 ..."
        "$PG_BIN/psql.exe" -h "$PG_HOST" -U postgres -d "$DB_NAME" -q \
            -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
        # psql 是 Windows 程序：路径需转成 Windows 形式（MSYS 路径会被当作盘符相对路径）
        win_file="$(cygpath -w "$file" 2>/dev/null || echo "$file")"
        if "$PG_BIN/psql.exe" -h "$PG_HOST" -U postgres -d "$DB_NAME" \
                -v ON_ERROR_STOP=1 -f "$win_file" >/dev/null 2>"$BACKUP_DIR/.restore_err.log"; then
            rm -f "$BACKUP_DIR/.restore_err.log"
            echo "[OK] 已恢复：$file"
            echo "     提醒：向量库需重建索引（重新上传知识文档或跑重建脚本）"
        else
            echo "[FAIL] 恢复失败，错误摘要："
            head -3 "$BACKUP_DIR/.restore_err.log" | sed 's/^/       /'
            if [ -n "${snapshot:-}" ] && [ -f "$snapshot" ]; then
                echo "     数据可回滚：bash scripts/db_backup.sh restore $(basename "$snapshot")"
            fi
            exit 1
        fi
        ;;

    *)
        echo "用法：bash scripts/db_backup.sh [backup|list|restore <文件名>]"
        exit 1
        ;;
esac
