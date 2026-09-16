#!/usr/bin/env python3
"""Send XiaoZhao automation fault alerts to Feishu without depending on GPT."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from feishu_gateway import DEFAULT_APP_ID, DEFAULT_CHAT_ID, FeishuSendError, read_config_value, send_post_message  # noqa: E402
from sqlite_store import DEFAULT_DB, connect, insert_run_event  # noqa: E402

YE_HAILIN_OPEN_ID = "ou_be28de7519471294e523a2708caa6190"
ZHONGMIAO_OPEN_ID = "ou_606d3c2906e2fb2529d64d87308e912c"
DEFAULT_STATE = Path.home() / ".hermes" / "state" / "xiaozhao_automation_fault_alert.json"


def now() -> datetime:
    return datetime.now().astimezone()


def now_text() -> str:
    return now().isoformat(timespec="seconds")


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def should_send(state: dict[str, Any], signature: str, cooldown_minutes: int) -> bool:
    item = state.get(signature)
    if not item:
        return True
    last = item.get("last_sent_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except ValueError:
        return True
    return now() - last_dt >= timedelta(minutes=cooldown_minutes)


def target_user(at: str) -> tuple[str, str]:
    if at == "program":
        return YE_HAILIN_OPEN_ID, "叶海淋"
    return ZHONGMIAO_OPEN_ID, "钟苗"


def build_lines(args: argparse.Namespace, created_at: str) -> list[list[dict[str, str]]]:
    user_id, user_name = target_user(args.at)
    lines = [
        [
            {"tag": "at", "user_id": user_id, "user_name": user_name},
            {"tag": "text", "text": f" 小昭自动化故障：{args.title}"},
        ],
        [{"tag": "text", "text": f"时间：{created_at}"}],
        [{"tag": "text", "text": f"任务：{args.task}"}],
        [{"tag": "text", "text": f"原因：{args.reason}"}],
    ]
    if args.detail:
        lines.append([{"tag": "text", "text": f"详情：{args.detail[:900]}"}])
    if args.diagnosis:
        lines.append([{"tag": "text", "text": f"诊断：{args.diagnosis[:900]}"}])
    lines.append([{"tag": "text", "text": "处理：Codex 已接管故障诊断/修复，会先做本地可判定检查。"}])
    lines.append([{"tag": "text", "text": "升级规则：如果无法自动确认已修复，会通知程序负责人继续处理；恢复前不要继续自动筛选。"}])
    return lines


def record_event(db: Path, args: argparse.Namespace, status: str, detail: dict[str, Any], created_at: str) -> None:
    if args.no_db_event:
        return
    event_args = SimpleNamespace(
        event_type="automation_fault_alert",
        job_ref=None,
        candidate_ref=None,
        status=status,
        note=f"{args.task}: {args.reason}",
        detail_text=json.dumps(detail, ensure_ascii=False)[:1800],
        detail_text_file=None,
        created_at=created_at,
    )
    try:
        with connect(db) as conn:
            insert_run_event(conn, event_args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"event_record_failed": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="流程故障")
    parser.add_argument("--task", default="小昭自动化")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--detail", default="")
    parser.add_argument("--diagnosis", default="")
    parser.add_argument("--at", choices=["program", "zhongmiao"], default="program")
    parser.add_argument("--cooldown-minutes", type=int, default=15)
    parser.add_argument("--signature", default="")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--feishu-app-id", default=read_config_value("FEISHU_APP_ID", DEFAULT_APP_ID))
    parser.add_argument("--feishu-chat-id", default=read_config_value("FEISHU_CHAT_ID", DEFAULT_CHAT_ID))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-db-event", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    created_at = now_text()
    signature_text = args.signature or f"{args.title}|{args.task}|{args.reason}|{args.detail[:300]}"
    signature = hashlib.sha256(signature_text.encode("utf-8")).hexdigest()
    state_path = Path(args.state_path)
    state = read_state(state_path)
    if not should_send(state, signature, args.cooldown_minutes):
        result = {"sent_status": "cooldown", "signature": signature, "created_at": created_at}
        record_event(Path(args.db), args, "cooldown", result, created_at)
        print(json.dumps(result, ensure_ascii=False))
        return

    send_response: dict[str, Any] | None = {"dry_run": True} if args.dry_run else None
    sent_status = "dry_run"
    if not args.dry_run:
        secret = read_config_value("FEISHU_APP_SECRET")
        if not secret:
            sent_status = "failed"
            send_response = {"error": "FEISHU_APP_SECRET missing"}
        else:
            try:
                send_response = send_post_message(
                    args.feishu_app_id,
                    secret,
                    args.feishu_chat_id,
                    "小昭自动化故障提醒",
                    build_lines(args, created_at),
                )
                sent_status = "sent" if send_response.get("code") == 0 else "failed"
            except FeishuSendError as exc:
                sent_status = "failed"
                send_response = {"error": str(exc), "detail": exc.detail}
            except Exception as exc:  # noqa: BLE001
                sent_status = "failed"
                send_response = {"error": f"{type(exc).__name__}: {exc}"}

    result = {
        "sent_status": sent_status,
        "signature": signature,
        "created_at": created_at,
        "send_response": send_response,
    }
    record_event(Path(args.db), args, sent_status, result, created_at)
    if sent_status in {"sent", "dry_run"}:
        state[signature] = {"last_sent_at": created_at, "title": args.title, "task": args.task, "reason": args.reason}
        write_state(state_path, state)
    print(json.dumps(result, ensure_ascii=False))
    if sent_status == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
