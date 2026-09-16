#!/usr/bin/env python3
"""Check whether current open BOSS/Zhipin jobs exist in the user-provided JD library."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from feishu_gateway import DEFAULT_APP_ID, DEFAULT_CHAT_ID, FeishuSendError, read_secret, send_post_message, text_node  # noqa: E402
from sqlite_store import DEFAULT_DB, USER_PROVIDED_JDS, canonical_job_name, connect, insert_run_event, plain_result

ZHONGMIAO_OPEN_ID = "ou_606d3c2906e2fb2529d64d87308e912c"


def send_feishu_notice(app_id: str, app_secret: str, chat_id: str, lines: list[str]) -> dict[str, Any]:
    post_lines: list[list[dict[str, Any]]] = [[text_node("JD库缺失提醒：", bold=True)]]
    post_lines.extend([[{"tag": "at", "user_id": ZHONGMIAO_OPEN_ID}, text_node(" " + line)] for line in lines])
    return send_post_message(app_id, app_secret, chat_id, "JD库缺失提醒", post_lines)


def known_jd_names(conn: sqlite3.Connection) -> set[str]:
    seeded_names = {item["job_ref"] for item in USER_PROVIDED_JDS}
    rows = conn.execute(
        "SELECT job_ref, job_title FROM jobs WHERE last_jd_read_at IN ('USER_PROVIDED', 'FEISHU_USER_PROVIDED')"
    ).fetchall()
    names = set(seeded_names)
    for row in rows:
        if row["job_ref"]:
            names.add(canonical_job_name(row["job_ref"]))
        if row["job_title"]:
            names.add(canonical_job_name(row["job_title"]))
        names.add(canonical_job_name(" ".join([row["job_ref"] or "", row["job_title"] or ""])))
    return {name for name in names if name}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--open-job-ref", action="append", required=True)
    parser.add_argument("--notify-feishu", action="store_true")
    parser.add_argument("--feishu-app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--feishu-chat-id", default=DEFAULT_CHAT_ID)
    return parser.parse_args()


def notice_line(job: str) -> str:
    suffix = "" if job.endswith("岗位") else "岗位"
    return f"jd库里没有{job}{suffix}的jd，请提供。"


def main() -> None:
    args = parse_args()
    refs = [ref.strip() for ref in args.open_job_ref if ref and ref.strip()]
    with connect(Path(args.db)) as conn:
        known = known_jd_names(conn)
        missing = []
        for ref in refs:
            canonical = canonical_job_name(ref)
            if canonical not in known:
                missing.append(canonical or ref)
        missing = sorted(set(missing))
        lines = [notice_line(job) for job in missing]
        send_status = "not_sent"
        send_detail = ""
        if missing and args.notify_feishu:
            secret = read_secret()
            if not secret:
                send_status = "failed"
                send_detail = "FEISHU_APP_SECRET missing"
            else:
                try:
                    response = send_feishu_notice(args.feishu_app_id, secret, args.feishu_chat_id, lines)
                    send_status = "sent" if response.get("code") == 0 else "failed"
                    send_detail = str(response)
                except FeishuSendError as exc:
                    send_status = "failed"
                    send_detail = json.dumps({"error": str(exc), "detail": exc.detail}, ensure_ascii=False)
                except Exception as exc:
                    send_status = "failed"
                    send_detail = str(exc)
        insert_run_event(
            conn,
            argparse.Namespace(
                event_type="jd_library_check",
                job_ref=None,
                candidate_ref=None,
                status="missing" if missing else "ok",
                note="；".join(lines),
                detail_text=f"open_jobs={len(refs)}; missing_jobs={len(missing)}; feishu={send_status}; {send_detail}",
                detail_text_file=None,
                created_at=None,
            ),
        )
    print(
        plain_result(
            database_path=str(Path(args.db).resolve()),
            checked_count=len(refs),
            missing_count=len(missing),
            missing_jobs="、".join(missing),
            notice="；".join(lines),
            feishu_status=send_status,
        )
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
