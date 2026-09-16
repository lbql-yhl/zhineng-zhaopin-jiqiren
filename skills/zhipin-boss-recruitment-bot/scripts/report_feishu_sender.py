#!/usr/bin/env python3
"""Send or resend saved XiaoZhao reports to Feishu."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from feishu_gateway import (  # noqa: E402
    DEFAULT_APP_ID,
    DEFAULT_CHAT_ID,
    FeishuSendError,
    body_to_post_lines,
    read_config_value,
    read_secret,
    send_post_message,
)
from report_metrics import build_report, codex_token_total_for_period  # noqa: E402

DEFAULT_DB = Path(".zhipin-copilot/recruitment.sqlite3")
AI_INFRA_CHAT_ID = "oc_7e0ab0f30306c580726cd38bdcdff31c"
DEFAULT_CHAT_IDS = [DEFAULT_CHAT_ID, AI_INFRA_CHAT_ID]
FORBIDDEN_VISIBLE_REPORT_FRAGMENTS = (
    "数据源",
    "数据来源",
    "权威数据源",
    "SQLite",
    "sqlite",
    "数据库路径",
    "database_path",
    "source_db",
    ".zhipin-copilot",
    "run_events",
    "processed_candidates",
    "screening_run_seen_candidates",
    "daily_processed_candidates",
    "forward_records",
    "batch_list_prefilter",
)


def default_period(report_type: str, anchor: date) -> tuple[str, str]:
    if report_type == "daily":
        target = anchor - timedelta(days=1)
        return target.isoformat(), target.isoformat()
    monday = anchor - timedelta(days=anchor.weekday())
    previous_monday = monday - timedelta(days=7)
    return previous_monday.isoformat(), (previous_monday + timedelta(days=6)).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def fetch_report(conn: sqlite3.Connection, report_type: str, start: str, end: str, report_id: int | None) -> sqlite3.Row | None:
    if report_id is not None:
        return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return conn.execute(
        """
        SELECT *
        FROM reports
        WHERE report_type = ?
          AND period_start = ?
          AND period_end = ?
          AND COALESCE(sent_status, '') IN ('PREPARED', 'FAILED', 'failed', '')
        ORDER BY
          CASE sent_status
            WHEN 'PREPARED' THEN 0
            WHEN 'FAILED' THEN 1
            WHEN 'failed' THEN 1
            ELSE 2
          END,
          id DESC
        LIMIT 1
        """,
        (report_type, start, end),
    ).fetchone()


def fetch_sent_report(
    conn: sqlite3.Connection,
    report_type: str,
    start: str,
    end: str,
    required_chat_ids: list[str],
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM reports
        WHERE report_type = ?
          AND period_start = ?
          AND period_end = ?
          AND lower(COALESCE(sent_status, '')) IN ('sent', 'sent_with_blocker_alert', 'sent_with_login_alert')
        ORDER BY sent_at DESC, id DESC
        LIMIT 1
        """,
        (report_type, start, end),
    ).fetchone()


def report_already_sent_to_all(row: sqlite3.Row | None, required_chat_ids: list[str]) -> bool:
    if row is None:
        return False
    if not required_chat_ids:
        return True
    sent_chat_ids = sent_chat_ids_from_report(row)
    return all(chat_id in sent_chat_ids for chat_id in required_chat_ids)


def sent_chat_ids_from_report(row: sqlite3.Row | None) -> set[str]:
    if row is None:
        return set()
    summary_text = str(row["summary_text"] or "")
    sent_chat_ids = set(re.findall(r"oc_[0-9a-f]{32}", summary_text))
    status = str(row["sent_status"] or "").lower()
    if status.startswith("sent") and not sent_chat_ids:
        # Historical report sends predate per-target details and used the main group only.
        sent_chat_ids.add(DEFAULT_CHAT_ID)
    return sent_chat_ids


def update_report(conn: sqlite3.Connection, report_id: int, status: str, detail: dict[str, Any] | None) -> None:
    now_text = datetime.now().astimezone().isoformat(timespec="seconds")
    summary = None if detail is None else json.dumps(detail, ensure_ascii=False)[:1800]
    conn.execute(
        """
        UPDATE reports
        SET sent_status = ?,
            sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END,
            summary_text = COALESCE(summary_text, '') || CASE WHEN ? IS NULL THEN '' ELSE char(10) || ? END
        WHERE id = ?
        """,
        (status, status, now_text, summary, f"send_detail={summary}", report_id),
    )
    conn.commit()


def insert_event(conn: sqlite3.Connection, event_type: str, status: str, note: str, detail: dict[str, Any] | None) -> None:
    now_text = datetime.now().astimezone().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO run_events (event_type, status, note, detail_text, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event_type, status, note, json.dumps(detail or {}, ensure_ascii=False), now_text),
    )
    conn.commit()


