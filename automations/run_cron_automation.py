#!/usr/bin/env python3
"""Run one XiaoZhao automation template from crontab with SQLite heartbeat."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None


SKILLS = ",".join(
    [
        "xiaozhao-robot-2",
        "zhipin-boss-recruitment-bot",
        "zhipin-scheduled-forward-report",
        "zhipin-weekly-work-report",
    ]
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_task(path: Path) -> dict:
    if tomllib is not None:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    task: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            task[key] = value[1:-1].replace('\\"', '"')
        elif value.startswith("[") and value.endswith("]"):
            task[key] = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
        elif value.isdigit():
            task[key] = int(value)
        else:
            task[key] = value
    return task


def run_sqlite_store(root: Path, *args: str, check: bool = True) -> dict:
    script = root / "skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py"
    command = [sys.executable, str(script), *args]
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"sqlite_store failed: {command}")
    text = proc.stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        parsed: dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                parsed[key.strip()] = value.strip()
        return parsed or {"raw": text}


def main_flow_activity_count(root: Path, started_at: str) -> int:
    db_path = root / ".zhipin-copilot/recruitment.sqlite3"
    if not db_path.exists():
        return 0
    day = started_at[:10]
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        daily_processed = conn.execute(
            """
            SELECT COUNT(*)
            FROM daily_processed_candidates
            WHERE process_date = ?
              AND created_at >= ?
            """,
            (day, started_at),
        ).fetchone()[0]
        online_views = conn.execute(
            """
            SELECT COUNT(*)
            FROM run_events
            WHERE event_type = 'online_resume_viewed'
              AND created_at >= ?
            """,
            (started_at,),
        ).fetchone()[0]
        forwards = conn.execute(
            """
            SELECT COUNT(*)
            FROM forward_records
            WHERE forwarded_at >= ?
            """,
            (started_at,),
        ).fetchone()[0]
    return int(daily_processed or 0) + int(online_views or 0) + int(forwards or 0)


def validate_main_flow_exit(root: Path, flow_id: str, started_at: str, code: int) -> tuple[str, str, bool]:
    if flow_id not in {"boss-1", "boss-2"}:
        return ("COMPLETED" if code == 0 else "FAILED", f"cron_exit code={code}", code != 0)
    if code != 0:
        return ("FAILED", f"cron_exit code={code}", True)
    activity_count = main_flow_activity_count(root, started_at)
    if activity_count <= 0:
        return (
            "FAILED_NO_SCREENING",
            f"cron_exit code=0 but no candidate/online-resume/forward activity since {started_at}",
            True,
        )
    return ("COMPLETED", f"cron_exit code=0 activity_count={activity_count}", False)


def diagnose(root: Path, flow_id: str, reason: str) -> str:
    script = root / "automations/diagnose_automation_fault.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--flow-id", flow_id, "--reason", reason],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=60,
    )
    text = (proc.stdout or proc.stderr).strip()
    if not text:
        return f"diagnosis_exit={proc.returncode}"
    try:
        data = json.loads(text)
        return str(data.get("summary") or text)[:900]
    except json.JSONDecodeError:
        return text[-900:]


def send_fault_alert(root: Path, flow_id: str, title: str, reason: str, detail: str, *, at: str = "program") -> None:
    if os.environ.get("XIAOZHAO_SUPPRESS_FEISHU") == "1":
        print(f"[{now()}] fault alert skipped by XIAOZHAO_SUPPRESS_FEISHU=1: {title} {reason}", flush=True)
        return
    diagnosis = diagnose(root, flow_id, reason)
    script = root / "skills/zhipin-boss-recruitment-bot/scripts/automation_fault_alert.py"
    stable_signature = f"{title}|{flow_id}|{reason}"
    command = [
        sys.executable,
        str(script),
        "--title",
        title,
        "--task",
        flow_id,
        "--reason",
        reason,
        "--detail",
        detail[:900],
        "--diagnosis",
        diagnosis,
        "--at",
        at,
        "--signature",
        stable_signature,
        "--cooldown-minutes",
        "10080",
    ]
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=60)
    if proc.returncode != 0:
        print(f"[{now()}] fault alert failed: {proc.stderr.strip() or proc.stdout.strip()}", flush=True)
    else:
        print(f"[{now()}] fault alert result: {proc.stdout.strip()}", flush=True)


def release(root: Path, flow_id: str, run_id: str, status: str, note: str) -> None:
    try:
        run_sqlite_store(
            root,
            "automation-lock",
            "--action",
            "release",
            "--flow-id",
            flow_id,
            "--run-id",
            run_id,
            "--status",
            status,
            "--note",
            note[:500],
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[{now()}] release failed: {exc}", flush=True)


def heartbeat(root: Path, flow_id: str, run_id: str, note: str) -> None:
    result = run_sqlite_store(
        root,
        "automation-lock",
        "--action",
        "heartbeat",
        "--flow-id",
        flow_id,
        "--run-id",
        run_id,
        "--note",
        note[:500],
        check=False,
    )
    print(f"[{now()}] heartbeat {flow_id}: {result}", flush=True)


def task_command(task: dict) -> tuple[list[str], str | None]:
    script = task.get("script")
    if script:
        command = [sys.executable, str((package_root() / str(script)).resolve())]
        for arg in task.get("args", []):
            command.append(str(arg))
        return command, None
    model = os.environ.get("XIAOZHAO_CODEX_MODEL") or task.get("model") or "gpt-5.5"
    codex_bin = os.environ.get("CODEX_BIN", "codex")
    prompt = str(task["prompt"])
    if os.environ.get("XIAOZHAO_SUPPRESS_FEISHU") == "1":
        prompt = (
            "本次为本地健康检查恢复执行，用户明确要求不要做任何飞书发送、飞书转发、"
            "飞书故障通知、飞书启动通知或飞书结束通知；只允许本地 SQLite/日志记录。"
            + prompt
        )
    return [
        codex_bin,
        "exec",
        "--cd",
        str(package_root()),
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-m",
        str(model),
        "-",
    ], prompt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_toml", type=Path)
    parser.add_argument("--heartbeat-seconds", type=int, default=240)
    parser.add_argument("--stale-minutes", type=int, default=30)
    args = parser.parse_args()

    root = package_root()
    task_path = args.task_toml.resolve()
    task = load_task(task_path)
    flow_id = str(task["id"])
    name = str(task.get("name") or flow_id)
    if task.get("status") != "ACTIVE":
        print(f"[{now()}] skip inactive task {flow_id} {name}", flush=True)
        return 0

    print(f"[{now()}] starting cron automation {flow_id} {name}", flush=True)
    acquired = run_sqlite_store(
        root,
        "automation-lock",
        "--action",
        "acquire",
        "--flow-id",
        flow_id,
        "--stale-minutes",
        str(args.stale_minutes),
        "--note",
        f"cron_start template={task_path.name}",
    )
    if acquired.get("status") == "blocked":
        print(f"[{now()}] {flow_id} already running: {acquired}", flush=True)
        return 0
    if acquired.get("status") != "acquired":
        print(f"[{now()}] failed to acquire {flow_id}: {acquired}", flush=True)
        return 1

    run_id = str(acquired["run_id"])
    started_at = str(acquired.get("heartbeat_at") or now())
    env = os.environ.copy()
    env["PATH"] = (
        "/Users/helloworld/.hermes/node/bin:/Users/helloworld/.local/bin:"
        "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
        + env.get("PATH", "")
    )
    env["PYTHONUNBUFFERED"] = "1"
    command, stdin_text = task_command(task)
    proc = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.PIPE if stdin_text is not None else None)
    if stdin_text is not None and proc.stdin is not None:
        proc.stdin.write(stdin_text.encode("utf-8"))
        proc.stdin.close()

    def forward_signal(signum: int, _frame: object) -> None:
        print(f"[{now()}] forwarding signal {signum} to {flow_id}", flush=True)
        proc.send_signal(signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)

    last_heartbeat = 0.0
    final_status = "FAILED"
    try:
        while True:
            code = proc.poll()
            current = time.monotonic()
            if current - last_heartbeat >= args.heartbeat_seconds:
                heartbeat(root, flow_id, run_id, f"cron_running pid={proc.pid}")
                last_heartbeat = current
            if code is not None:
                final_status, final_note, should_alert = validate_main_flow_exit(root, flow_id, started_at, code)
                print(f"[{now()}] {flow_id} exited with code {code}", flush=True)
                release(root, flow_id, run_id, final_status, final_note)
                if should_alert:
                    send_fault_alert(
                        root,
                        flow_id,
                        "流程故障",
                        final_note,
                        f"run_id={run_id}; template={task_path.name}",
                    )
                return code
            time.sleep(5)
    except BaseException as exc:  # noqa: BLE001
        release(root, flow_id, run_id, "FAILED", f"cron_exception {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
