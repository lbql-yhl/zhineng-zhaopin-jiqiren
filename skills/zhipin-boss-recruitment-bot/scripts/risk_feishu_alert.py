#!/usr/bin/env python3
"""Send XiaoZhao risk alerts to Feishu without depending on GPT."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sqlite_store import DEFAULT_DB, connect, insert_run_event, plain_result  # noqa: E402
from feishu_gateway import (  # noqa: E402
    DEFAULT_APP_ID,
    DEFAULT_CHAT_ID,
    FeishuSendError,
    post_json,
    read_config_value,
    send_post_message,
)

YE_HAILIN_OPEN_ID = "ou_be28de7519471294e523a2708caa6190"
ZHONGMIAO_OPEN_ID = "ou_606d3c2906e2fb2529d64d87308e912c"


def fallback_llm_message(provider: str, base_message: str) -> tuple[str | None, str]:
    if provider == "none":
        return None, "disabled"
    if provider == "deepseek":
        api_key = read_config_value("DEEPSEEK_API_KEY")
        base_url = read_config_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        model = read_config_value("DEEPSEEK_MODEL", "deepseek-chat")
    elif provider == "minimax":
        api_key = read_config_value("MINIMAX_API_KEY") or read_config_value("MINIMAX_CN_API_KEY")
        base_url = (
            read_config_value("MINIMAX_BASE_URL")
            or read_config_value("MINIMAX_CN_BASE_URL")
            or "https://api.minimax.io/v1"
        ).rstrip("/")
        model = read_config_value("MINIMAX_MODEL", "MiniMax-M3")
    else:
        return None, f"unsupported_provider:{provider}"
    if not api_key:
        return None, f"{provider}:missing_api_key"

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你只改写飞书风险告警，中文，120字以内，不输出密钥、路径或实现细节。",
            },
            {"role": "user", "content": base_message},
        ],
        "temperature": 0.2,
    }
    try:
        data = post_json(
            f"{base_url}/chat/completions",
            body,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=25,
        )
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if content:
            return str(content).strip(), f"{provider}:ok"
        return None, f"{provider}:empty_response"
    except Exception as exc:
        return None, f"{provider}:failed:{type(exc).__name__}"


def build_default_lines(args: argparse.Namespace, created_at: str, llm_status: str) -> list[list[dict[str, str]]]:
    fallback_text = args.fallback_provider
    if args.fallback_provider != "none":
        fallback_text = f"{args.fallback_provider}（{llm_status}）"
    target_open_id = YE_HAILIN_OPEN_ID if args.at == "program" else ZHONGMIAO_OPEN_ID
    target_name = "叶海淋" if args.at == "program" else "钟苗"
    lines = [
        [
            {"tag": "at", "user_id": target_open_id, "user_name": target_name},
            {"tag": "text", "text": " 小昭风险提醒：GPT/主模型通道不可用"},
        ],
        [{"tag": "text", "text": f"时间：{created_at}"}],
        [{"tag": "text", "text": f"任务：{args.task}"}],
        [{"tag": "text", "text": f"原因：{args.reason}"}],
        [{"tag": "text", "text": f"兜底模型：{fallback_text}"}],
        [{"tag": "text", "text": "处理建议：请检查 GPT/Codex/Hermes 通道，恢复前不要启动 BOSS 自动筛选。"}],
    ]
    return lines


def record_event(db: Path, args: argparse.Namespace, status: str, detail: str, created_at: str) -> dict[str, Any] | None:
    if args.no_db_event:
        return None
    event_args = SimpleNamespace(
        event_type="gpt_unavailable_risk_alert",
        job_ref=None,
        candidate_ref=None,
        status=status,
        note=args.reason,
        detail_text=detail,
        detail_text_file=None,
        created_at=created_at,
    )
    with connect(db) as conn:
        return insert_run_event(conn, event_args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="小昭/BOSS 自动化")
    parser.add_argument("--reason", default="GPT/主模型通道无法使用")
    parser.add_argument("--fallback-provider", choices=["none", "deepseek", "minimax"], default="none")
    parser.add_argument("--at", choices=["program", "zhongmiao"], default="program")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--feishu-app-id", default=read_config_value("FEISHU_APP_ID", DEFAULT_APP_ID))
    parser.add_argument("--feishu-chat-id", default=read_config_value("FEISHU_CHAT_ID", DEFAULT_CHAT_ID))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-db-event", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    base_message = f"小昭风险提醒：{args.task} 因 {args.reason} 未能正常使用 GPT/主模型通道。"
    llm_message, llm_status = fallback_llm_message(args.fallback_provider, base_message)
    lines = build_default_lines(args, created_at, llm_status)
    if llm_message:
        lines.append([{"tag": "text", "text": f"补充说明：{llm_message}"}])

    send_response: dict[str, Any] | None = None
    sent_status = "dry_run"
    detail = f"fallback_provider={args.fallback_provider}; fallback_status={llm_status}"
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
                    "小昭风险提醒",
                    lines,
                )
                sent_status = "sent" if send_response.get("code") == 0 else "failed"
            except FeishuSendError as exc:
                sent_status = "failed"
                send_response = {"error": str(exc), "detail": exc.detail}
            except Exception as exc:
                sent_status = "failed"
                send_response = {"error": f"{type(exc).__name__}: {exc}"}
    event = record_event(Path(args.db), args, sent_status, detail, created_at)
    print(
        json.dumps(
            {
                "database_path": str(Path(args.db).resolve()),
                "sent_status": sent_status,
                "fallback_status": llm_status,
                "event": event,
                "send_response": send_response,
            },
            ensure_ascii=False,
        )
    )

    if sent_status == "failed":
        raise SystemExit(2)
    print(plain_result(sent_status=sent_status, fallback_status=llm_status))


if __name__ == "__main__":
    main()