def insert_fresh_report(conn: sqlite3.Connection, report_type: str, start: str, end: str, persist: bool = True) -> sqlite3.Row | dict[str, Any]:
    """Recompute the report body immediately before sending.

    Prepared report rows are useful for diagnostics, but they must not become a
    stale cache for scheduled Feishu sends. The sender therefore regenerates the
    body from the live canonical SQLite source for the requested period whenever
    it is not asked to send an explicit report id.
    """
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    token_total = codex_token_total_for_period(start_day, end_day)
    report = build_report(conn, report_type, start_day, end_day, token_total)
    summary = json.dumps(
        {
            "generated_by": "report_feishu_sender_latest",
            "processed": report.get("processed"),
            "forwarded": report.get("forwarded"),
            "hard_fail": report.get("hard_fail"),
        },
        ensure_ascii=False,
    )
    if not persist:
        return {
            "id": 0,
            "report_type": report_type,
            "period_start": start,
            "period_end": end,
            "body": str(report["body"]),
            "summary_text": summary,
            "sent_status": "PREPARED",
            "sent_at": None,
        }
    now_text = datetime.now().astimezone().isoformat(timespec="seconds")
    cur = conn.execute(
        """
        INSERT INTO reports (report_type, period_start, period_end, body, summary_text, sent_status, created_at)
        VALUES (?, ?, ?, ?, ?, 'PREPARED', ?)
        """,
        (report_type, start, end, str(report["body"]), summary, now_text),
    )
    conn.commit()
    return conn.execute("SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone()


def report_title(report_type: str, start: str, end: str) -> str:
    if report_type == "daily":
        return f"小昭工作日报 {start}"
    return f"小昭工作周报 {start} 至 {end}"


def validate_latest_report_format(report_type: str, body: str) -> list[str]:
    expected_title = "工作日报：" if report_type == "daily" else "工作周报："
    period_word = "今日" if report_type == "daily" else "上周"
    required_fragments = [
        expected_title,
        "1. 运行状态与风控",
        "- 运行时长与状态：",
        "- Token消耗：累计消耗 Token",
        "2. 任务完成度与简历质量",
        "- 全局漏斗：",
        f"{period_word}共筛选候选人",
        "重复候选人",
        "- 筛选过程全量统计：",
        "去除重复后进入列表预筛",
        "列表预筛通过",
        "列表预筛不通过",
        "原因：年龄不符合",
        "打开在线简历",
        "列表信息不完整",
        "- 岗位拆解：",
        "硬性条件通过并转发",
        "硬性条件缺失未转发",
        "- 岗位不符合原因统计（按候选人去重，记录主因）：",
        "3. 小昭洞察与建议",
        "- 画像总结：",
        "- 未转发原因分析：",
        "- 行动建议：",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in body]
    no_job_record = "无岗位筛选记录" in body
    if not no_job_record:
        for fragment in ["岗位总数据", "列表读取", "入库候选人"]:
            if fragment not in body:
                missing.append(fragment)
    period_word = "今日" if report_type == "daily" else "上周"
    total_match = re.search(rf"{period_word}共筛选候选人\s*(\d+)\s*位", body)
    opened_match = re.search(r"打开在线简历\s*(\d+)\s*(?:位|份)", body)
    if total_match and opened_match and int(opened_match.group(1)) > int(total_match.group(1)):
        missing.append("数据口径错误：打开在线简历人数大于共筛选候选人数")
    forbidden = [fragment for fragment in FORBIDDEN_VISIBLE_REPORT_FRAGMENTS if fragment in body]
    if forbidden:
        missing.append("对外报告禁止展示内部数据源/数据链路：" + "、".join(forbidden))
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--report-type", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument("--date", help="Anchor date. Daily defaults to previous day of this date.")
    parser.add_argument("--report-id", type=int)
    parser.add_argument("--feishu-app-id", default=DEFAULT_APP_ID)
    parser.add_argument(
        "--feishu-chat-id",
        action="append",
        default=[],
        help="Feishu group chat_id. Repeat to send the same report to multiple groups.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_chat_ids(raw_chat_ids: list[str]) -> list[str]:
    values = raw_chat_ids or []
    if not values:
        env_value = read_config_value("FEISHU_CHAT_IDS")
        values = [env_value] if env_value else DEFAULT_CHAT_IDS
    chat_ids: list[str] = []
    for value in values:
        for item in re.split(r"[,，\\s]+", value.strip()):
            if item and item not in chat_ids:
                chat_ids.append(item)
    return chat_ids


def main() -> None:
    args = parse_args()
    chat_ids = resolve_chat_ids(args.feishu_chat_id)
    anchor = date.fromisoformat(args.date) if args.date else datetime.now().astimezone().date()
    start, end = (args.period_start, args.period_end) if args.period_start and args.period_end else default_period(args.report_type, anchor)
    db_path = Path(args.db)
    with connect(db_path) as conn:
        sent_row: sqlite3.Row | None = None
        chat_ids_to_send = chat_ids
        if not args.dry_run and args.report_id is None:
            sent_row = fetch_sent_report(conn, args.report_type, start, end, chat_ids)
            if report_already_sent_to_all(sent_row, chat_ids):
                result = {
                    "database_path": str(db_path.resolve()),
                    "report_id": int(sent_row["id"]),
                    "report_type": args.report_type,
                    "period_start": start,
                    "period_end": end,
                    "sent_status": "already_sent",
                    "sent_at": sent_row["sent_at"],
                    "feishu_chat_ids": chat_ids,
                    "send_response": None,
                }
                insert_event(
                    conn,
                    f"{args.report_type}_report_feishu_send",
                    "already_sent",
                    "日报/周报已发送，跳过重复发送",
                    result,
                )
                print(json.dumps(result, ensure_ascii=False))
                return
            sent_chat_ids = sent_chat_ids_from_report(sent_row)
            if sent_chat_ids:
                chat_ids_to_send = [chat_id for chat_id in chat_ids if chat_id not in sent_chat_ids]

        if args.report_id is None:
            row = insert_fresh_report(conn, args.report_type, start, end, persist=not args.dry_run)
        else:
            row = fetch_report(conn, args.report_type, start, end, args.report_id)
        if row is None and sent_row is not None and args.report_id is not None:
            row = sent_row
        if row is None:
            result = {
                "database_path": str(db_path.resolve()),
                "sent_status": "failed",
                "error": "no prepared or failed report found",
                "report_type": args.report_type,
                "period_start": start,
                "period_end": end,
                "feishu_chat_ids": chat_ids,
                "feishu_chat_ids_to_send": chat_ids_to_send,
            }
            insert_event(conn, f"{args.report_type}_report_feishu_send", "failed", "未找到可发送日报/周报记录", result)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(2)

        report_id = int(row["id"])
        body = str(row["body"] or "")
        missing_format = validate_latest_report_format(str(row["report_type"]), body)
        if missing_format:
            detail = {
                "report_id": report_id,
                "report_type": str(row["report_type"]),
                "period_start": str(row["period_start"]),
                "period_end": str(row["period_end"]),
                "missing_format_fragments": missing_format,
            }
            if not args.dry_run:
                update_report(conn, report_id, "failed", {"error": "latest report format validation failed", **detail})
                insert_event(
                    conn,
                    f"{args.report_type}_report_feishu_send",
                    "failed",
                    "日报/周报新格式校验失败，停止飞书发送",
                    detail,
                )
            print(
                json.dumps(
                    {
                        "database_path": str(db_path.resolve()),
                        "report_id": report_id,
                        "report_type": args.report_type,
                        "period_start": start,
                        "period_end": end,
                        "sent_status": "failed",
                        "error": "latest report format validation failed",
                        "missing_format_fragments": missing_format,
                    },
                    ensure_ascii=False,
                )
            )
            raise SystemExit(2)
        send_response: dict[str, Any] | None = (
            {"dry_run": True, "chat_ids": chat_ids, "chat_ids_to_send": chat_ids_to_send}
            if args.dry_run
            else None
        )
        status = "dry_run"
        if not args.dry_run:
            secret = read_secret()
            if not secret:
                status = "failed"
                send_response = {"error": "FEISHU_APP_SECRET missing"}
            else:
                send_results: list[dict[str, Any]] = []
                title = report_title(str(row["report_type"]), str(row["period_start"]), str(row["period_end"]))
                lines = body_to_post_lines(body)
                for chat_id in chat_ids_to_send:
                    try:
                        response = send_post_message(
                            args.feishu_app_id,
                            secret,
                            chat_id,
                            title,
                            lines,
                        )
                        send_results.append(
                            {
                                "chat_id": chat_id,
                                "status": "sent" if response.get("code") == 0 else "failed",
                                "response": response,
                            }
                        )
                    except FeishuSendError as exc:
                        send_results.append(
                            {
                                "chat_id": chat_id,
                                "status": "failed",
                                "error": str(exc),
                                "detail": exc.detail,
                            }
                        )
                status = "sent" if send_results and all(item["status"] == "sent" for item in send_results) else "failed"
                send_response = {"targets": send_results}

        if not args.dry_run:
            update_report(conn, report_id, status, send_response)
            insert_event(
                conn,
                f"{args.report_type}_report_feishu_send",
                status,
                "日报/周报飞书发送完成" if status == "sent" else "日报/周报飞书发送失败",
                {
                    "report_id": report_id,
                    "feishu_chat_ids": chat_ids,
                    "feishu_chat_ids_to_send": chat_ids_to_send,
                    "send_response": send_response,
                },
            )

    print(
        json.dumps(
            {
                "database_path": str(db_path.resolve()),
                "report_id": report_id,
                "report_type": args.report_type,
                "period_start": start,
                "period_end": end,
                "sent_status": status,
                "feishu_chat_ids": chat_ids,
                "feishu_chat_ids_to_send": chat_ids_to_send,
                "send_response": send_response,
            },
            ensure_ascii=False,
        )
    )
    if status == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
