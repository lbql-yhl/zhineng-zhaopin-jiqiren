#!/usr/bin/env python3
"""Send XiaoZhao unfinished xq/bug report to Feishu."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from feishu_gateway import FeishuSendError, read_secret, send_post_message
except ModuleNotFoundError:
    class FeishuSendError(RuntimeError):
        detail: dict[str, Any] = {}

    def read_secret() -> str | None:
        return None

    def send_post_message(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"code": -1, "error": "feishu_gateway.py not found"}


DEFAULT_APP_ID = "cli_aa8878662d62dbee"
DEFAULT_CHAT_ID = "oc_606e61cfefd9cfb4b88409f0a480ad1d"
YE_HAILIN_OPEN_ID = "ou_be28de7519471294e523a2708caa6190"


def default_db_candidates() -> list[Path]:
    root = SCRIPT_DIR.parents[2]
    return [
        root / ".zhipin-copilot" / "recruitment.sqlite3",
        root / "data" / ".zhipin-copilot" / "recruitment.sqlite3",
    ]


def resolve_default_db() -> Path:
    for candidate in default_db_candidates():
        if candidate.exists():
            return candidate
    return default_db_candidates()[0]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def fetch_unfinished(conn: sqlite3.Connection, table: str, label: str) -> list[dict[str, Any]]:
    if not table_exists(conn, table):
        return []
    rows = conn.execute(
        f"""
        SELECT id, optimized_summary, original_text, status, created_at
        FROM {table}
        WHERE status NOT IN ('COMPLETED', 'CLOSED')
        ORDER BY id ASC
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        summary = (row["optimized_summary"] or row["original_text"] or "").strip()
        if len(summary) > 90:
            summary = summary[:87] + "..."
        result.append(
            {
                "type": label,
                "id": int(row["id"]),
                "status": row["status"] or "RECORDED",
                "created_at": row["created_at"] or "",
                "summary": summary or "<无摘要>",
            }
        )
    return result


def build_report(items: list[dict[str, Any]], report_date: str) -> str:
    bug_count = sum(1 for item in items if item["type"] == "Bug单")
    xq_count = sum(1 for item in items if item["type"] == "需求单")
    lines = [
        f"小昭未完成工单合并报表：{report_date}",
        f"未完成合计：{len(items)} 个（需求 {xq_count} 个，Bug {bug_count} 个）",
        "",
    ]
    if not items:
        lines.append("当前没有未完成的需求单或Bug单。")
        return "\n".join(lines)
    for item in items:
        lines.append(
            f"- {item['type']} #{item['id']}｜{item['status']}｜{item['created_at']}｜{item['summary']}"
        )
    return "\n".join(lines)


def build_post_lines(items: list[dict[str, Any]], report_date: str) -> list[list[dict[str, Any]]]:
    bug_count = sum(1 for item in items if item["type"] == "Bug单")
    xq_count = sum(1 for item in items if item["type"] == "需求单")
    lines: list[list[dict[str, Any]]] = [
        [
            {"tag": "at", "user_id": YE_HAILIN_OPEN_ID, "user_name": "叶海淋"},
            {"tag": "text", "text": f" 小昭未完成工单合并报表：{report_date}"},
        ],
        [{"tag": "text", "text": f"未完成合计：{len(items)} 个（需求 {xq_count} 个，Bug {bug_count} 个）"}],
    ]
    if not items:
        lines.append([{"tag": "text", "text": "当前没有未完成的需求单或Bug单。"}])
        return lines
    for item in items:
        lines.append(
            [
                {
                    "tag": "text",
                    "text": f"{item['type']} #{item['id']}｜{item['status']}｜{item['created_at']}｜{item['summary']}",
                }
            ]
        )
    return lines


def insert_report(conn: sqlite3.Connection, *, report_date: str, body: str, sent_status: str) -> int:
    now_text = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        """
        INSERT INTO reports (
          report_type, period_start, period_end, body,
          summary_text, sent_status, sent_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "unfinished_tickets",
            report_date,
            report_date,
            body,
            "未完成xq/bug合并报表",
            sent_status,
            now_text if sent_status == "sent" else None,
            now_text,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(resolve_default_db()))
    parser.add_argument("--feishu-app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--feishu-chat-id", default=DEFAULT_CHAT_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    report_date = datetime.now().date().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        items = []
        items.extend(fetch_unfinished(conn, "xiaozhao_feishu_requirement_tickets", "需求单"))
        items.extend(fetch_unfinished(conn, "xiaozhao_feishu_bug_tickets", "Bug单"))
        body = build_report(items, report_date)
        sent_status = "dry_run"
        send_response: dict[str, Any] | None = None
        if not args.dry_run:
            secret = read_secret()
            if not secret:
                sent_status = "failed"
                send_response = {"error": "FEISHU_APP_SECRET missing"}
            else:
                try:
                    send_response = send_post_message(
                        args.feishu_app_id,
                        secret,
                        args.feishu_chat_id,
                        "小昭未完成工单合并报表",
                        build_post_lines(items, report_date),
                    )
                    sent_status = "sent" if send_response.get("code") == 0 else "failed"
                except FeishuSendError as exc:
                    sent_status = "failed"
                    send_response = {"error": str(exc), "detail": getattr(exc, "detail", {})}
        report_id = insert_report(conn, report_date=report_date, body=body, sent_status=sent_status)
    print(
        json.dumps(
            {
                "database_path": str(db_path.resolve()),
                "report_id": report_id,
                "unfinished_count": len(items),
                "sent_status": sent_status,
                "send_response": send_response,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
