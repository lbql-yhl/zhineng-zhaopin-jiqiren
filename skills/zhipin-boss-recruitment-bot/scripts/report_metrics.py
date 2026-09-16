#!/usr/bin/env python3
"""Build aggregate daily/weekly report metrics from the XiaoZhao SQLite store."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(".zhipin-copilot/recruitment.sqlite3")
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
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


def assert_public_report_body(body: str) -> None:
    forbidden = [fragment for fragment in FORBIDDEN_VISIBLE_REPORT_FRAGMENTS if fragment in body]
    if forbidden:
        raise ValueError("对外报告禁止展示内部数据源/数据链路：" + "、".join(forbidden))


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-20000")
    return conn


def parse_day(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now().astimezone().date()


def default_window(report_type: str, anchor: date) -> tuple[date, date]:
    if report_type == "daily":
        target = anchor - timedelta(days=1)
        return target, target
    monday = anchor - timedelta(days=anchor.weekday())
    previous_monday = monday - timedelta(days=7)
    return previous_monday, previous_monday + timedelta(days=6)


def day_bounds(start: date, end: date) -> tuple[str, str]:
    return start.isoformat(), end.isoformat()


def iter_reverse_lines(path: Path, block_size: int = 1024 * 1024):
    with path.open("rb") as fh:
        fh.seek(0, 2)
        position = fh.tell()
        buffer = b""
        while position > 0:
            read_size = min(block_size, position)
            position -= read_size
            fh.seek(position)
            buffer = fh.read(read_size) + buffer
            lines = buffer.splitlines()
            if position > 0 and lines:
                buffer = lines.pop(0)
            else:
                buffer = b""
            for line in reversed(lines):
                if line:
                    yield line.decode("utf-8", errors="replace")
        if buffer:
            yield buffer.decode("utf-8", errors="replace")


def token_total_for_session_file(path: Path) -> int | None:
    try:
        lines = iter_reverse_lines(path)
        for line in lines:
            if "token_count" not in line or "total_token_usage" not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload") if isinstance(event, dict) else {}
            if not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            total_usage = info.get("total_token_usage") if isinstance(info.get("total_token_usage"), dict) else {}
            total_tokens = total_usage.get("total_tokens")
            if isinstance(total_tokens, int):
                return total_tokens
    except OSError:
        return None
    return None


def codex_token_total_for_day(day: date, sessions_dir: Path = CODEX_SESSIONS_DIR) -> int | None:
    day_dir = sessions_dir / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
    if not day_dir.exists():
        return None
    total = 0
    found = False
    for path in sorted(day_dir.glob("*.jsonl")):
        tokens = token_total_for_session_file(path)
        if tokens is None:
            continue
        total += tokens
        found = True
    return total if found else None


def codex_token_total_for_period(start: date, end: date) -> int | None:
    total = 0
    found = False
    day = start
    while day <= end:
        day_total = codex_token_total_for_day(day)
        if day_total is not None:
            total += day_total
            found = True
        day += timedelta(days=1)
    return total if found else None


def canonical_job(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "未标记岗位"
    lowered = text.lower()
    if "运营负责人" in lowered:
        return "运营负责人"
    if "海外广告优化师" in lowered:
        return "海外广告优化师（双休）"
    if "ui设计师" in lowered or "ui设计" in lowered:
        return "Ui设计师"
    return text


def fetch_scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def processed_total(conn: sqlite3.Connection, start: str, end: str) -> int:
    # Daily/weekly visible totals are defined by the date-level reporting table.
    # `screening_run_seen_candidates` is a list-stage operational table and can
    # be partial after recovery/migration cycles, so it must not override the
    # canonical daily processed count when daily rows exist.
    daily_count = fetch_scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM daily_processed_candidates
        WHERE process_date BETWEEN ? AND ?
        """,
        (start, end),
    )
    if daily_count:
        return daily_count
    list_count = fetch_scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM screening_run_seen_candidates
        WHERE date(seen_at) BETWEEN ? AND ?
        """,
        (start, end),
    )
    if list_count:
        return list_count
    return fetch_scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM processed_candidates
        WHERE date(processed_at) BETWEEN ? AND ?
        """,
        (start, end),
    )


def success_forwards(conn: sqlite3.Connection, start: str, end: str) -> int:
    return sum(len(candidates) for candidates in forwarded_candidates_by_job(conn, start, end).values())


