#!/usr/bin/env python3
"""Collect a local, one-shot diagnosis for XiaoZhao automation faults."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run(command: list[str], root: Path, timeout: int = 20) -> dict[str, object]:
    try:
        proc = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "stdout": proc.stdout.strip()[-1200:],
            "stderr": proc.stderr.strip()[-1200:],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def db_path(root: Path) -> Path | None:
    for candidate in [
        root / ".zhipin-copilot/recruitment.sqlite3",
        root / "data/.zhipin-copilot/recruitment.sqlite3",
    ]:
        if candidate.exists():
            return candidate
    return None


def latest_runs(path: Path) -> list[dict[str, object]]:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT flow_id, run_id, status, started_at, heartbeat_at, ended_at, note
            FROM automation_runs
            ORDER BY heartbeat_at DESC
            LIMIT 12
            """
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        return [{"error": str(exc)}]
    finally:
        conn.close()


def latest_feishu_failures(path: Path) -> list[dict[str, object]]:
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT event_type, status, note, detail_text, created_at
            FROM run_events
            WHERE (
                event_type LIKE '%feishu%'
                OR event_type LIKE '%forward%'
                OR event_type = 'automation_fault_alert'
            )
              AND lower(COALESCE(status, '')) IN ('failed', 'failure', 'error')
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        return [{"error": str(exc)}]
    finally:
        conn.close()


def summarize(result: dict[str, object]) -> str:
    parts: list[str] = []
    if result["checks"]["crontab"].get("ok"):
        parts.append("crontab 可读取")
    else:
        parts.append("crontab 不可读取")
    if result["checks"]["codex"].get("ok"):
        parts.append("Codex 可执行")
    else:
        parts.append("Codex 检查失败")
    if result["checks"]["feishu_tcp"].get("ok"):
        parts.append("飞书网络预检可达")
    else:
        parts.append("飞书网络预检失败")
    if result.get("database_path"):
        parts.append("SQLite 可读取")
    else:
        parts.append("SQLite 未找到")
    failures = result.get("recent_feishu_failures") or []
    if failures:
        parts.append(f"近期飞书/转发失败 {len(failures)} 条")
    return "；".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--flow-id", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    root = package_root()
    db = db_path(root)
    gateway_probe = (
        "import sys;"
        "sys.path.insert(0,'skills/zhipin-boss-recruitment-bot/scripts');"
        "from feishu_gateway import network_precheck;"
        "print(network_precheck())"
    )
    result: dict[str, object] = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "flow_id": args.flow_id,
        "reason": args.reason,
        "database_path": str(db.resolve()) if db else "",
        "checks": {
            "crontab": run(["crontab", "-l"], root),
            "codex": run(["codex", "--version"], root),
            "feishu_tcp": run([sys.executable, "-c", gateway_probe], root),
        },
        "latest_runs": latest_runs(db) if db else [],
        "recent_feishu_failures": latest_feishu_failures(db) if db else [],
    }
    result["summary"] = summarize(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
