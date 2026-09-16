#!/usr/bin/env python3
"""One-shot health check for XiaoZhao crontab automations."""

from __future__ import annotations

import argparse
import os
import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None


DAY_TO_CRON = {"MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6, "SU": 0}


@dataclass(frozen=True)
class Task:
    flow_id: str
    name: str
    path: Path
    days: set[int]
    hour: int
    minute: int


APP_AUTOMATION_IDS = {
    "boss-1": "automation",
    "boss-2": "automation-2",
    "boss-3": "automation-3",
    "boss-4": "automation-4",
    "boss-5": "automation-5",
    "boss-6": "automation-6",
    "boss-7": "sqlite",
    "xiaozhao-unfinished-tickets": "automation-7",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_rrule(rrule: str) -> tuple[set[int], int, int]:
    parts: dict[str, str] = {}
    for item in rrule.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key] = value
    freq = parts.get("FREQ")
    if "BYDAY" in parts:
        days = {DAY_TO_CRON[item] for item in parts["BYDAY"].split(",") if item in DAY_TO_CRON}
    elif freq == "DAILY":
        days = set(range(7))
    else:
        days = set(range(7))
    return days, int(parts.get("BYHOUR", "0")), int(parts.get("BYMINUTE", "0"))


def load_tasks(root: Path) -> list[Task]:
    tasks: list[Task] = []
    for path in sorted((root / "automations").glob("*.toml")):
        if tomllib is not None:
            with path.open("rb") as handle:
                raw = tomllib.load(handle)
        else:
            raw = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, raw_value = stripped.split("=", 1)
                value = raw_value.strip()
                if value.startswith('"') and value.endswith('"'):
                    raw[key.strip()] = value[1:-1].replace('\\"', '"')
                elif value.isdigit():
                    raw[key.strip()] = int(value)
                else:
                    raw[key.strip()] = value
        if raw.get("status") != "ACTIVE":
            continue
        days, hour, minute = parse_rrule(str(raw["rrule"]))
        tasks.append(Task(str(raw["id"]), str(raw.get("name") or raw["id"]), path, days, hour, minute))
    return tasks


def load_toml(path: Path) -> dict:
    if tomllib is not None:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    raw: dict[str, object] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            raw[key.strip()] = value[1:-1].replace('\\"', '"')
        elif value.startswith("[") and value.endswith("]"):
            raw[key.strip()] = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
        elif value.isdigit():
            raw[key.strip()] = int(value)
        else:
            raw[key.strip()] = value
    return raw


def load_codex_app_automations() -> dict[str, dict]:
    automations: dict[str, dict] = {}
    base = Path.home() / ".codex/automations"
    if not base.exists():
        return automations
    for path in sorted(base.glob("*/automation.toml")):
        try:
            raw = load_toml(path)
        except Exception:  # noqa: BLE001
            continue
        automation_id = str(raw.get("id") or path.parent.name)
        raw["_path"] = str(path)
        automations[automation_id] = raw
    return automations


def app_automation_matches_task(task: Task, raw: dict, root: Path) -> list[str]:
    problems: list[str] = []
    workspace_raw = load_toml(task.path)
    if str(raw.get("status") or "") != "ACTIVE":
        problems.append(f"{task.flow_id} Codex App automation is not ACTIVE")
    if str(raw.get("kind") or "") != "cron":
        problems.append(f"{task.flow_id} Codex App automation is not cron kind")
    if str(raw.get("rrule") or "") != str(workspace_raw.get("rrule") or ""):
        problems.append(f"{task.flow_id} Codex App schedule does not match workspace task")
    cwds = raw.get("cwds") or []
    if isinstance(cwds, str):
        cwds = [cwds]
    if str(root) not in [str(item) for item in cwds]:
        problems.append(f"{task.flow_id} Codex App cwd missing {root}")
    return problems


def connect_db(root: Path) -> sqlite3.Connection | None:
    for candidate in [
        root / ".zhipin-copilot/recruitment.sqlite3",
        root / "data/.zhipin-copilot/recruitment.sqlite3",
    ]:
        if candidate.exists():
            conn = sqlite3.connect(str(candidate), timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
    return None


def latest_run(conn: sqlite3.Connection, flow_id: str, day: date | None = None) -> sqlite3.Row | None:
    if day is None:
        return conn.execute(
            """
            SELECT flow_id, run_id, status, started_at, heartbeat_at, ended_at, note
            FROM automation_runs
            WHERE flow_id = ?
            ORDER BY heartbeat_at DESC, started_at DESC, CASE WHEN status = 'RUNNING' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (flow_id,),
        ).fetchone()
    return conn.execute(
        """
        SELECT flow_id, run_id, status, started_at, heartbeat_at, ended_at, note
        FROM automation_runs
        WHERE flow_id = ? AND substr(started_at, 1, 10) = ?
        ORDER BY heartbeat_at DESC, started_at DESC, CASE WHEN status = 'RUNNING' THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (flow_id, day.isoformat()),
    ).fetchone()


def is_stale(heartbeat_at: str, stale_minutes: int, current: datetime) -> bool:
    if not heartbeat_at:
        return True
    try:
        seen = datetime.fromisoformat(heartbeat_at)
    except ValueError:
        return True
    if seen.tzinfo is None:
        seen = seen.astimezone()
    return seen < current - timedelta(minutes=stale_minutes)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def active_window(task: Task, current: datetime) -> tuple[datetime, datetime] | None:
    cron_day = int(current.strftime("%w"))
    if task.flow_id == "boss-1":
        if cron_day in task.days:
            return datetime.combine(current.date(), time(8, 0), current.tzinfo), datetime.combine(current.date(), time(20, 15), current.tzinfo)
        return None
    if task.flow_id == "boss-2":
        if cron_day in task.days:
            return datetime.combine(current.date(), time(19, 0), current.tzinfo), datetime.combine(current.date(), time(21, 15), current.tzinfo)
        return None
    return None


def scheduled_today(task: Task, current: datetime) -> datetime | None:
    cron_day = int(current.strftime("%w"))
    if cron_day not in task.days:
        return None
    return datetime.combine(current.date(), time(task.hour, task.minute), current.tzinfo)


def crontab_text() -> str:
    proc = subprocess.run(["crontab", "-l"], text=True, capture_output=True)
    return proc.stdout if proc.returncode == 0 else ""


def diagnose(root: Path, reason: str) -> str:
    script = root / "automations/diagnose_automation_fault.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--reason", reason],
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


def recent_feishu_or_forward_failures(conn: sqlite3.Connection | None, minutes: int, current: datetime) -> list[str]:
    if conn is None:
        return []
    cutoff = (current - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    try:
        rows = conn.execute(
            """
            SELECT event_type, status, note, created_at
            FROM run_events
            WHERE created_at >= ?
              AND (
                event_type LIKE '%feishu%'
                OR event_type LIKE '%forward%'
                OR lower(COALESCE(note, '')) LIKE '%飞书%'
                OR lower(COALESCE(note, '')) LIKE '%转发%'
                OR lower(COALESCE(detail_text, '')) LIKE '%feishu%'
                OR lower(COALESCE(detail_text, '')) LIKE '%forward%'
              )
              AND lower(COALESCE(status, '')) IN ('failed', 'failure', 'error')
            ORDER BY created_at DESC
            LIMIT 8
            """,
            (cutoff,),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [f"{row['event_type']} {row['status']} {row['created_at']} {row['note'] or ''}".strip() for row in rows]


def failed_reports_for_retry(conn: sqlite3.Connection | None, current: datetime, days: int = 7) -> list[sqlite3.Row]:
    if conn is None:
        return []
    cutoff = (current.date() - timedelta(days=days)).isoformat()
    try:
        return conn.execute(
            """
            SELECT id, report_type, period_start, period_end, sent_status
            FROM reports
            WHERE report_type IN ('daily', 'weekly')
              AND lower(COALESCE(sent_status, '')) = 'failed'
              AND period_end >= ?
            ORDER BY id DESC
            LIMIT 5
            """,
            (cutoff,),
        ).fetchall()
    except sqlite3.Error:
        return []


def retry_failed_reports(root: Path, rows: list[sqlite3.Row]) -> list[str]:
    results: list[str] = []
    if not rows:
        return results
    script = root / "skills/zhipin-boss-recruitment-bot/scripts/report_feishu_sender.py"
    for row in rows:
        report_id = int(row["id"])
        command = [
            sys.executable,
            str(script),
            "--report-type",
            str(row["report_type"]),
            "--period-start",
            str(row["period_start"]),
            "--period-end",
            str(row["period_end"]),
            "--report-id",
            str(report_id),
        ]
        proc = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=90)
        output = (proc.stdout or proc.stderr).strip().replace("\n", " ")
        status = "ok" if proc.returncode == 0 else f"failed code={proc.returncode}"
        results.append(f"report_retry id={report_id} {status}: {output[:700]}")
    return results


def send_fault_alert(root: Path, title: str, reason: str, detail: str, at: str = "program") -> None:
    diagnosis = diagnose(root, reason)
    script = root / "skills/zhipin-boss-recruitment-bot/scripts/automation_fault_alert.py"
    stable_signature = f"{title}|{reason}"
    command = [
        sys.executable,
        str(script),
        "--title",
        title,
        "--task",
        "小昭 crontab 自动化健康检查",
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
    output = proc.stdout.strip() or proc.stderr.strip()
    print(f"[{now_iso()}] alert {title}: {output}", flush=True)


def restart_log_name(task: Task) -> str:
    return task.path.stem + ".log"


def restart_task(root: Path, task: Task, reason: str, *, suppress_feishu: bool = False) -> str:
    runner = Path.home() / ".hermes/bin/xiaozhao-cron/run-cron-automation.sh"
    if not runner.exists():
        runner = root / "bin/run-cron-automation.sh"
    log_dir = Path.home() / ".hermes/logs/xiaozhao_cron"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / restart_log_name(task)
    env = os.environ.copy()
    env["XIAOZHAO_PACKAGE_ROOT"] = str(root)
    if suppress_feishu:
        env["XIAOZHAO_SUPPRESS_FEISHU"] = "1"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] health check restarting {task.flow_id}: {reason}\n")
        proc = subprocess.Popen(
            [str(runner), str(task.path)],
            cwd=root,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return f"{task.flow_id} restart pid={proc.pid} log={log_path}"


def task_process_running(task: Task) -> bool:
    proc = subprocess.run(["pgrep", "-f", f"run_cron_automation.py .*{task.path.name}"], text=True, capture_output=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def stop_task_process(task: Task) -> str:
    proc = subprocess.run(["pgrep", "-f", f"run_cron_automation.py .*{task.path.name}"], text=True, capture_output=True)
    pids = [pid.strip() for pid in proc.stdout.splitlines() if pid.strip().isdigit()]
    if not pids:
        return f"{task.flow_id} no runner process to stop"
    subprocess.run(["kill", "-TERM", *pids], text=True, capture_output=True)
    return f"{task.flow_id} stopped stale/no-activity runner pid(s)={','.join(pids)}"


def main_flow_activity_count(conn: sqlite3.Connection | None, day: date, started_at: str | None) -> int:
    if conn is None:
        return 0
    day_text = day.isoformat()
    since = started_at or day_text
    try:
        daily_processed = conn.execute(
            """
            SELECT COUNT(*)
            FROM daily_processed_candidates
            WHERE process_date = ?
              AND created_at >= ?
            """,
            (day_text, since),
        ).fetchone()[0]
        online_views = conn.execute(
            "SELECT COUNT(*) FROM run_events WHERE event_type = 'online_resume_viewed' AND created_at >= ?",
            (since,),
        ).fetchone()[0]
        forwards = conn.execute(
            "SELECT COUNT(*) FROM forward_records WHERE forwarded_at >= ?",
            (since,),
        ).fetchone()[0]
    except sqlite3.Error:
        return 0
    return int(daily_processed or 0) + int(online_views or 0) + int(forwards or 0)


def release_false_running(root: Path, task: Task, row: sqlite3.Row | None, reason: str) -> str:
    if row is None:
        return ""
    run_id = str(row["run_id"] or "")
    if not run_id:
        return ""
    script = root / "skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "automation-lock",
            "--action",
            "release",
            "--flow-id",
            task.flow_id,
            "--run-id",
            run_id,
            "--status",
            "FAILED",
            "--note",
            reason[:500],
        ],
        cwd=root,
        text=True,
        capture_output=True,
    )
    detail = proc.stdout.strip() or proc.stderr.strip()
    return f"{task.flow_id} released false RUNNING {run_id}: {detail}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-minutes", type=int, default=15)
    parser.add_argument("--one-shot-grace-minutes", type=int, default=45)
    parser.add_argument("--startup-activity-grace-minutes", type=int, default=3)
    parser.add_argument("--scheduler", choices=["auto", "crontab", "codex-app"], default="auto")
    parser.add_argument("--no-auto-restart", action="store_true")
    parser.add_argument("--no-alert", action="store_true")
    args = parser.parse_args()

    root = package_root()
    current = datetime.now().astimezone()
    tasks = load_tasks(root)
    cron = crontab_text()
    app_automations = load_codex_app_automations()
    has_crontab_block = "BEGIN XIAOZHAO ROBOT AUTOMATIONS" in cron
    scheduler = args.scheduler
    if scheduler == "auto":
        scheduler = "crontab" if has_crontab_block else "codex-app"
    conn = connect_db(root)
    problems: list[str] = []
    restarts: list[str] = []

    print(f"[{now_iso()}] checking {len(tasks)} automations scheduler={scheduler}", flush=True)
    if conn is None:
        problems.append("SQLite database not found")

    if scheduler == "crontab" and not has_crontab_block:
        problems.append("managed crontab block missing")
    if scheduler == "codex-app" and has_crontab_block:
        problems.append("managed crontab block still present while scheduler=codex-app")

    for task in tasks:
        if scheduler == "crontab" and task.path.name not in cron:
            problems.append(f"{task.flow_id} crontab entry missing")
        if scheduler == "codex-app":
            app_id = APP_AUTOMATION_IDS.get(task.flow_id)
            raw = app_automations.get(app_id or "")
            if raw is None:
                problems.append(f"{task.flow_id} Codex App automation missing id={app_id}")
            else:
                problems.extend(app_automation_matches_task(task, raw, root))

        row = latest_run(conn, task.flow_id, current.date()) if conn is not None else None
        latest = latest_run(conn, task.flow_id) if conn is not None else None
        window = active_window(task, current)
        status = "NO_DB"
        no_screening_activity = False
        completed_with_screening_activity = False

        if row is not None:
            run_status = str(row["status"] or "")
            heartbeat_at = str(row["heartbeat_at"] or "")
            stale = is_stale(heartbeat_at, args.stale_minutes, current)
            if run_status == "RUNNING" and not stale:
                status = "RUNNING"
                if task.flow_id in {"boss-1", "boss-2", "boss-3", "xiaozhao-unfinished-tickets"} and not task_process_running(task):
                    status = "MISSING_PROCESS"
                    problems.append(f"{task.flow_id} heartbeat exists but process is missing")
                elif task.flow_id in {"boss-1", "boss-2"}:
                    started_at = str(row["started_at"] or "")
                    started_dt = parse_dt(started_at)
                    activity = main_flow_activity_count(conn, current.date(), started_at)
                    if (
                        started_dt is not None
                        and current >= started_dt + timedelta(minutes=args.startup_activity_grace_minutes)
                        and activity <= 0
                    ):
                        status = "RUNNING_NO_ACTIVITY"
                        problems.append(
                            f"{task.flow_id} is RUNNING but has no candidate/browser activity "
                            f"since {started_at}"
                        )
            elif run_status == "RUNNING":
                status = "STALE"
                problems.append(f"{task.flow_id} heartbeat stale at {heartbeat_at}")
            elif run_status in {"COMPLETED", "SKIPPED"}:
                status = run_status
                if task.flow_id in {"boss-1", "boss-2"} and run_status == "COMPLETED":
                    activity = main_flow_activity_count(conn, current.date(), str(row["started_at"] or ""))
                    if activity <= 0:
                        status = "COMPLETED_NO_SCREENING"
                        no_screening_activity = True
                        problems.append(f"{task.flow_id} completed without screening activity")
                    else:
                        completed_with_screening_activity = True
            else:
                status = run_status or "UNKNOWN"
                problems.append(f"{task.flow_id} ended with status {status}")
        else:
            status = "MISSING_TODAY"

        if window is not None and window[0] <= current <= window[1]:
            if status != "RUNNING":
                if completed_with_screening_activity:
                    print(
                        f"[{now_iso()}] {task.flow_id} completed with screening activity during active window; no restart needed",
                        flush=True,
                    )
                    continue
                problems.append(f"{task.flow_id} should be running now but is {status}")
                if scheduler in {"crontab", "codex-app"} and not args.no_auto_restart and task.flow_id in {"boss-1", "boss-2"}:
                    try:
                        if status in {"MISSING_PROCESS", "RUNNING_NO_ACTIVITY"}:
                            if status == "RUNNING_NO_ACTIVITY":
                                restarts.append(stop_task_process(task))
                            release_reason = (
                                "health_check_running_without_activity"
                                if status == "RUNNING_NO_ACTIVITY"
                                else "health_check_false_running_no_process"
                            )
                            restarts.append(release_false_running(root, task, row, release_reason))
                        if no_screening_activity:
                            restarts.append(release_false_running(root, task, row, "health_check_completed_without_screening"))
                        restarts.append(restart_task(root, task, f"active window status={status}", suppress_feishu=args.no_alert))
                    except Exception as exc:  # noqa: BLE001
                        problems.append(f"{task.flow_id} restart failed: {type(exc).__name__}: {exc}")
        else:
            scheduled_at = scheduled_today(task, current)
            if scheduled_at and current >= scheduled_at + timedelta(minutes=args.one_shot_grace_minutes):
                if row is None:
                    problems.append(f"{task.flow_id} missing today's scheduled run")
                    # One-shot reporting tasks must be triggered only by their cron
                    # schedule; health checks should report missing state but never
                    # rerun them, or they can send duplicate Feishu reports.
                elif status == "STALE":
                    problems.append(f"{task.flow_id} scheduled run is stale")

        latest_text = "none"
        if latest is not None:
            latest_text = f"{latest['status']}@{latest['heartbeat_at']}"
        print(f"[{now_iso()}] {task.flow_id} {task.name}: today={status}; latest={latest_text}", flush=True)

    send_failures = recent_feishu_or_forward_failures(conn, 10, current)
    report_retry_results: list[str] = []
    if send_failures:
        if not args.no_auto_restart:
            report_retry_results = retry_failed_reports(root, failed_reports_for_retry(conn, current))
            if report_retry_results:
                restarts.extend(report_retry_results)
        problems.append("recent Feishu/forward failure detected; retry attempted" if report_retry_results else "recent Feishu/forward failure detected")

    if problems:
        print(f"[{now_iso()}] ATTENTION", flush=True)
        for problem in problems:
            print(f"- {problem}", flush=True)
        for restart in restarts:
            print(f"- {restart}", flush=True)
        if args.no_alert:
            print(f"[{now_iso()}] alert skipped by --no-alert", flush=True)
        else:
            send_fault_alert(
                root,
                "流程故障或飞书转发故障",
                "；".join(problems[:6]),
                "\n".join(problems + send_failures + restarts),
            )
        return 2
    print(f"[{now_iso()}] OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
