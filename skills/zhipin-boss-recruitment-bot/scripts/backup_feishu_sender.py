#!/usr/bin/env python3
"""Send XiaoZhao SQLite backup success notices to Feishu."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from feishu_gateway import DEFAULT_APP_ID, DEFAULT_CHAT_ID, FeishuSendError, read_secret, send_post_message  # noqa: E402
from sqlite_store import DEFAULT_DB, connect, insert_run_event  # noqa: E402


def build_lines(args: argparse.Namespace, payload: dict[str, Any], created_at: str) -> list[list[dict[str, str]]]:
    local_backup = str(payload.get("local_backup") or args.local_backup or "")
    desktop_backup = str(payload.get("desktop_backup") or args.desktop_backup or "")
    sha256 = str(payload.get("sha256") or args.sha256 or "")
    integrity = str(payload.get("integrity") or args.integrity or "")
    return [
        [{"tag": "text", "text": "小昭 SQLite 自动备份成功"}],
        [{"tag": "text", "text": f"时间：{created_at}"}],
        [{"tag": "text", "text": f"本机备份：{local_backup}"}],
        [{"tag": "text", "text": f"桌面备份：{desktop_backup}"}],
        [{"tag": "text", "text": f"integrity：{integrity}"}],
        [{"tag": "text", "text": f"sha256：{sha256}"}],
    ]


def record_event(db: Path, status: str, detail: dict[str, Any], created_at: str) -> None:
    event_args = argparse.Namespace(
        event_type="sqlite_backup_feishu_notice",
        job_ref=None,
        candidate_ref=None,
        status=status,
        note="SQLite 自动备份成功通知" if status == "sent" else "SQLite 自动备份通知失败",
        detail_text=json.dumps(detail, ensure_ascii=False)[:1800],
        detail_text_file=None,
        created_at=created_at,
    )
    with connect(db) as conn:
        insert_run_event(conn, event_args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--payload-json", default="")
    parser.add_argument("--local-backup", default="")
    parser.add_argument("--desktop-backup", default="")
    parser.add_argument("--sha256", default="")
    parser.add_argument("--integrity", default="")
    parser.add_argument("--feishu-app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--feishu-chat-id", default=DEFAULT_CHAT_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload: dict[str, Any] = json.loads(args.payload_json) if args.payload_json else {}
    send_response: dict[str, Any] | None = {"dry_run": True} if args.dry_run else None
    status = "dry_run"
    if not args.dry_run:
        secret = read_secret()
        if not secret:
            status = "failed"
            send_response = {"error": "FEISHU_APP_SECRET missing"}
        else:
            try:
                send_response = send_post_message(
                    args.feishu_app_id,
                    secret,
                    args.feishu_chat_id,
                    "小昭 SQLite 自动备份成功",
                    build_lines(args, payload, created_at),
                )
                status = "sent" if send_response.get("code") == 0 else "failed"
            except FeishuSendError as exc:
                status = "failed"
                send_response = {"error": str(exc), "detail": exc.detail}

    result = {
        "database_path": str(Path(args.db).resolve()),
        "sent_status": status,
        "send_response": send_response,
        "payload": payload,
    }
    if not args.dry_run:
        record_event(Path(args.db), status, result, created_at)
    print(json.dumps(result, ensure_ascii=False))
    if status == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