def hard_fail_count(conn: sqlite3.Connection, start: str, end: str) -> int:
    # Keep the global funnel closed: processed candidates = forwarded + hard-fail.
    # Operational list/open queues can be partial or use a narrower stage scope.
    # Final reports cross-check list, processed, online-view, and forward tables.
    total = processed_total(conn, start, end)
    return max(total - success_forwards(conn, start, end), 0)


def job_breakdown(conn: sqlite3.Connection, start: str, end: str) -> list[dict[str, Any]]:
    funnel = funnel_metrics(conn, start, end)
    funnel_jobs = funnel.get("jobs") if isinstance(funnel.get("jobs"), dict) else {}
    forwarded_by_job = forwarded_candidates_by_job(conn, start, end)
    report_total = processed_total(conn, start, end)
    funnel_visible_total = int(funnel.get("visible_total") or 0)
    use_funnel_denominator = bool(funnel_visible_total and funnel_visible_total >= report_total)
    processed_rows = conn.execute(
        """
        SELECT job_ref, COUNT(*) AS processed
        FROM processed_candidates
        WHERE date(processed_at) BETWEEN ? AND ?
        GROUP BY job_ref
        """,
        (start, end),
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for job, values in funnel_jobs.items():
        if not isinstance(values, dict):
            continue
        visible = int(values.get("visible_total") or 0)
        if visible:
            grouped.setdefault(job, {"job": job, "processed": 0, "forwarded": 0, "hard_fail": 0, "visible": 0})
            grouped[job]["visible"] = visible

    for row in processed_rows:
        job = canonical_job(row["job_ref"])
        grouped.setdefault(job, {"job": job, "processed": 0, "forwarded": 0, "hard_fail": 0, "visible": 0})
        grouped[job]["processed"] += int(row["processed"] or 0)

    for job, candidates in forwarded_by_job.items():
        grouped.setdefault(job, {"job": job, "processed": 0, "forwarded": 0, "hard_fail": 0, "visible": 0})
        grouped[job]["forwarded"] = len(candidates)

    for item in grouped.values():
        job = str(item["job"])
        job_funnel = funnel_jobs.get(job, {}) if isinstance(funnel_jobs, dict) else {}
        visible = int(item.get("visible") or 0)
        duplicate = int(job_funnel.get("duplicate_total") or 0)
        if not duplicate:
            duplicate = int(job_funnel.get("duplicate_global") or 0) + int(job_funnel.get("duplicate_same_run") or 0)
        skipped = int(job_funnel.get("list_skipped") or 0)
        open_queue = int(job_funnel.get("list_open_queue") or 0)
        unknown = int(job_funnel.get("unknown_visible") or 0)
        judged_total = open_queue + skipped + unknown
        if visible and not judged_total:
            judged_total = max(visible - duplicate, 0)
        if use_funnel_denominator and judged_total:
            # The job-level report must use the same live-list funnel口径 as the
            # global totals.  `processed_candidates` can lag for historical runs
            # (for example when list-stage rows were tracked in the list funnel
            # but not fully backfilled into the processed table).  Showing the
            # lower persisted-row count made the visible job block internally
            # inconsistent: forwarded + hard_fail could exceed “入库候选人”.
            # Use the deduped judged/list-prefilter total whenever the funnel is
            # available so each job reconciles with the global report.
            item["processed"] = judged_total
        denominator = (judged_total if use_funnel_denominator else 0) or int(item["processed"] or 0)
        item["hard_fail"] = max(denominator - int(item["forwarded"] or 0), 0)
        item["pass_rate"] = round((int(item["forwarded"] or 0) / denominator * 100), 1) if denominator else 0.0

    assigned_total = sum(int(item.get("processed") or 0) for item in grouped.values())
    if report_total > assigned_total:
        gap = report_total - assigned_total
        grouped["未标记岗位"] = {
            "job": "未标记岗位",
            "processed": gap,
            "forwarded": 0,
            "hard_fail": gap,
            "visible": 0,
            "pass_rate": 0.0,
        }
    return sorted(grouped.values(), key=lambda item: (-(int(item.get("visible") or item.get("processed") or 0)), item["job"]))


def forwarded_candidates_by_job(conn: sqlite3.Connection, start: str, end: str) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    processed_rows = conn.execute(
        """
        SELECT job_ref, candidate_ref, candidate_name, date(processed_at) AS day
        FROM processed_candidates
        WHERE date(processed_at) BETWEEN ? AND ?
          AND status = 'forwarded'
        """,
        (start, end),
    ).fetchall()
    for row in processed_rows:
        job = canonical_job(row["job_ref"])
        candidate = str(row["candidate_ref"] or row["candidate_name"] or "").strip()
        if candidate:
            grouped[job].add(f"{row['day']}|{candidate}")

    forward_rows = conn.execute(
        """
        SELECT job_ref, candidate_ref, candidate_key, date(forwarded_at) AS day
        FROM forward_records
        WHERE date(forwarded_at) BETWEEN ? AND ?
          AND lower(COALESCE(status, '')) = 'success'
          -- Legacy HR-review forwards were hard-fail candidates and must not
          -- count as successful JD passes.
          AND COALESCE(note, '') NOT LIKE 'UNSUITABLE_REVIEW%'
        """,
        (start, end),
    ).fetchall()
    for row in forward_rows:
        job = canonical_job(row["job_ref"])
        candidate = str(row["candidate_ref"] or row["candidate_key"] or "").strip()
        if candidate:
            grouped[job].add(f"{row['day']}|{candidate}")

    event_rows = conn.execute(
        """
        SELECT job_ref, candidate_ref, note, date(created_at) AS day
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND (
            (event_type IN ('boss_forward_success', 'forward_success') AND lower(COALESCE(status, '')) IN ('ok', 'success'))
            OR (event_type = 'boss_forward' AND lower(COALESCE(status, '')) = 'success')
          )
          -- Keep legacy hard-fail review forwards out of the hard-requirement
          -- pass metric.
          AND COALESCE(note, '') NOT LIKE 'UNSUITABLE_REVIEW%'
        """,
        (start, end),
    ).fetchall()
    for row in event_rows:
        job = canonical_job(row["job_ref"])
        candidate = str(row["candidate_ref"] or row["note"] or "").strip()
        if candidate:
            grouped[job].add(f"{row['day']}|{candidate}")
    return dict(grouped)


def online_resume_by_job(conn: sqlite3.Connection, start: str, end: str) -> dict[str, int]:
    # Visible report wording is "opened online resumes". Count operation events,
    # not distinct candidates and not the list-stage queued subset, because
    # recovery cycles can legitimately reopen/check the same resume and users
    # compare this number with `online_resume_viewed` event totals.
    rows = conn.execute(
        """
        SELECT job_ref, COUNT(*) AS opened
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND event_type = 'online_resume_viewed'
          AND lower(COALESCE(status, '')) IN ('viewed', 'opened', 'success', 'ok')
        GROUP BY job_ref
        """,
        (start, end),
    ).fetchall()
    grouped: dict[str, int] = defaultdict(int)
    for row in rows:
        grouped[canonical_job(row["job_ref"])] += int(row["opened"] or 0)
    if grouped:
        return dict(grouped)

    rows = conn.execute(
        """
        SELECT job_ref, COUNT(*) AS opened
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND event_type = 'online_resume_view'
          AND lower(COALESCE(status, '')) IN ('viewed', 'opened', 'success', 'ok')
        GROUP BY job_ref
        """,
        (start, end),
    ).fetchall()
    for row in rows:
        grouped[canonical_job(row["job_ref"])] += int(row["opened"] or 0)
    if grouped:
        return dict(grouped)

    seen_rows = conn.execute(
        """
        SELECT job_ref, COUNT(*) AS opened
        FROM screening_run_seen_candidates
        WHERE date(seen_at) BETWEEN ? AND ?
          AND status = 'queued_open_resume'
        GROUP BY job_ref
        """,
        (start, end),
    ).fetchall()
    for row in seen_rows:
        grouped[canonical_job(row["job_ref"])] += int(row["opened"] or 0)
    return dict(grouped)


def _batch_events(conn: sqlite3.Connection, start: str, end: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT job_ref, detail_text
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND event_type = 'batch_list_prefilter'
        """,
        (start, end),
    ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["detail_text"] or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload["job_ref"] = payload.get("job_ref") or row["job_ref"]
            events.append(payload)
    return events


def funnel_metrics(conn: sqlite3.Connection, start: str, end: str) -> dict[str, Any]:
    batches = _batch_events(conn, start, end)
    opened_online = sum(online_resume_by_job(conn, start, end).values())
    fallback = _funnel_metrics_from_seen(conn, start, end, opened_online)
    if batches:
        by_job: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # type: ignore[assignment]
        totals = {
            "visible_total": 0,
            "list_open_queue": 0,
            "list_skipped": 0,
            "duplicate_global": 0,
            "duplicate_same_run": 0,
            "list_failed_age": 0,
            "list_failed_education": 0,
            "unknown_visible": 0,
        }
        for event in batches:
            job = canonical_job(event.get("job_ref"))
            mapping = {
                "visible_total": "total",
                "list_open_queue": "open_count",
                "list_skipped": "skip_count",
                "duplicate_global": "duplicate_count",
                "duplicate_same_run": "seen_in_run_count",
                "list_failed_age": "failed_age_count",
                "list_failed_education": "failed_education_count",
                "unknown_visible": "unknown_visible_count",
            }
            for target, source in mapping.items():
                value = int(event.get(source) or 0)
                totals[target] += value
                by_job[job][target] += value
        totals["duplicate_total"] = totals["duplicate_global"] + totals["duplicate_same_run"]
        totals["opened_online"] = opened_online
        batch_result = {"source": "batch_list_prefilter", **totals, "jobs": dict(by_job)}
        if int(batch_result["visible_total"] or 0) >= int(fallback["visible_total"] or 0):
            return batch_result
        fallback["source"] = "screening_run_seen_candidates_fallback_partial_batch"
        return fallback

    return fallback


def _funnel_metrics_from_seen(conn: sqlite3.Connection, start: str, end: str, opened_online: int) -> dict[str, Any]:
    seen_rows = conn.execute(
        """
        SELECT job_ref, status, COUNT(*) AS count
        FROM screening_run_seen_candidates
        WHERE date(seen_at) BETWEEN ? AND ?
        GROUP BY job_ref, status
        """,
        (start, end),
    ).fetchall()
    totals = {
        "visible_total": 0,
        "list_open_queue": 0,
        "list_skipped": 0,
        "duplicate_global": 0,
        "duplicate_same_run": 0,
        "list_failed_age": 0,
        "list_failed_education": 0,
        "unknown_visible": 0,
    }
    by_job: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # type: ignore[assignment]
    for row in seen_rows:
        job = canonical_job(row["job_ref"])
        status = str(row["status"] or "")
        count = int(row["count"] or 0)
        totals["visible_total"] += count
        by_job[job]["visible_total"] += count
        if status == "queued_open_resume":
            totals["list_open_queue"] += count
            by_job[job]["list_open_queue"] += count
        elif status == "duplicate_global":
            totals["duplicate_global"] += count
            by_job[job]["duplicate_global"] += count
        elif status == "REJECT_LIST_AGE_PRECHECK":
            totals["list_skipped"] += count
            totals["list_failed_age"] += count
            by_job[job]["list_skipped"] += count
            by_job[job]["list_failed_age"] += count
        elif status == "REJECT_LIST_EDUCATION_PRECHECK":
            totals["list_skipped"] += count
            totals["list_failed_education"] += count
            by_job[job]["list_skipped"] += count
            by_job[job]["list_failed_education"] += count
    totals["duplicate_total"] = totals["duplicate_global"] + totals["duplicate_same_run"]
    totals["opened_online"] = opened_online
    return {"source": "screening_run_seen_candidates_fallback", **totals, "jobs": dict(by_job)}


def classify_fail_reason(note: str, status: str = "", job_ref: str = "") -> str:
    text = f"{status} {note}".lower()
    job = canonical_job(job_ref)
    if "reject_list_age_precheck" in text:
        return "年龄不符合"
    if "reject_list_education_precheck" in text:
        return "学历不符合"
    if re.search(r"(age|年龄|max_age)[^;。；]*(fail|exceed|not_below|violat|max_age|不符合|未满足|>=|大于|超过)", text):
        return "年龄不符合"
    if re.search(r"(education|学历|大专|本科)[^;。；]*(fail|below|不符合|未满足|不足)", text):
        return "学历不符合"
    if any(token in text for token in ["middle east", "middle_east", "中东", "overseas middle east", "overseas_region", "overseas region"]):
        return "中东/海外区域经验不符合"
    if any(token in text for token in ["投放", "广告投放", "media buying", "ads", "advertising", "优化师"]):
        return "广告投放经验不符合"
    if any(
        token in text
        for token in [
            "target",
            "product",
            "social",
            "voice",
            "live",
            "ai social",
            "语聊",
            "语音",
            "直播",
            "社交",
            "ui evidence",
            "业务",
        ]
    ):
        return "目标产品/业务经验不符合"
    if any(token in text for token in ["duration", "insufficient", "under 1 year", "1y", "2y", "mo", "months", "年限", "不足", "不满"]):
        return "相关经验年限不足"
    if job == "运营负责人":
        return "中东/海外运营及语聊项目经验不符合"
    if job == "海外广告优化师（双休）":
        return "目标海外社交/直播/语聊/AI社交广告投放经验不符合"
    if job == "Ui设计师":
        return "目标社交/直播/语聊/AI社交产品UI经验不符合"
    return "目标产品/业务经验不符合"


def job_reason_breakdown(conn: sqlite3.Connection, start: str, end: str) -> dict[str, dict[str, int]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # type: ignore[assignment]
    seen: set[tuple[str, str]] = set()
    rows = conn.execute(
        """
        SELECT job_ref, candidate_ref, candidate_name, status, note
        FROM processed_candidates
        WHERE date(processed_at) BETWEEN ? AND ?
          AND status IN ('REJECT_LIST_AGE_PRECHECK', 'REJECT_LIST_EDUCATION_PRECHECK', 'hard_fail', 'skipped')
        """,
        (start, end),
    ).fetchall()
    for row in rows:
        job = canonical_job(row["job_ref"])
        candidate_key = str(row["candidate_ref"] or row["candidate_name"] or "")
        if candidate_key and (job, candidate_key) in seen:
            continue
        if candidate_key:
            seen.add((job, candidate_key))
        grouped[job][classify_fail_reason(row["note"] or "", row["status"] or "", row["job_ref"] or "")] += 1
    if grouped:
        return {job: dict(reasons) for job, reasons in grouped.items()}

    event_rows = conn.execute(
        """
        SELECT job_ref, candidate_ref, status, note, detail_text
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND event_type IN ('hard_gate_result', 'hard_gate')
          AND lower(COALESCE(status, '')) IN ('fail', 'failed')
        """,
        (start, end),
    ).fetchall()
    for row in event_rows:
        job = canonical_job(row["job_ref"])
        candidate_key = str(row["candidate_ref"] or "")
        if candidate_key and (job, candidate_key) in seen:
            continue
        if candidate_key:
            seen.add((job, candidate_key))
        note = " ".join([str(row["note"] or ""), str(row["detail_text"] or "")]).strip()
        grouped[job][classify_fail_reason(note, row["status"] or "", row["job_ref"] or "")] += 1
    return {job: dict(reasons) for job, reasons in grouped.items()}


def format_reason_lines(reasons_by_job: dict[str, dict[str, int]]) -> list[str]:
    if not reasons_by_job:
        return ["    - 暂无结构化不符合原因记录。"]
    lines: list[str] = []
    for job in sorted(reasons_by_job):
        reasons = reasons_by_job[job]
        parts = [f"{reason} {count}位" for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))]
        lines.append(f"    - [{job}]：" + "；".join(parts))
    return lines


def cap_reasons_by_job(reasons_by_job: dict[str, dict[str, int]], jobs: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    limits = {str(item["job"]): int(item.get("hard_fail") or 0) for item in jobs}
    capped: dict[str, dict[str, int]] = {}
    for job, reasons in reasons_by_job.items():
        remaining = limits.get(job)
        if remaining is None:
            capped[job] = dict(reasons)
            continue
        capped[job] = {}
        for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
            if remaining <= 0:
                break
            value = min(int(count or 0), remaining)
            if value > 0:
                capped[job][reason] = value
                remaining -= value
    return capped


def format_reason_summary_from_breakdown(reasons_by_job: dict[str, dict[str, int]]) -> str:
    totals: dict[str, int] = defaultdict(int)
    for reasons in reasons_by_job.values():
        for reason, count in reasons.items():
            totals[reason] += count
    if not totals:
        return "当前周期没有结构化硬性条件缺失样本，暂无法形成未转发原因分布。"
    parts = [f"{reason}（{count}）" for reason, count in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:5]]
    return "；".join(parts)


def reason_summary(conn: sqlite3.Connection, start: str, end: str) -> str:
    rows = conn.execute(
        """
        SELECT hard_fail_reasons, missing_evidence, risk_reason, COUNT(*) AS count
        FROM matches
        WHERE date(matched_at) BETWEEN ? AND ?
          AND (decision_tier = 'REJECT_DAILY_REPORT' OR hard_pass = 0)
        GROUP BY hard_fail_reasons, missing_evidence, risk_reason
        ORDER BY count DESC
        LIMIT 5
        """,
        (start, end),
    ).fetchall()
    if not rows:
        return "当前周期没有硬性条件缺失样本，暂无法形成未转发原因分布。"
    parts: list[str] = []
    for row in rows:
        reason = row["hard_fail_reasons"] or row["missing_evidence"] or row["risk_reason"] or "简历证据不足"
        parts.append(f"{reason}（{row['count']}）")
    return "；".join(parts)


def run_status(conn: sqlite3.Connection, start: str, end: str) -> str:
    related_types = (
        "batch_list_prefilter",
        "list_prefilter",
        "list_prefilter_skip",
        "online_resume_viewed",
        "online_resume_view",
        "resume_bottom",
        "resume_bottom_read",
        "bottom_read",
        "online_resume_bottom_read",
        "hard_gate_result",
        "hard_gate",
        "boss_forward",
        "boss_forward_success",
        "forward_success",
        "job_switch",
        "checkpoint",
        "shutdown_notice",
    )
    placeholders = ",".join("?" for _ in related_types)
    row = conn.execute(
        f"""
        SELECT MIN(created_at) AS first_at, MAX(created_at) AS last_at, COUNT(*) AS count
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND event_type IN ({placeholders})
        """,
        (start, end, *related_types),
    ).fetchone()
    if not row or not row["count"]:
        return "无运行事件记录"

    first_at = str(row["first_at"])
    last_at = str(row["last_at"])
    try:
        first_dt = datetime.fromisoformat(first_at)
        last_dt = datetime.fromisoformat(last_at)
        minutes = max(int(round((last_dt - first_dt).total_seconds() / 60)), 0)
        hours, mins = divmod(minutes, 60)
        duration = f"{hours}小时{mins}分钟" if hours else f"{mins}分钟"
        window = f"{first_dt:%H:%M}-{last_dt:%H:%M}"
    except ValueError:
        duration = "已记录"
        window = f"{first_at} 至 {last_at}"

    blocker_rows = conn.execute(
        """
        SELECT event_type, COUNT(*) AS count
        FROM run_events
        WHERE date(created_at) BETWEEN ? AND ?
          AND (
            lower(COALESCE(status, '')) IN ('blocked', 'error')
            OR event_type IN ('automation_fault_alert', 'login_blocked', 'security_verification', 'safety_stop')
            OR lower(COALESCE(note, '')) LIKE '%验证码%'
            OR lower(COALESCE(note, '')) LIKE '%登录%'
            OR lower(COALESCE(note, '')) LIKE '%安全%'
          )
          AND event_type NOT IN ('hard_gate_result')
        GROUP BY event_type
        """,
        (start, end),
    ).fetchall()
    blocker_count = sum(int(item["count"] or 0) for item in blocker_rows)
    if blocker_count:
        return f"运行约 {duration}（{window}），存在中断/异常，记录到 {blocker_count} 条流程阻断或故障事件。"
    return f"运行约 {duration}（{window}），正常"


def heartbeat_status(conn: sqlite3.Connection, day: date, stale_minutes: int) -> str:
    stale_before = (datetime.now().astimezone() - timedelta(minutes=stale_minutes)).isoformat(timespec="seconds")
    flow_ids = ["boss-1", "boss-2", "boss-3", "boss-4", "xiaozhao-unfinished-tickets"]
    parts: list[str] = []
    stale_or_missing = 0
    day_text = day.isoformat()
    for flow_id in flow_ids:
        try:
            row = conn.execute(
                """
                SELECT run_id, status, heartbeat_at
                FROM automation_runs
                WHERE flow_id = ?
                  AND substr(started_at, 1, 10) = ?
                ORDER BY heartbeat_at DESC
                LIMIT 1
                """,
                (flow_id, day_text),
            ).fetchone()
        except sqlite3.OperationalError:
            return "当天自动化心跳：不可用（数据库缺少 automation_runs 表）"
        if row is None:
            parts.append(f"{flow_id}:MISSING")
            stale_or_missing += 1
            continue
        status = str(row["status"] or "")
        heartbeat_at = str(row["heartbeat_at"] or "")
        if status == "RUNNING" and heartbeat_at >= stale_before:
            check_status = "OK"
        elif status == "RUNNING":
            check_status = "STALE"
            stale_or_missing += 1
        elif status in {"COMPLETED", "SKIPPED"}:
            check_status = status
        else:
            check_status = status or "UNKNOWN"
            stale_or_missing += 1
        parts.append(f"{flow_id}:{check_status}")
    prefix = "正常" if stale_or_missing == 0 else "需关注"
    return f"当天自动化心跳：{prefix}（" + "；".join(parts) + "）"


def build_report(
    conn: sqlite3.Connection,
    report_type: str,
    start: date,
    end: date,
    token_total: int | None,
    heartbeat_day: date | None = None,
    stale_minutes: int = 30,
) -> dict[str, Any]:
    # User-owned visible format: do not change daily/weekly structure without
    # explicit user approval. Weekly mirrors daily with period wording only.
    start_text, end_text = day_bounds(start, end)
    total = processed_total(conn, start_text, end_text)
    forwarded = success_forwards(conn, start_text, end_text)
    hard_fail = hard_fail_count(conn, start_text, end_text)
    jobs = job_breakdown(conn, start_text, end_text)
    online_by_job = online_resume_by_job(conn, start_text, end_text)
    funnel = funnel_metrics(conn, start_text, end_text)
    reasons_by_job = job_reason_breakdown(conn, start_text, end_text)
    period_word = "今日" if report_type == "daily" else "上周"
    title = "工作日报" if report_type == "daily" else "工作周报"
    token_text = "未统计到" if token_total is None else f"{token_total:,}"
    status = run_status(conn, start_text, end_text)
    job_lines = ["    - 今日无岗位筛选记录。" if report_type == "daily" else "    - 上周无岗位筛选记录。"]
    if jobs:
        funnel_jobs = funnel.get("jobs") if isinstance(funnel.get("jobs"), dict) else {}
        use_funnel_display = int(funnel.get("visible_total") or 0) >= total
        job_lines = []
        for item in jobs:
            job = item["job"]
            job_funnel = funnel_jobs.get(job, {}) if isinstance(funnel_jobs, dict) else {}
            if use_funnel_display:
                job_visible = int(job_funnel.get("visible_total") or 0)
                job_duplicate = int(job_funnel.get("duplicate_total") or 0)
                if not job_duplicate:
                    job_duplicate = int(job_funnel.get("duplicate_global") or 0) + int(job_funnel.get("duplicate_same_run") or 0)
                job_list_skipped = int(job_funnel.get("list_skipped") or 0)
            else:
                job_visible = int(item["processed"] or 0)
                job_duplicate = 0
                job_reasons = reasons_by_job.get(job, {}) if isinstance(reasons_by_job, dict) else {}
                job_list_skipped = int(job_reasons.get("年龄不符合") or 0) + int(job_reasons.get("学历不符合") or 0)
            job_online = int(online_by_job.get(job, 0))
            job_lines.extend(
                [
                    f"    - [{job}]",
                    f"      岗位总数据：{job_visible} 位；列表读取：{job_visible} 位",
                    f"      列表阶段：重复 {job_duplicate} 位；列表弃选 {job_list_skipped} 位；打开在线简历 {job_online} 份",
                    f"      入库候选人：{item['processed']} 位",
                    f"      结果：硬性条件通过并转发 {item['forwarded']} 位，占比 {item['pass_rate']}%；硬性条件缺失未转发 {item['hard_fail']} 位",
                ]
            )
    reasons_by_job = cap_reasons_by_job(reasons_by_job, jobs)
    reason_lines = format_reason_lines(reasons_by_job)
    reasons = format_reason_summary_from_breakdown(reasons_by_job)
    duplicate_total = int(funnel.get("duplicate_total") or 0)
    duplicate_global = int(funnel.get("duplicate_global") or 0)
    duplicate_same_run = int(funnel.get("duplicate_same_run") or 0)
    visible_total = int(funnel.get("visible_total") or 0)
    list_open_queue = int(funnel.get("list_open_queue") or 0)
    list_skipped = int(funnel.get("list_skipped") or 0)
    opened_online = int(funnel.get("opened_online") or 0)
    list_failed_age = int(funnel.get("list_failed_age") or 0)
    list_failed_education = int(funnel.get("list_failed_education") or 0)
    unknown_visible = int(funnel.get("unknown_visible") or 0)
    if visible_total < total:
        status_counts = conn.execute(
            """
            SELECT
              SUM(CASE WHEN status IN ('REJECT_LIST_AGE_PRECHECK', 'list_age_fail', 'list_failed_age') THEN 1 ELSE 0 END) AS age_count,
              SUM(CASE WHEN status IN ('REJECT_LIST_EDUCATION_PRECHECK', 'REJECT_LIST_EDU_PRECHECK', 'list_education_fail', 'list_failed_education') THEN 1 ELSE 0 END) AS education_count
            FROM processed_candidates
            WHERE date(processed_at) BETWEEN ? AND ?
            """,
            (start_text, end_text),
        ).fetchone()
        list_failed_age = int((status_counts or {})["age_count"] or 0)
        list_failed_education = int((status_counts or {})["education_count"] or 0)
        list_skipped = list_failed_age + list_failed_education
        duplicate_total = duplicate_global = duplicate_same_run = 0
        visible_total = total
        list_open_queue = max(total - list_skipped, 0)
        unknown_visible = 0
    deduped_list_total = max(visible_total - duplicate_total, 0)
    unknown_reason = "无" if unknown_visible == 0 else "列表缺少年龄或学历，需打开在线简历确认"
    if total:
        portrait = f"{period_word}共筛选 {total} 位候选人，需结合岗位拆解和未转发原因判断画像分布。"
        advice = "建议优先复盘未转发原因占比最高的硬性条件，必要时校准 JD、薪资范围和关键词。"
    else:
        portrait = f"{period_word}没有候选人筛选数据入库，无法形成薪资、学历、经验、技能或行业背景画像。"
        advice = "建议先确认自动化是否按计划启动、BOSS 登录态是否正常、JD 库是否完整。"
    body = "\n".join(
        [
            f"{title}：",
            "1. 运行状态与风控",
            f"- 运行时长与状态：{period_word}运行状态：{status.rstrip('。')}",
            f"- Token消耗：累计消耗 Token {token_text}",
            "",
            "2. 任务完成度与简历质量",
            "- 全局漏斗：",
            f"    - {period_word}共筛选候选人 {total} 位",
            f"    - 硬性条件通过并转发 {forwarded} 位",
            f"    - 硬性条件缺失未转发 {hard_fail} 位",
            f"    - 重复候选人 {duplicate_total} 位",
            "- 筛选过程全量统计：",
            f"    - 去除重复后进入列表预筛 {deduped_list_total} 位",
            f"    - 列表预筛通过 {list_open_queue} 位",
            f"    - 列表预筛不通过 {list_skipped} 位",
            f"      原因：年龄不符合 {list_failed_age} 位；学历不符合 {list_failed_education} 位",
            f"    - 打开在线简历 {opened_online} 位",
            f"    - 列表信息不完整 {unknown_visible} 位；问题：{unknown_reason}",
            "- 岗位拆解：",
            *job_lines,
            "- 岗位不符合原因统计（按候选人去重，记录主因）：",
            *reason_lines,
            "",
            "3. 小昭洞察与建议",
            f"- 画像总结：{portrait}",
            f"- 未转发原因分析：{reasons}",
            f"- 行动建议：{advice}",
        ]
    )
    assert_public_report_body(body)
    return {
        "report_type": report_type,
        "period_start": start_text,
        "period_end": end_text,
        "processed": total,
        "forwarded": forwarded,
        "hard_fail": hard_fail,
        "jobs": jobs,
        "online_resume_by_job": online_by_job,
        "funnel": funnel,
        "reasons_by_job": reasons_by_job,
        "run_status": status,
        "body": body,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--type", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date", help="Anchor date in YYYY-MM-DD. Daily uses previous day; weekly uses previous week.")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument("--token-total", type=int)
    parser.add_argument("--heartbeat-day", help="Automation heartbeat date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    if args.period_start and args.period_end:
        start, end = date.fromisoformat(args.period_start), date.fromisoformat(args.period_end)
    else:
        start, end = default_window(args.type, parse_day(args.date))

    with connect_readonly(Path(args.db)) as conn:
        heartbeat_day = date.fromisoformat(args.heartbeat_day) if args.heartbeat_day else None
        token_total = args.token_total if args.token_total is not None else codex_token_total_for_period(start, end)
        report = build_report(conn, args.type, start, end, token_total, heartbeat_day, args.stale_minutes)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["body"])


if __name__ == "__main__":
    main()
