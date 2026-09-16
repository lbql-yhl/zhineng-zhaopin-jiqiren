#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "zhipin-boss-recruitment-bot" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from sqlite_store import DEFAULT_DB, connect, insert_run_event, plain_result  # noqa: E402

created_at = datetime.now().astimezone().isoformat(timespec="seconds")
try:
    with socket.create_connection(("open.feishu.cn", 443), timeout=8):
        probe = "ok"
except Exception as exc:
    probe = f"{type(exc).__name__}: {exc}"

detail = "\n".join(
    [
        f"pid={os.getpid()}",
        f"codex_sandbox_network_disabled={os.environ.get('CODEX_SANDBOX_NETWORK_DISABLED') or ''}",
        f"codex_sandbox={os.environ.get('CODEX_SANDBOX') or ''}",
        f"probe={probe}",
    ]
)
args = SimpleNamespace(
    event_type="feishu_launchd_network_probe",
    job_ref=None,
    candidate_ref=None,
    status="ok" if probe == "ok" else "failed",
    note=probe,
    detail_text=detail,
    detail_text_file=None,
    created_at=created_at,
)

with connect(DEFAULT_DB) as conn:
    result = insert_run_event(conn, args)

print(plain_result(**result))
