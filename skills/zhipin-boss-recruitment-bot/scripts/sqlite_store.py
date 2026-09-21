#!/usr/bin/env python3
"""SQLite store for the local BOSS/Zhipin screening index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(".zhipin-copilot/recruitment.sqlite3")
DEFAULT_BACKUP_DIR = Path("data/backups/sqlite")
DEFAULT_DESKTOP_BACKUP_DIR = Path("/Users/helloworld/Desktop/小昭机器人2.0/backups/sqlite")
USER_JD_READ_MARKERS = ("USER_PROVIDED", "FEISHU_USER_PROVIDED")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA busy_timeout=10000;
        PRAGMA temp_store=MEMORY;
        PRAGMA cache_size=-20000;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY,
          job_ref TEXT UNIQUE NOT NULL,
          job_title TEXT,
          city TEXT,
          salary TEXT,
          experience TEXT,
          education TEXT,
          work_address TEXT,
          jd_text TEXT,
          jd_summary TEXT,
          page_scrolled_to_bottom INTEGER NOT NULL DEFAULT 0,
          job_description_scrolled_to_bottom INTEGER NOT NULL DEFAULT 0,
          last_jd_read_at TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS job_requirements (
          id INTEGER PRIMARY KEY,
          job_ref TEXT NOT NULL,
          requirement_type TEXT NOT NULL,
          category TEXT NOT NULL,
          label TEXT NOT NULL,
          value TEXT,
          min_value REAL,
          max_value REAL,
          evidence TEXT,
          UNIQUE(job_ref, requirement_type, category, label)
        );
        CREATE TABLE IF NOT EXISTS job_hard_gates (
          job_ref TEXT PRIMARY KEY,
          canonical_job_ref TEXT NOT NULL,
          max_age INTEGER,
          min_education TEXT,
          hard_gates_json TEXT NOT NULL,
          decision_plan_json TEXT NOT NULL DEFAULT '[]',
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_job_hard_gates_canonical ON job_hard_gates(canonical_job_ref);
        CREATE TABLE IF NOT EXISTS resumes (
          id INTEGER PRIMARY KEY,
          job_ref TEXT NOT NULL,
          candidate_ref TEXT NOT NULL,
          candidate_key TEXT UNIQUE,
          candidate_name TEXT,
          age INTEGER,
          target_role TEXT,
          city TEXT,
          salary TEXT,
          years_experience TEXT,
          is_fresh_graduate INTEGER NOT NULL DEFAULT 0,
          education_level TEXT,
          resume_text TEXT,
          resume_summary TEXT,
          read_at TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(job_ref, candidate_ref)
        );
        CREATE INDEX IF NOT EXISTS idx_resumes_job ON resumes(job_ref);
        CREATE INDEX IF NOT EXISTS idx_resumes_candidate_ref ON resumes(candidate_ref);
        CREATE TABLE IF NOT EXISTS candidate_education (
          id INTEGER PRIMARY KEY,
          candidate_key TEXT NOT NULL,
          school TEXT,
          major TEXT,
          degree TEXT,
          period TEXT,
          evidence TEXT
        );
        CREATE TABLE IF NOT EXISTS candidate_experience (
          id INTEGER PRIMARY KEY,
          candidate_key TEXT NOT NULL,
          company TEXT,
          title TEXT,
          period TEXT,
          months INTEGER,
          evidence TEXT
        );
        CREATE TABLE IF NOT EXISTS candidate_projects (
          id INTEGER PRIMARY KEY,
          candidate_key TEXT NOT NULL,
          project_name TEXT,
          role TEXT,
          period TEXT,
          evidence TEXT
        );
        CREATE TABLE IF NOT EXISTS candidate_skills (
          candidate_key TEXT NOT NULL,
          skill TEXT NOT NULL,
          evidence TEXT,
          UNIQUE(candidate_key, skill)
        );
        CREATE TABLE IF NOT EXISTS candidate_languages (
          candidate_key TEXT NOT NULL,
          language TEXT NOT NULL,
          evidence TEXT,
          UNIQUE(candidate_key, language)
        );
        CREATE TABLE IF NOT EXISTS candidate_features (
          candidate_key TEXT NOT NULL,
          feature_key TEXT NOT NULL,
          feature_value TEXT,
          evidence TEXT,
          UNIQUE(candidate_key, feature_key)
        );
        CREATE TABLE IF NOT EXISTS matches (
          id INTEGER PRIMARY KEY,
          job_ref TEXT NOT NULL,
          candidate_ref TEXT NOT NULL,
          decision_tier TEXT,
          hard_pass INTEGER NOT NULL DEFAULT 1,
          hard_fail_reasons TEXT,
          matched_evidence TEXT,
          missing_evidence TEXT,
          summary TEXT,
          recommend_reason TEXT,
          risk_reason TEXT,
          matched_at TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_matches_day ON matches(matched_at);
        CREATE INDEX IF NOT EXISTS idx_matches_day_decision ON matches(matched_at, decision_tier, hard_pass);
        CREATE INDEX IF NOT EXISTS idx_matches_job_candidate ON matches(job_ref, candidate_ref);
        CREATE TABLE IF NOT EXISTS processed_candidates (
          id INTEGER PRIMARY KEY,
          job_ref TEXT NOT NULL,
          candidate_ref TEXT NOT NULL,
          candidate_key TEXT UNIQUE,
          candidate_fingerprint TEXT,
          candidate_name TEXT,
          age INTEGER,
          education_level TEXT,
          target_role TEXT,
          city TEXT,
          salary TEXT,
          years_experience TEXT,
          status TEXT,
          note TEXT,
          processed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_processed_candidate_ref ON processed_candidates(candidate_ref);
        CREATE INDEX IF NOT EXISTS idx_processed_candidate_key ON processed_candidates(candidate_key);
        CREATE INDEX IF NOT EXISTS idx_processed_candidate_name ON processed_candidates(candidate_name);
        CREATE INDEX IF NOT EXISTS idx_processed_processed_at ON processed_candidates(processed_at);
        CREATE TABLE IF NOT EXISTS daily_processed_candidates (
          id INTEGER PRIMARY KEY,
          process_date TEXT NOT NULL,
          candidate_name TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(process_date, candidate_name)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_processed_date ON daily_processed_candidates(process_date);
        CREATE INDEX IF NOT EXISTS idx_daily_processed_date_name ON daily_processed_candidates(process_date, candidate_name);
        CREATE TABLE IF NOT EXISTS screening_run_seen_candidates (
          id INTEGER PRIMARY KEY,
          run_id TEXT NOT NULL,
          job_ref TEXT NOT NULL,
          candidate_fingerprint TEXT NOT NULL,
          candidate_name TEXT,
          age INTEGER,
          education_level TEXT,
          status TEXT NOT NULL,
          seen_at TEXT NOT NULL,
          UNIQUE(run_id, candidate_fingerprint)
        );
        CREATE INDEX IF NOT EXISTS idx_seen_run_job ON screening_run_seen_candidates(run_id, job_ref, seen_at);
        CREATE INDEX IF NOT EXISTS idx_seen_run_fingerprint ON screening_run_seen_candidates(run_id, candidate_fingerprint);
        CREATE TABLE IF NOT EXISTS forward_records (
          id INTEGER PRIMARY KEY,
          job_ref TEXT NOT NULL,
          candidate_ref TEXT NOT NULL,
          candidate_key TEXT,
          match_id INTEGER,
          recipient TEXT NOT NULL,
          note TEXT,
          status TEXT,
          forwarded_at TEXT NOT NULL,
          UNIQUE(candidate_key, recipient)
        );
        CREATE INDEX IF NOT EXISTS idx_forward_records_day_status ON forward_records(forwarded_at, status);
        CREATE TABLE IF NOT EXISTS run_events (
          id INTEGER PRIMARY KEY,
          event_type TEXT NOT NULL,
          job_ref TEXT,
          candidate_ref TEXT,
          status TEXT,
          note TEXT,
          detail_text TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_events_created_type_status ON run_events(created_at, event_type, status);
        CREATE TABLE IF NOT EXISTS reports (
          id INTEGER PRIMARY KEY,
          report_type TEXT NOT NULL,
          period_start TEXT NOT NULL,
          period_end TEXT NOT NULL,
          body TEXT NOT NULL,
          summary_text TEXT,
          sent_status TEXT,
          sent_at TEXT,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_period ON reports(report_type, period_start, period_end);
        CREATE INDEX IF NOT EXISTS idx_reports_type_created ON reports(report_type, created_at);
        CREATE TABLE IF NOT EXISTS automation_runs (
          id INTEGER PRIMARY KEY,
          flow_id TEXT NOT NULL,
          run_id TEXT UNIQUE NOT NULL,
          status TEXT NOT NULL,
          started_at TEXT NOT NULL,
          heartbeat_at TEXT NOT NULL,
          ended_at TEXT,
          note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_automation_runs_flow_status ON automation_runs(flow_id, status, heartbeat_at);
        CREATE TABLE IF NOT EXISTS xiaozhao_jd_updates (
          id INTEGER PRIMARY KEY,
          action TEXT NOT NULL,
          job_ref TEXT,
          original_text TEXT,
          optimized_summary TEXT,
          source TEXT,
          operator TEXT,
          status TEXT NOT NULL DEFAULT 'RECORDED',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS xiaozhao_feishu_feedback (
          id INTEGER PRIMARY KEY,
          original_text TEXT NOT NULL,
          optimized_summary TEXT,
          source TEXT,
          requester TEXT,
          status TEXT NOT NULL DEFAULT 'RECORDED',
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS xiaozhao_feishu_bug_tickets (
          id INTEGER PRIMARY KEY,
          original_text TEXT NOT NULL,
          optimized_summary TEXT,
          source TEXT,
          requester TEXT,
          status TEXT NOT NULL DEFAULT 'OPEN',
          closed_at TEXT,
          completed_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS xiaozhao_feishu_requirement_tickets (
          id INTEGER PRIMARY KEY,
          original_text TEXT NOT NULL,
          optimized_summary TEXT,
          source TEXT,
          requester TEXT,
          feedback_id INTEGER,
          status TEXT NOT NULL DEFAULT 'OPEN',
          acceptance_reviewer TEXT,
          acceptance_result TEXT,
          closed_at TEXT,
          completed_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_xiaozhao_bug_status ON xiaozhao_feishu_bug_tickets(status);
        CREATE INDEX IF NOT EXISTS idx_xiaozhao_xq_status ON xiaozhao_feishu_requirement_tickets(status);
        """
    )
    ensure_column(conn, "resumes", "age", "INTEGER")
    ensure_column(conn, "processed_candidates", "candidate_fingerprint", "TEXT")
    ensure_column(conn, "processed_candidates", "age", "INTEGER")
    ensure_column(conn, "processed_candidates", "education_level", "TEXT")
    ensure_column(conn, "processed_candidates", "target_role", "TEXT")
    ensure_column(conn, "processed_candidates", "city", "TEXT")
    ensure_column(conn, "processed_candidates", "salary", "TEXT")
    ensure_column(conn, "processed_candidates", "years_experience", "TEXT")
    ensure_column(conn, "job_hard_gates", "decision_plan_json", "TEXT NOT NULL DEFAULT '[]'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_candidate_fingerprint ON processed_candidates(candidate_fingerprint)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_name_age_edu ON processed_candidates(candidate_name, age, education_level)")
    ensure_column(conn, "reports", "summary_text", "TEXT")
    ensure_column(conn, "reports", "sent_status", "TEXT")
    ensure_column(conn, "reports", "sent_at", "TEXT")
    ensure_fts(conn)
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_fts(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS jd_fts USING fts5(job_ref UNINDEXED, jd_text)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS resume_fts USING fts5(candidate_key UNINDEXED, resume_text)")


def plain_result(**items: Any) -> str:
    return "\n".join(f"{key}={'' if value is None else value}" for key, value in items.items())


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return {} if row is None else dict(row)


def scalar_int(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def read_text_arg(value: str | None, file_value: str | None) -> str:
    if file_value:
        return Path(file_value).read_text(encoding="utf-8")
    return value or ""


def has_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(term.lower() in low for term in terms)


def canonical_job_name(value: str | None) -> str:
    raw = str(value or "").strip()
    text = re.sub(r"[\s|/_,，、:：;；·•\-—()（）]+", "", raw.lower())
    if "运营负责人" in text:
        return "运营负责人"
    if "海外广告优化师" in text:
        return "海外广告优化师（双休）"
    if "ui设计师" in text or "ui设计" in text:
        return "Ui设计师"
    normalized = raw.replace("（", "(").replace("）", ")")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"岗位$", "", normalized)
    return normalized


def parse_age(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d{2})\s*岁", text)
    if not match:
        return None
    age = int(match.group(1))
    return age if 16 <= age <= 80 else None


def candidate_identity_key(candidate_ref: str | None, candidate_name: str | None = None) -> str:
    raw = candidate_ref or candidate_name or "unknown_candidate"
    text = str(raw).lower()
    text = re.sub(r"[\s|/_,，、:：;；·•\-—]+", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text or str(candidate_name or raw)


def candidate_fingerprint(candidate_name: str | None, age: int | None = None, education_level: str | None = None) -> str:
    normalized_name = candidate_identity_key(candidate_name)
    normalized_education = education_rank(education_level or "") or ""
    age_text = str(age or "")
    parts = [normalized_name, age_text, normalized_education]
    return candidate_identity_key("|".join(parts))


def batch_lookup_key(item: dict[str, Any]) -> str:
    return candidate_fingerprint(item.get("candidate_name"), item.get("age"), item.get("education_level"))


def infer_candidate_ref(candidate_name: str | None, target_role: str | None, city: str | None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return " | ".join(part for part in [candidate_name, target_role, city] if part) or "unknown_candidate"


def candidate_name_from_ref(candidate_ref: str | None) -> str:
    text = str(candidate_ref or "").strip()
    if not text:
        return ""
    parts = re.split(r"\s*[|/，,、]\s*", text)
    return parts[0].strip() if parts else text


def education_rank(text: str) -> str | None:
    if has_any(text, ["初中", "初中及以下"]):
        return "初中及以下"
    if has_any(text, ["博士"]):
        return "博士"
    if has_any(text, ["硕士", "研究生", "MBA", "mba"]):
        return "硕士"
    if has_any(text, ["本科", "学士"]):
        return "本科"
    if has_any(text, ["大专", "专科"]):
        return "大专"
    if has_any(text, ["高中", "中专", "技校", "职高"]):
        return "高中/中专"
    return text or None


EDUCATION_ORDER = {
    "初中及以下": 0,
    "高中/中专": 1,
    "大专": 2,
    "本科": 3,
    "硕士": 4,
    "博士": 5,
}


def education_value(text: str | None) -> int | None:
    rank = education_rank(text or "")
    if not rank:
        return None
    return EDUCATION_ORDER.get(rank)


def is_fresh_graduate(years_experience: str | None, resume_text: str | None) -> int:
    return 1 if has_any(" ".join([years_experience or "", resume_text or ""]), ["应届", "在校", "实习", "毕业生", "校招"]) else 0


def upsert_candidate_feature(conn: sqlite3.Connection, candidate_key: str, feature_key: str, feature_value: Any, evidence: str = "") -> None:
    conn.execute(
        """
        INSERT INTO candidate_features (candidate_key, feature_key, feature_value, evidence)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(candidate_key, feature_key) DO UPDATE SET
          feature_value=excluded.feature_value,
          evidence=excluded.evidence
        """,
        (candidate_key, feature_key, str(feature_value), evidence),
    )


def add_job_requirement(conn: sqlite3.Connection, job_ref: str, requirement_type: str, category: str, label: str, value: str = "", min_value: float | None = None, max_value: float | None = None, evidence: str = "") -> None:
    conn.execute(
        """
        INSERT INTO job_requirements (
          job_ref, requirement_type, category, label, value, min_value, max_value, evidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_ref, requirement_type, category, label) DO UPDATE SET
          value=excluded.value,
          min_value=excluded.min_value,
          max_value=excluded.max_value,
          evidence=excluded.evidence
        """,
        (job_ref, requirement_type, category, label, value, min_value, max_value, evidence),
    )


def manual_requirement_lines(job_ref: str, jd_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in (jd_text or "").splitlines():
        line = re.sub(r"^\s*[-*•]?\s*\d+[.、)]\s*", "", raw_line).strip()
        line = re.sub(r"^硬性要求[:：]?\s*", "", line).strip()
        if not line or line == "硬性要求":
            continue
        if line.startswith(job_ref) and "硬性要求" in line and len(line) <= len(job_ref) + 8:
            continue
        if line not in lines:
            lines.append(line)
    return lines


def add_manual_jd_requirements(conn: sqlite3.Connection, job_ref: str, jd_text: str) -> None:
    for line in manual_requirement_lines(job_ref, jd_text):
        age_match = re.search(r"(\d+)\s*岁\s*(?:以下|以内|内)", line)
        if age_match:
            age = float(age_match.group(1))
            add_job_requirement(conn, job_ref, "hard", "age", "max_age", f"{int(age)}岁以下", None, age, line)
        if "本科" in line:
            add_job_requirement(conn, job_ref, "hard", "education", "bachelor_or_above", "本科", evidence=line)
        elif "大专" in line or "专科" in line:
            add_job_requirement(conn, job_ref, "hard", "education", "college_or_above", "大专", evidence=line)
        years_match = re.search(r"(\d+)\s*年(?:以上|及以上|\+)", line)
        if years_match:
            add_job_requirement(conn, job_ref, "hard", "experience", "min_years", line, float(years_match.group(1)), None, line)
        label = f"manual_{hashlib.sha1(line.encode('utf-8')).hexdigest()[:12]}"
        add_job_requirement(conn, job_ref, "hard", "manual", label, line, evidence=line)


def build_job_hard_gates(conn: sqlite3.Connection, job_ref: str) -> dict[str, Any]:
    canonical = canonical_job_name(job_ref)
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT requirement_type, category, label, value, min_value, max_value
            FROM job_requirements
            WHERE job_ref = ?
              AND requirement_type = 'hard'
            ORDER BY category, label
            """,
            (job_ref,),
        )
    ]
    max_age: int | None = None
    min_education: str | None = None
    for row in rows:
        if row["category"] == "age" and row["label"] == "max_age" and row["max_value"] is not None:
            max_age = int(row["max_value"])
        if row["category"] == "education":
            label = str(row["label"] or "")
            if label == "bachelor_or_above":
                min_education = "本科"
            elif label == "college_or_above":
                min_education = "大专"
    return {
        "job_ref": job_ref,
        "canonical_job_ref": canonical,
        "max_age": max_age,
        "min_education": min_education,
        "hard_gates": rows,
        "decision_plan": build_decision_plan(canonical, rows),
    }


def build_decision_plan(canonical_job_ref: str, hard_gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = {str(row.get("label") or "") for row in hard_gates}
    plan: list[dict[str, Any]] = [
        {
            "step": "age",
            "action": "fail_fast_if_visible_age_exceeds_max_age",
            "source": "list_or_resume",
        },
        {
            "step": "education",
            "action": "fail_fast_if_visible_education_below_minimum",
            "source": "list_or_resume",
        },
    ]
    if canonical_job_ref == "运营负责人":
        plan.extend(
            [
                {
                    "step": "region",
                    "action": "verify_overseas_middle_east_responsibility_before_deep_analysis",
                    "required_labels": ["middle_east_region_1y", "overseas_middle_east_ops_2y"],
                },
                {
                    "step": "business_type",
                    "action": "verify_voice_chat_or_voice_room_business",
                    "required_labels": ["voice_chat_business"],
                },
                {
                    "step": "years",
                    "action": "verify_middle_east_ops_years_after_region_and_business_match",
                    "required_labels": ["overseas_middle_east_ops_2y"],
                },
            ]
        )
    elif canonical_job_ref == "海外广告优化师（双休）":
        plan.extend(
            [
                {
                    "step": "region",
                    "action": "verify_overseas_region_experience_before_product_deep_analysis",
                    "required_labels": ["overseas_region_any"],
                },
                {
                    "step": "product_type",
                    "action": "verify_original_social_ads_product_1y_or_overseas_plus_any_target_keyword",
                    "required_labels_any": ["social_ads_product_1y", "overseas_social_ads_keyword"],
                },
                {
                    "step": "delivery_years",
                    "action": "verify_one_year_only_when_using_original_social_ads_product_gate",
                    "required_labels": ["social_ads_product_1y"],
                },
            ]
        )
    elif canonical_job_ref == "Ui设计师":
        plan.extend(
            [
                {
                    "step": "product_type",
                    "action": "verify_live_voice_room_or_ai_social_app_ui_experience",
                    "required_labels": ["social_product_ui_1y"],
                },
                {
                    "step": "design_years",
                    "action": "verify_one_year_social_app_ui_design_experience",
                    "required_labels": ["social_product_ui_1y"],
                },
            ]
        )
    else:
        for label in sorted(labels - {"max_age", "college_or_above", "bachelor_or_above"}):
            plan.append(
                {
                    "step": label,
                    "action": "verify_hard_requirement_only_if_previous_steps_do_not_fail",
                    "required_labels": [label],
                }
            )
    plan.append(
        {
            "step": "stop_rule",
            "action": "once_any_hard_requirement_clearly_fails_stop_deep_reasoning_and_do_not_forward",
        }
    )
    return plan


def refresh_job_hard_gates(conn: sqlite3.Connection, job_ref: str) -> dict[str, Any]:
    gates = build_job_hard_gates(conn, job_ref)
    updated_at = now_iso()
    conn.execute(
        """
        INSERT INTO job_hard_gates (
          job_ref, canonical_job_ref, max_age, min_education, hard_gates_json, decision_plan_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_ref) DO UPDATE SET
          canonical_job_ref=excluded.canonical_job_ref,
          max_age=excluded.max_age,
          min_education=excluded.min_education,
          hard_gates_json=excluded.hard_gates_json,
          decision_plan_json=excluded.decision_plan_json,
          updated_at=excluded.updated_at
        """,
        (
            gates["job_ref"],
            gates["canonical_job_ref"],
            gates["max_age"],
            gates["min_education"],
            json.dumps(gates["hard_gates"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(gates["decision_plan"], ensure_ascii=False, separators=(",", ":")),
            updated_at,
        ),
    )
    return {
        "job_ref": gates["job_ref"],
        "canonical_job_ref": gates["canonical_job_ref"],
        "max_age": "" if gates["max_age"] is None else gates["max_age"],
        "min_education": gates["min_education"] or "",
        "hard_gate_count": len(gates["hard_gates"]),
        "decision_step_count": len(gates["decision_plan"]),
        "updated_at": updated_at,
    }


def seed_jd_hard_gates(conn: sqlite3.Connection) -> dict[str, Any]:
    if scalar_int(conn, "SELECT COUNT(*) FROM jobs") == 0:
        seed_user_provided_jds(conn)
    rows = conn.execute(
        """
        SELECT job_ref
        FROM jobs
        ORDER BY CASE WHEN last_jd_read_at = 'USER_PROVIDED' THEN 0 ELSE 1 END, job_ref
        """
    ).fetchall()
    refreshed = [refresh_job_hard_gates(conn, row["job_ref"]) for row in rows]
    conn.commit()
    return {
        "status": "ok",
        "refreshed_count": len(refreshed),
        "refreshed_jobs": "、".join(item["job_ref"] for item in refreshed),
    }


def get_jd_hard_gates(conn: sqlite3.Connection, job_ref: str) -> dict[str, Any]:
    canonical = canonical_job_name(job_ref)
    row = conn.execute(
        """
        SELECT *
        FROM job_hard_gates
        WHERE job_ref = ? OR canonical_job_ref = ?
        ORDER BY CASE WHEN job_ref = ? THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        (job_ref, canonical, job_ref),
    ).fetchone()
    if row is None:
        latest = get_latest_jd(conn, job_ref)
        refresh_job_hard_gates(conn, latest["job_ref"])
        conn.commit()
        row = conn.execute("SELECT * FROM job_hard_gates WHERE job_ref = ?", (latest["job_ref"],)).fetchone()
    if row is None:
        raise SystemExit(f"No hard gates found for job_ref={job_ref}")
    data = dict(row)
    data["hard_gates"] = json.loads(str(data.pop("hard_gates_json") or "[]"))
    data["decision_plan"] = json.loads(str(data.pop("decision_plan_json", "[]") or "[]"))
    data["requested_job_ref"] = job_ref
    return data


def derive_job_requirements(conn: sqlite3.Connection, job_ref: str, job_title: str | None, experience: str | None, education: str | None, jd_text: str) -> None:
    conn.execute("DELETE FROM job_requirements WHERE job_ref = ?", (job_ref,))
    canonical = canonical_job_name(" ".join([job_ref, job_title or "", jd_text or ""]))
    if canonical == "运营负责人":
        add_job_requirement(conn, job_ref, "hard", "domain", "middle_east_region_1y", "负责过海外中东地区，1年以上", 1, None, jd_text)
        add_job_requirement(conn, job_ref, "hard", "domain", "voice_chat_business", "负责过语聊或语音房项目", evidence=jd_text)
        add_job_requirement(conn, job_ref, "hard", "domain", "overseas_middle_east_ops_2y", "2年以上海外中东地区运营经验", 2, None, jd_text)
        add_job_requirement(conn, job_ref, "hard", "education", "college_or_above", "大专以上", evidence=jd_text)
        add_job_requirement(conn, job_ref, "hard", "age", "max_age", "35岁以下", None, 35, jd_text)
        return
    if canonical == "海外广告优化师（双休）":
        add_job_requirement(conn, job_ref, "hard", "domain", "overseas_region_any", "负责海外地区", evidence=jd_text)
        add_job_requirement(conn, job_ref, "hard", "domain", "social_ads_product_1y", "1年以上1v1社交/直播社交/语聊/语音房/AI社交投放经验", 1, None, jd_text)
        add_job_requirement(conn, job_ref, "hard", "domain", "overseas_social_ads_keyword", "a=海外；b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词；简历全文满足a+b或ab都符合目标产品/业务要求，a+b不要求相邻，ab如“海外社交”等连写", evidence=jd_text)
        add_job_requirement(conn, job_ref, "hard", "education", "college_or_above", "大专以上", evidence=jd_text)
        add_job_requirement(conn, job_ref, "hard", "age", "max_age", "35岁以下", None, 35, jd_text)
        return
    if canonical == "Ui设计师":
        add_job_requirement(conn, job_ref, "hard", "domain", "social_product_ui_1y", "1年以上直播社交/语聊/语音房/AI社交App UI设计经验", 1, None, jd_text)
        add_job_requirement(conn, job_ref, "hard", "education", "college_or_above", "大专以上", evidence=jd_text)
        add_job_requirement(conn, job_ref, "hard", "age", "max_age", "32岁以下", None, 32, jd_text)
        return
    text = " ".join([job_ref, job_title or "", experience or "", education or "", jd_text or ""])
    match = re.search(r"(\d+)\s*[-~到]\s*(\d+)\s*年", text)
    if match:
        add_job_requirement(conn, job_ref, "hard", "experience", "years_range", experience or "", float(match.group(1)), float(match.group(2)), experience or text)
    else:
        match = re.search(r"(\d+)\s*年(?:以上|及以上|\+)", text)
        if match:
            add_job_requirement(conn, job_ref, "hard", "experience", "min_years", experience or "", float(match.group(1)), None, experience or text)
    if has_any(text, ["应届", "在校", "实习生"]):
        add_job_requirement(conn, job_ref, "hard", "experience", "entry_level", experience or "", 0, 2, experience or text)
    if has_any(text, ["本科"]):
        add_job_requirement(conn, job_ref, "hard", "education", "bachelor_or_above", "本科", evidence=text)
    elif has_any(text, ["大专", "专科"]):
        add_job_requirement(conn, job_ref, "hard", "education", "college_or_above", "大专", evidence=text)
    if "英语" in text and not re.search(r"英语.{0,8}(优先|加分)|优先.{0,8}英语", text):
        add_job_requirement(conn, job_ref, "hard", "language", "english", "英语", evidence=text)
    elif "英语" in text:
        add_job_requirement(conn, job_ref, "bonus", "language", "english", "英语", evidence=text)
    if "阿拉伯语" in text or "阿语" in text:
        if re.search(r"(阿拉伯语|阿语).{0,8}(优先|加分)|优先.{0,8}(阿拉伯语|阿语)", text):
            add_job_requirement(conn, job_ref, "bonus", "language", "arabic", "阿拉伯语", evidence=text)
        else:
            add_job_requirement(conn, job_ref, "hard", "language", "arabic", "阿拉伯语", evidence=text)
    if "ui设计师" in text.lower() or "ui 设计师" in text.lower():
        add_job_requirement(conn, job_ref, "hard", "domain", "social_product_design", "社交软件/社交产品设计经历", evidence=text)
    add_manual_jd_requirements(conn, job_ref, jd_text)

def upsert_jd_record(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    jd_text = read_text_arg(args.jd_text, args.jd_text_file)
    current = now_iso()
    read_at = args.last_jd_read_at or current
    conn.execute(
        """
        INSERT INTO jobs (
          job_ref, job_title, city, salary, experience, education, work_address,
          jd_text, jd_summary, page_scrolled_to_bottom,
          job_description_scrolled_to_bottom, last_jd_read_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_ref) DO UPDATE SET
          job_title=excluded.job_title,
          city=excluded.city,
          salary=excluded.salary,
          experience=excluded.experience,
          education=excluded.education,
          work_address=excluded.work_address,
          jd_text=excluded.jd_text,
          jd_summary=excluded.jd_summary,
          page_scrolled_to_bottom=excluded.page_scrolled_to_bottom,
          job_description_scrolled_to_bottom=excluded.job_description_scrolled_to_bottom,
          last_jd_read_at=excluded.last_jd_read_at,
          updated_at=excluded.updated_at
        """,
        (
            args.job_ref,
            args.job_title,
            args.city,
            args.salary,
            args.experience,
            args.education,
            args.work_address,
            jd_text,
            args.jd_summary,
            1 if args.page_scrolled else 0,
            1 if args.description_scrolled else 0,
            read_at,
            current,
            current,
        ),
    )
    conn.execute("DELETE FROM jd_fts WHERE job_ref = ?", (args.job_ref,))
    conn.execute("INSERT INTO jd_fts(job_ref, jd_text) VALUES (?, ?)", (args.job_ref, jd_text))
    derive_job_requirements(conn, args.job_ref, args.job_title, args.experience, args.education, jd_text)
    refresh_job_hard_gates(conn, args.job_ref)
    conn.commit()
    return dict(conn.execute("SELECT id, job_ref, last_jd_read_at FROM jobs WHERE job_ref = ?", (args.job_ref,)).fetchone())


def prune_jds_to_current_open_jobs(conn: sqlite3.Connection, open_job_refs: list[str], today: str | None = None) -> dict[str, Any]:
    refs = [str(ref).strip() for ref in open_job_refs if str(ref).strip()]
    if not refs:
        raise SystemExit("At least one --open-job-ref is required before pruning JD rows.")
    day = today or now_iso()[:10]
    placeholders = ",".join("?" for _ in refs)
    stale_rows = conn.execute(
        f"""
        SELECT id, job_ref, last_jd_read_at
        FROM jobs
        WHERE job_ref NOT IN ({placeholders})
           OR substr(last_jd_read_at, 1, 10) != ?
        ORDER BY job_ref
        """,
        (*refs, day),
    ).fetchall()
    conn.execute(
        f"""
        DELETE FROM jobs
        WHERE job_ref NOT IN ({placeholders})
           OR substr(last_jd_read_at, 1, 10) != ?
        """,
        (*refs, day),
    )
    conn.execute(
        f"""
        DELETE FROM job_hard_gates
        WHERE job_ref NOT IN ({placeholders})
        """,
        tuple(refs),
    )
    conn.commit()
    return {"deleted_count": len(stale_rows), "kept_count": len(refs), "today": day}


USER_PROVIDED_JDS: tuple[dict[str, str], ...] = (
    {
        "job_ref": "运营负责人",
        "job_title": "运营负责人",
        "experience": "2年以上海外中东地区运营经验",
        "education": "大专以上",
        "jd_text": "运营负责人 硬性要求：1、负责过的区域：海外中东地区（1年以上）。2、负责过的业务：语聊或者语音房项目。3、经验：2年以上海外中东地区运营经验。4、学历：大专以上。5、年龄：35岁以下。",
        "jd_summary": "用户提供JD：海外中东地区1年以上、语聊/语音房、2年以上海外中东运营、大专以上、35岁以下。",
    },
    {
        "job_ref": "海外广告优化师（双休）",
        "job_title": "海外广告优化师（双休）",
        "experience": "1年以上相关海外社交产品投放经验；或简历全文满足a+b/ab：a=海外，b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词",
        "education": "大专以上",
        "jd_text": "海外广告优化师（双休） 硬性要求：1、负责区域：海外地区都可以。2、原有要求保留：有1年以上1v1社交app/直播社交app/语聊app/语音房app/AI社交app投放经验，满足其一即可。3、新增符合条件：a=海外；b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词。简历全文满足a+b（分别出现海外和b任一关键词，不要求相邻）或ab（如“海外社交”等连写，同时包含海外和b任一关键词）都符合目标产品/业务要求。4、学历：大专以上。5、年龄：35岁以下。",
        "jd_summary": "用户提供JD：海外地区；保留1年以上1v1社交/直播社交/语聊/语音房/AI社交投放经验；新增简历全文满足a+b或ab也符合，a=海外，b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词；大专以上；35岁以下。",
    },
    {
        "job_ref": "高级海外广告优化师",
        "job_title": "高级海外广告优化师",
        "experience": "1年以上相关海外社交产品投放经验；或简历全文满足a+b/ab：a=海外，b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词",
        "education": "大专以上",
        "jd_text": "高级海外广告优化师 硬性要求：1、负责区域：海外地区都可以。2、原有要求保留：有1年以上1v1社交app/直播社交app/语聊app/语音房app/AI社交app投放经验，满足其一即可。3、新增符合条件：a=海外；b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词。简历全文满足a+b（分别出现海外和b任一关键词，不要求相邻）或ab（如“海外社交”等连写，同时包含海外和b任一关键词）都符合目标产品/业务要求。4、学历：大专以上。5、年龄：35岁以下。",
        "jd_summary": "用户提供JD：海外地区；保留1年以上1v1社交/直播社交/语聊/语音房/AI社交投放经验；新增简历全文满足a+b或ab也符合，a=海外，b=1v1/社交/语音/语聊/直播社交/AI社交任一关键词；大专以上；35岁以下。",
    },
    {
        "job_ref": "Ui设计师",
        "job_title": "Ui设计师",
        "experience": "1年以上社交App UI设计经验",
        "education": "大专以上",
        "jd_text": "Ui设计师 硬性要求：1、负责过的产品：直播社交app/语聊app/语音房app/ai社交app（满足其一就可以）。2、经验：1年以上社交app UI设计经验。3、学历：大专以上。4、年龄：32岁以下。",
        "jd_summary": "用户提供JD：直播社交/语聊/语音房/AI社交App，1年以上社交App UI设计经验，大专以上，32岁以下。",
    },
)


def seed_user_provided_jds(conn: sqlite3.Connection) -> dict[str, Any]:
    stale_job_refs = [
        row["job_ref"]
        for row in conn.execute(
            f"SELECT job_ref FROM jobs WHERE last_jd_read_at NOT IN ({','.join('?' for _ in USER_JD_READ_MARKERS)})",
            USER_JD_READ_MARKERS,
        ).fetchall()
    ]
    for stale_ref in stale_job_refs:
        conn.execute("DELETE FROM job_requirements WHERE job_ref = ?", (stale_ref,))
        conn.execute("DELETE FROM job_hard_gates WHERE job_ref = ?", (stale_ref,))
        conn.execute("DELETE FROM jd_fts WHERE job_ref = ?", (stale_ref,))
    conn.execute(
        f"DELETE FROM jobs WHERE last_jd_read_at NOT IN ({','.join('?' for _ in USER_JD_READ_MARKERS)})",
        USER_JD_READ_MARKERS,
    )
    seeded: list[str] = []
    for item in USER_PROVIDED_JDS:
        existing = conn.execute("SELECT last_jd_read_at FROM jobs WHERE job_ref = ?", (item["job_ref"],)).fetchone()
        if existing is not None and existing["last_jd_read_at"] == "FEISHU_USER_PROVIDED":
            seeded.append(f"{item['job_ref']}(kept_feishu)")
            continue
        args = argparse.Namespace(
            job_ref=item["job_ref"],
            job_title=item["job_title"],
            city=None,
            salary=None,
            experience=item["experience"],
            education=item["education"],
            work_address=None,
            jd_text=item["jd_text"],
            jd_text_file=None,
            jd_summary=item["jd_summary"],
            page_scrolled=False,
            description_scrolled=False,
            last_jd_read_at="USER_PROVIDED",
        )
        upsert_jd_record(conn, args)
        seeded.append(item["job_ref"])
    return {"seeded_count": len(seeded), "seeded_jobs": "、".join(seeded), "deleted_old_jds": len(stale_job_refs)}


def upsert_resume_record(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    resume_text = read_text_arg(args.resume_text, args.resume_text_file)
    minimal_args = argparse.Namespace(
        job_ref=args.job_ref,
        candidate_ref=args.candidate_name or args.candidate_ref,
        candidate_name=args.candidate_name,
        age=args.age if getattr(args, "age", None) is not None else parse_age(resume_text),
        target_role=getattr(args, "target_role", None),
        city=getattr(args, "city", None),
        salary=getattr(args, "salary", None),
        years_experience=getattr(args, "years_experience", None),
        education_level=args.education_level or education_rank(resume_text),
        status=None,
        note=None,
        read_at=args.read_at,
    )
    return upsert_candidate_minimal(conn, minimal_args)


def upsert_candidate_minimal(conn: sqlite3.Connection, args: argparse.Namespace, commit: bool = True) -> dict[str, Any]:
    candidate_ref = args.candidate_name or args.candidate_ref or "unknown_candidate"
    education_level = education_rank(args.education_level or "")
    key_parts = [args.candidate_name or candidate_ref, str(args.age or ""), education_level or ""]
    candidate_key = candidate_identity_key("|".join(key_parts), args.candidate_name)
    current = now_iso()
    read_at = args.read_at or current
    conn.execute(
        """
        INSERT INTO resumes (
          job_ref, candidate_ref, candidate_key, candidate_name, age, target_role,
          city, salary, years_experience, is_fresh_graduate, education_level,
          resume_text, resume_summary, read_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, '', '', ?, ?, ?)
        ON CONFLICT(candidate_key) DO UPDATE SET
          job_ref=excluded.job_ref,
          candidate_ref=excluded.candidate_ref,
          candidate_name=excluded.candidate_name,
          age=excluded.age,
          target_role=excluded.target_role,
          city=excluded.city,
          salary=excluded.salary,
          years_experience=excluded.years_experience,
          education_level=excluded.education_level,
          read_at=excluded.read_at,
          updated_at=excluded.updated_at
        """,
        (
            args.job_ref,
            candidate_ref,
            candidate_key,
            args.candidate_name,
            args.age,
            args.target_role,
            args.city,
            args.salary,
            args.years_experience,
            education_level,
            read_at,
            current,
            current,
        ),
    )
    conn.execute("DELETE FROM resume_fts WHERE candidate_key = ?", (candidate_key,))
    conn.execute("DELETE FROM candidate_features WHERE candidate_key = ?", (candidate_key,))
    conn.execute("DELETE FROM candidate_skills WHERE candidate_key = ?", (candidate_key,))
    conn.execute("DELETE FROM candidate_languages WHERE candidate_key = ?", (candidate_key,))
    if args.status:
        mark_processed(
            conn,
            args.job_ref,
            candidate_ref,
            args.candidate_name,
            args.status,
            args.note,
            age=args.age,
            education_level=education_level,
            target_role=args.target_role,
            city=args.city,
            salary=args.salary,
            years_experience=args.years_experience,
            commit=False,
        )
    if commit:
        conn.commit()
    return dict(conn.execute("SELECT id, job_ref, candidate_ref, candidate_key, candidate_name, age, education_level, read_at FROM resumes WHERE candidate_key = ?", (candidate_key,)).fetchone())


def insert_match_record(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    created_at = now_iso()
    matched_at = args.matched_at or created_at
    def arg_value(name: str, default: Any = None) -> Any:
        return getattr(args, name, default)

    column_values: list[tuple[str, Any]] = [
        ("job_ref", args.job_ref),
        ("candidate_ref", args.candidate_ref),
        ("decision_tier", args.decision_tier),
        ("hard_pass", 1 if arg_value("hard_pass", True) else 0),
        ("hard_fail_reasons", arg_value("hard_fail_reasons") or ""),
        ("matched_evidence", arg_value("matched_evidence") or ""),
        ("missing_evidence", arg_value("missing_evidence") or ""),
        ("summary", arg_value("summary") or ""),
        ("recommend_reason", arg_value("recommend_reason") or ""),
        ("risk_reason", arg_value("risk_reason") or ""),
        ("matched_at", matched_at),
        ("created_at", created_at),
    ]
    table_cols = table_columns(conn, "matches")
    filtered = [(column, value) for column, value in column_values if column in table_cols]
    cur = conn.execute(
        f"INSERT INTO matches ({', '.join(column for column, _ in filtered)}) VALUES ({', '.join('?' for _ in filtered)})",
        tuple(value for _, value in filtered),
    )
    conn.commit()
    return dict(conn.execute("SELECT id, job_ref, candidate_ref, decision_tier, hard_pass FROM matches WHERE id = ?", (cur.lastrowid,)).fetchone())


def mark_processed(
    conn: sqlite3.Connection,
    job_ref: str,
    candidate_ref: str,
    candidate_name: str | None,
    status: str,
    note: str | None = None,
    age: int | None = None,
    education_level: str | None = None,
    target_role: str | None = None,
    city: str | None = None,
    salary: str | None = None,
    years_experience: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    processed_at = now_iso()
    stored_candidate_ref = candidate_name or candidate_ref or "unknown_candidate"
    normalized_education = education_rank(education_level or "") or education_level
    key_parts = [candidate_name or stored_candidate_ref, str(age or ""), normalized_education or ""]
    candidate_key = candidate_identity_key("|".join(key_parts), candidate_name)
    fingerprint = candidate_fingerprint(candidate_name or stored_candidate_ref, age, normalized_education)
    table_cols = table_columns(conn, "processed_candidates")
    column_values = [
        ("job_ref", job_ref),
        ("candidate_ref", stored_candidate_ref),
        ("candidate_key", candidate_key),
        ("candidate_fingerprint", fingerprint),
        ("candidate_name", candidate_name),
        ("age", age),
        ("education_level", normalized_education),
        ("target_role", target_role),
        ("city", city),
        ("salary", salary),
        ("years_experience", years_experience),
        ("status", status),
        ("note", note),
        ("processed_at", processed_at),
    ]
    filtered = [(column, value) for column, value in column_values if column in table_cols]
    update_columns = [column for column, _ in filtered if column not in {"candidate_key"}]
    conn.execute(
        f"""
        INSERT INTO processed_candidates ({', '.join(column for column, _ in filtered)})
        VALUES ({', '.join('?' for _ in filtered)})
        ON CONFLICT(candidate_key) DO UPDATE SET
          {', '.join(f'{column}=excluded.{column}' for column in update_columns)}
        """,
        tuple(value for _, value in filtered),
    )
    daily_candidate_name = candidate_name or stored_candidate_ref
    if daily_candidate_name:
        conn.execute(
            """
            INSERT INTO daily_processed_candidates (process_date, candidate_name, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(process_date, candidate_name) DO NOTHING
            """,
            (processed_at[:10], daily_candidate_name, processed_at),
        )
    if commit:
        conn.commit()
    return dict(conn.execute("SELECT id, job_ref, candidate_ref, candidate_key, candidate_name, age, education_level, target_role, city, salary, years_experience, status, processed_at FROM processed_candidates WHERE candidate_key = ?", (candidate_key,)).fetchone())


def record_forward(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    forwarded_at = args.forwarded_at or now_iso()
    recipient = args.recipient or "HR"
    candidate_ref = args.candidate_ref or args.candidate_name or "unknown_candidate"
    candidate_name = args.candidate_name or candidate_name_from_ref(candidate_ref) or candidate_ref
    normalized_education = education_rank(args.education_level or "") or args.education_level
    candidate_key = args.candidate_key or candidate_identity_key("|".join([candidate_name, str(args.age or ""), normalized_education or ""]), candidate_name)
    note = args.note or ""
    status = args.status or "SUCCESS"
    conn.execute(
        """
        INSERT INTO forward_records (
          job_ref, candidate_ref, candidate_key, match_id, recipient, note, status, forwarded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(candidate_key, recipient) DO UPDATE SET
          job_ref=excluded.job_ref,
          candidate_ref=excluded.candidate_ref,
          match_id=excluded.match_id,
          note=excluded.note,
          status=excluded.status,
          forwarded_at=excluded.forwarded_at
        """,
        (args.job_ref, candidate_ref, candidate_key, args.match_id, recipient, note, status, forwarded_at),
    )
    conn.execute(
        """
        INSERT INTO run_events (event_type, job_ref, candidate_ref, status, note, detail_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "boss_forward_success",
            args.job_ref,
            candidate_ref,
            "success" if str(status).lower() == "success" else status,
            note,
            args.detail_text or "",
            forwarded_at,
        ),
    )
    if args.mark_processed:
        mark_processed(
            conn,
            args.job_ref,
            candidate_ref,
            candidate_name,
            "forwarded",
            note,
            age=args.age,
            education_level=normalized_education,
            target_role=getattr(args, "target_role", None),
            city=getattr(args, "city", None),
            salary=getattr(args, "salary", None),
            years_experience=getattr(args, "years_experience", None),
            commit=False,
        )
    conn.commit()
    return {
        "job_ref": args.job_ref,
        "candidate_ref": candidate_ref,
        "candidate_key": candidate_key,
        "recipient": recipient,
        "status": status,
        "note": note,
        "forwarded_at": forwarded_at,
    }


def get_latest_jd(conn: sqlite3.Connection, job_ref: str) -> dict[str, Any]:
    canonical = canonical_job_name(job_ref)
    user_job_refs = {item["job_ref"] for item in USER_PROVIDED_JDS}
    row = None
    if canonical in user_job_refs:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE (job_ref = ? OR job_title = ?)
              AND last_jd_read_at IN ('USER_PROVIDED', 'FEISHU_USER_PROVIDED')
            ORDER BY CASE WHEN last_jd_read_at = 'FEISHU_USER_PROVIDED' THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (canonical, canonical),
        ).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM jobs WHERE job_ref = ?", (job_ref,)).fetchone()
    if row is None:
        row = conn.execute(
            """
            SELECT * FROM jobs
            WHERE job_ref = ? OR job_title = ?
            ORDER BY CASE
              WHEN last_jd_read_at = 'FEISHU_USER_PROVIDED' THEN 0
              WHEN last_jd_read_at = 'USER_PROVIDED' THEN 1
              ELSE 2
            END, updated_at DESC
            LIMIT 1
            """,
            (canonical, canonical),
        ).fetchone()
    if row is None:
        candidates = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        for candidate in candidates:
            if canonical_job_name(" ".join([candidate["job_ref"] or "", candidate["job_title"] or ""])) == canonical:
                row = candidate
                break
    if row is None:
        raise SystemExit(f"No JD found in SQLite for job_ref={job_ref}")
    data = dict(row)
    data["requirements"] = [
        dict(req)
        for req in conn.execute(
            "SELECT * FROM job_requirements WHERE job_ref = ? ORDER BY requirement_type, category, label",
            (data["job_ref"],),
        )
    ]
    return data


def hard_age_max(conn: sqlite3.Connection, job_ref: str) -> int | None:
    gate = conn.execute(
        """
        SELECT max_age
        FROM job_hard_gates
        WHERE job_ref = ? OR canonical_job_ref = ?
        ORDER BY CASE WHEN job_ref = ? THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        (job_ref, canonical_job_name(job_ref), job_ref),
    ).fetchone()
    if gate is not None and gate["max_age"] is not None:
        return int(gate["max_age"])
    canonical = canonical_job_name(job_ref)
    refs = [job_ref]
    if canonical != job_ref:
        refs.append(canonical)
    placeholders = ",".join("?" for _ in refs)
    row = conn.execute(
        f"""
        SELECT max_value FROM job_requirements
        WHERE job_ref IN ({placeholders})
          AND requirement_type = 'hard'
          AND category = 'age'
          AND label = 'max_age'
        ORDER BY CASE WHEN job_ref = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (*refs, canonical),
    ).fetchone()
    if row is None or row["max_value"] is None:
        return None
    return int(row["max_value"])


def hard_education_min(conn: sqlite3.Connection, job_ref: str) -> str | None:
    gate = conn.execute(
        """
        SELECT min_education
        FROM job_hard_gates
        WHERE job_ref = ? OR canonical_job_ref = ?
        ORDER BY CASE WHEN job_ref = ? THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        (job_ref, canonical_job_name(job_ref), job_ref),
    ).fetchone()
    if gate is not None and gate["min_education"]:
        return str(gate["min_education"])
    canonical = canonical_job_name(job_ref)
    refs = [job_ref]
    if canonical != job_ref:
        refs.append(canonical)
    placeholders = ",".join("?" for _ in refs)
    row = conn.execute(
        f"""
        SELECT label FROM job_requirements
        WHERE job_ref IN ({placeholders})
          AND requirement_type = 'hard'
          AND category = 'education'
        ORDER BY CASE WHEN label = 'college_or_above' THEN 0
                      WHEN label = 'bachelor_or_above' THEN 1
                      ELSE 2 END
        LIMIT 1
        """,
        (*refs,),
    ).fetchone()
    if row is None:
        return None
    label = str(row["label"] or "")
    if label == "bachelor_or_above":
        return "本科"
    if label == "college_or_above":
        return "大专"
    return None


def minimal_precheck_args(args: argparse.Namespace, candidate_ref: str, status: str, note: str) -> argparse.Namespace:
    return argparse.Namespace(
        job_ref=args.job_ref,
        candidate_ref=candidate_ref,
        candidate_name=args.candidate_name,
        age=args.age,
        target_role=args.target_role,
        city=args.city,
        salary=args.salary,
        years_experience=args.years_experience,
        education_level=args.education_level,
        status=status,
        note=note,
        read_at=args.read_at,
    )


def list_prefilter(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    max_age = hard_age_max(conn, args.job_ref)
    min_education = hard_education_min(conn, args.job_ref)
    normalized_education = education_rank(args.education_level or "")
    candidate_ref = infer_candidate_ref(args.candidate_name, args.target_role, args.city, args.candidate_ref)
    candidate_key = candidate_identity_key(candidate_ref, args.candidate_name)
    if max_age is not None and args.age is not None and args.age >= max_age:
        note = args.note or f"列表显示{args.age}岁，不符合{max_age}岁以下硬性年龄要求。"
        minimal_args = minimal_precheck_args(args, candidate_ref, "REJECT_LIST_AGE_PRECHECK", note)
        row = upsert_candidate_minimal(conn, minimal_args)
        return {
            "job_ref": args.job_ref,
            "candidate_ref": candidate_ref,
            "candidate_key": candidate_key,
            "age": args.age,
            "max_age": max_age,
            "education_level": normalized_education or "",
            "min_education": min_education or "",
            "precheck": "failed_age",
            "action": "skip_resume",
            "status": "REJECT_LIST_AGE_PRECHECK",
            "resume_id": row["id"],
            "note": note,
        }
    if min_education is not None and normalized_education:
        candidate_edu = education_value(normalized_education)
        required_edu = education_value(min_education)
        if candidate_edu is not None and required_edu is not None and candidate_edu < required_edu:
            note = args.note or f"列表显示学历{normalized_education}，不符合{min_education}以上硬性学历要求。"
            minimal_args = minimal_precheck_args(args, candidate_ref, "REJECT_LIST_EDUCATION_PRECHECK", note)
            row = upsert_candidate_minimal(conn, minimal_args)
            return {
                "job_ref": args.job_ref,
                "candidate_ref": candidate_ref,
                "candidate_key": candidate_key,
                "age": "" if args.age is None else args.age,
                "max_age": "" if max_age is None else max_age,
                "education_level": normalized_education,
                "min_education": min_education,
                "precheck": "failed_education",
                "action": "skip_resume",
                "status": "REJECT_LIST_EDUCATION_PRECHECK",
                "resume_id": row["id"],
                "note": note,
            }
    return {
        "job_ref": args.job_ref,
        "candidate_ref": candidate_ref,
        "candidate_key": candidate_key,
        "age": "" if args.age is None else args.age,
        "max_age": "" if max_age is None else max_age,
        "education_level": normalized_education or "",
        "min_education": min_education or "",
        "precheck": "passed",
        "action": "open_resume",
    }


def list_age_precheck(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    return list_prefilter(conn, args)


def parse_batch_candidate(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in re.split(r"\s*\|\s*|\t", value.strip())]
    while len(parts) < 3:
        parts.append("")
    name, age_text, education = parts[:3]
    if not name:
        raise SystemExit("Batch candidate must include a name: 姓名|年龄|学历")
    age = None
    if age_text:
        parsed_age = parse_age(age_text)
        if parsed_age is None and age_text.isdigit():
            parsed_age = int(age_text)
        age = parsed_age
    return {"candidate_name": name, "age": age, "education_level": education}


def seen_in_run_lookup(conn: sqlite3.Connection, run_id: str | None, items: list[dict[str, Any]]) -> set[str]:
    if not run_id or not items:
        return set()
    fingerprints = list(dict.fromkeys(batch_lookup_key(item) for item in items))
    placeholders = ",".join("?" for _ in fingerprints)
    rows = conn.execute(
        f"""
        SELECT candidate_fingerprint
        FROM screening_run_seen_candidates
        WHERE run_id = ?
          AND candidate_fingerprint IN ({placeholders})
        """,
        (run_id, *fingerprints),
    ).fetchall()
    return {str(row["candidate_fingerprint"]) for row in rows}


def mark_seen_in_run(conn: sqlite3.Connection, run_id: str | None, job_ref: str, item: dict[str, Any], status: str, seen_at: str) -> None:
    if not run_id:
        return
    normalized_education = education_rank(item.get("education_level") or "")
    conn.execute(
        """
        INSERT INTO screening_run_seen_candidates (
          run_id, job_ref, candidate_fingerprint, candidate_name, age, education_level, status, seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, candidate_fingerprint) DO UPDATE SET
          job_ref=excluded.job_ref,
          candidate_name=excluded.candidate_name,
          age=excluded.age,
          education_level=excluded.education_level,
          status=excluded.status,
          seen_at=excluded.seen_at
        """,
        (
            run_id,
            job_ref,
            batch_lookup_key(item),
            item.get("candidate_name"),
            item.get("age"),
            normalized_education,
            status,
            seen_at,
        ),
    )


def cleanup_screening_run_seen(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    retention_days = int(getattr(args, "retention_days", 14) or 14)
    cutoff = (datetime.now().astimezone() - timedelta(days=retention_days)).isoformat(timespec="seconds")
    cur = conn.execute("DELETE FROM screening_run_seen_candidates WHERE seen_at < ?", (cutoff,))
    if getattr(args, "commit", True):
        conn.commit()
    return {
        "status": "ok",
        "retention_days": retention_days,
        "cutoff": cutoff,
        "deleted_count": cur.rowcount,
    }


def batch_list_prefilter(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    open_names: list[str] = []
    skip_names: list[str] = []
    duplicate_names: list[str] = []
    seen_run_names: list[str] = []
    unknown_names: list[str] = []
    failed_age = 0
    failed_education = 0
    items = [parse_batch_candidate(raw_candidate) for raw_candidate in args.candidate]
    duplicate_by_name = batch_processed_lookup(conn, items)
    seen_fingerprints = seen_in_run_lookup(conn, getattr(args, "run_id", None), items)
    max_age = hard_age_max(conn, args.job_ref)
    min_education = hard_education_min(conn, args.job_ref)
    pending_writes = 0
    seen_writes = 0
    seen_at = args.read_at or now_iso()

    for item in items:
        candidate_name = item["candidate_name"]
        if batch_lookup_key(item) in seen_fingerprints:
            seen_run_names.append(candidate_name)
            continue
        if batch_lookup_key(item) in duplicate_by_name:
            duplicate_names.append(candidate_name)
            mark_seen_in_run(conn, getattr(args, "run_id", None), args.job_ref, item, "duplicate_global", seen_at)
            seen_writes += 1
            continue

        normalized_education = education_rank(item["education_level"] or "")
        result = {
            "precheck": "passed",
            "action": "open_resume",
            "note": None,
            "status": None,
        }
        if max_age is not None and item["age"] is not None and item["age"] >= max_age:
            result = {
                "precheck": "failed_age",
                "action": "skip_resume",
                "note": f"列表显示{item['age']}岁，不符合{max_age}岁以下硬性年龄要求。",
                "status": "REJECT_LIST_AGE_PRECHECK",
            }
        elif min_education is not None and normalized_education:
            candidate_edu = education_value(normalized_education)
            required_edu = education_value(min_education)
            if candidate_edu is not None and required_edu is not None and candidate_edu < required_edu:
                result = {
                    "precheck": "failed_education",
                    "action": "skip_resume",
                    "note": f"列表显示学历{normalized_education}，不符合{min_education}以上硬性学历要求。",
                    "status": "REJECT_LIST_EDUCATION_PRECHECK",
                }

        if result["action"] == "open_resume":
            prefilter_args = argparse.Namespace(
                job_ref=args.job_ref,
                candidate_ref=candidate_name,
                candidate_name=candidate_name,
                age=item["age"],
                target_role=None,
                city=None,
                salary=None,
                years_experience=None,
                education_level=item["education_level"],
                note="列表年龄/学历预筛通过，待打开在线简历。",
                read_at=args.read_at,
            )
            minimal_args = minimal_precheck_args(
                prefilter_args,
                candidate_name,
                "LIST_PREFILTER_PASSED",
                "列表年龄/学历预筛通过，待打开在线简历。",
            )
            upsert_candidate_minimal(conn, minimal_args, commit=False)
            pending_writes += 1
            open_names.append(candidate_name)
            mark_seen_in_run(conn, getattr(args, "run_id", None), args.job_ref, item, "queued_open_resume", seen_at)
            seen_writes += 1
            if item["age"] is None or not normalized_education:
                unknown_names.append(candidate_name)
            continue

        prefilter_args = argparse.Namespace(
            job_ref=args.job_ref,
            candidate_ref=candidate_name,
            candidate_name=candidate_name,
            age=item["age"],
            target_role=None,
            city=None,
            salary=None,
            years_experience=None,
            education_level=item["education_level"],
            note=result["note"],
            read_at=args.read_at,
        )
        minimal_args = minimal_precheck_args(prefilter_args, candidate_name, str(result["status"]), str(result["note"]))
        upsert_candidate_minimal(conn, minimal_args, commit=False)
        pending_writes += 1
        mark_seen_in_run(conn, getattr(args, "run_id", None), args.job_ref, item, str(result["status"]), seen_at)
        seen_writes += 1
        skip_names.append(candidate_name)
        if result["precheck"] == "failed_age":
            failed_age += 1
        elif result["precheck"] == "failed_education":
            failed_education += 1

    result = {
        "job_ref": args.job_ref,
        "total": len(items),
        "open_count": len(open_names),
        "skip_count": len(skip_names),
        "duplicate_count": len(duplicate_names),
        "seen_in_run_count": len(seen_run_names),
        "failed_age_count": failed_age,
        "failed_education_count": failed_education,
        "unknown_visible_count": len(unknown_names),
        "run_id": getattr(args, "run_id", None) or "",
        "max_age": "" if max_age is None else max_age,
        "min_education": min_education or "",
        "open_candidates": "、".join(open_names),
        "skip_candidates": "、".join(skip_names),
        "duplicate_candidates": "、".join(duplicate_names),
        "seen_in_run_candidates": "、".join(seen_run_names),
        "unknown_visible_candidates": "、".join(unknown_names),
    }
    conn.execute(
        """
        INSERT INTO run_events (event_type, job_ref, candidate_ref, status, note, detail_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "batch_list_prefilter",
            args.job_ref,
            None,
            "ok",
            (
                f"total={result['total']}; open={result['open_count']}; skip={result['skip_count']}; "
                f"duplicate={result['duplicate_count']}; seen_in_run={result['seen_in_run_count']}"
            ),
            json.dumps(result, ensure_ascii=False),
            seen_at,
        ),
    )

    if pending_writes or seen_writes or items:
        conn.commit()

    return result


def get_resume(conn: sqlite3.Connection, job_ref: str, candidate_ref: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM resumes WHERE job_ref = ? AND candidate_ref = ?", (job_ref, candidate_ref)).fetchone()
    if row is None:
        raise SystemExit(f"No resume found in SQLite for job_ref={job_ref}, candidate_ref={candidate_ref}")
    data = dict(row)
    key = data.get("candidate_key")
    data["features"] = {r["feature_key"]: r["feature_value"] for r in conn.execute("SELECT feature_key, feature_value FROM candidate_features WHERE candidate_key = ?", (key,))}
    data["skills"] = [r["skill"] for r in conn.execute("SELECT skill FROM candidate_skills WHERE candidate_key = ? ORDER BY skill", (key,))]
    data["languages"] = [r["language"] for r in conn.execute("SELECT language FROM candidate_languages WHERE candidate_key = ? ORDER BY language", (key,))]
    data["experience"] = [dict(r) for r in conn.execute("SELECT * FROM candidate_experience WHERE candidate_key = ? ORDER BY id", (key,))]
    data["projects"] = [dict(r) for r in conn.execute("SELECT * FROM candidate_projects WHERE candidate_key = ? ORDER BY id", (key,))]
    return data


def get_match(conn: sqlite3.Connection, match_id: int | None, job_ref: str | None, candidate_ref: str | None) -> dict[str, Any]:
    if match_id is not None:
        row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM matches WHERE job_ref = ? AND candidate_ref = ? ORDER BY matched_at DESC, id DESC LIMIT 1", (job_ref, candidate_ref)).fetchone()
    if row is None:
        raise SystemExit("No match found in SQLite")
    data = dict(row)
    data["sqlite_match_id"] = data["id"]
    return data


def check_processed(
    conn: sqlite3.Connection,
    job_ref: str,
    candidate_ref: str,
    age: int | None = None,
    education_level: str | None = None,
) -> dict[str, Any]:
    key = candidate_identity_key(candidate_ref)
    fingerprint = candidate_fingerprint(candidate_ref, age, education_level)
    row = None
    if age is not None or education_level:
        row = conn.execute(
            """
            SELECT *
            FROM processed_candidates
            WHERE candidate_fingerprint = ? OR candidate_key = ?
            ORDER BY processed_at DESC, id DESC
            LIMIT 1
            """,
            (fingerprint, fingerprint),
        ).fetchone()
        if row is None:
            return {
                "job_ref": job_ref,
                "candidate_ref": candidate_ref,
                "candidate_key": key,
                "candidate_fingerprint": fingerprint,
                "processed": False,
                "scope": "none",
            }
    if row is None:
        row = conn.execute("SELECT * FROM processed_candidates WHERE candidate_key = ? ORDER BY processed_at DESC, id DESC LIMIT 1", (key,)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM processed_candidates WHERE candidate_ref = ? ORDER BY processed_at DESC, id DESC LIMIT 1", (candidate_ref,)).fetchone()
    if row is None:
        name_guess = candidate_name_from_ref(candidate_ref)
        if name_guess:
            row = conn.execute("SELECT * FROM processed_candidates WHERE candidate_name = ? OR candidate_ref = ? ORDER BY processed_at DESC, id DESC LIMIT 1", (name_guess, name_guess)).fetchone()
    if row is None:
        return {
            "job_ref": job_ref,
            "candidate_ref": candidate_ref,
            "candidate_key": key,
            "candidate_fingerprint": fingerprint,
            "processed": False,
            "scope": "none",
        }
    data = dict(row)
    data["processed"] = True
    data["scope"] = "candidate_fingerprint" if data.get("candidate_fingerprint") == fingerprint else "global_candidate_key"
    data["requested_job_ref"] = job_ref
    data["requested_candidate_ref"] = candidate_ref
    data["requested_candidate_fingerprint"] = fingerprint
    return data


def batch_processed_lookup(conn: sqlite3.Connection, candidates: list[dict[str, Any]]) -> dict[str, sqlite3.Row]:
    items = [item for item in candidates if item.get("candidate_name")]
    if not items:
        return {}
    names = [str(item["candidate_name"]) for item in items]
    fingerprints = [
        candidate_fingerprint(item.get("candidate_name"), item.get("age"), item.get("education_level"))
        for item in items
    ]
    name_keys = [candidate_identity_key(name) for name in names]
    values = list(dict.fromkeys([*fingerprints, *name_keys, *names]))
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        f"""
        SELECT *
        FROM processed_candidates
        WHERE candidate_key IN ({placeholders})
           OR candidate_fingerprint IN ({placeholders})
           OR candidate_ref IN ({placeholders})
           OR candidate_name IN ({placeholders})
        ORDER BY processed_at DESC, id DESC
        """,
        (*values, *values, *values, *values),
    ).fetchall()
    by_candidate: dict[str, sqlite3.Row] = {}
    by_fingerprint = {str(row["candidate_fingerprint"] or ""): row for row in rows if row["candidate_fingerprint"]}
    by_key = {str(row["candidate_key"] or ""): row for row in rows if row["candidate_key"]}
    by_exact_name = {str(row["candidate_name"] or ""): row for row in rows if row["candidate_name"]}
    by_ref_name = {candidate_name_from_ref(row["candidate_ref"]): row for row in rows if candidate_name_from_ref(row["candidate_ref"])}
    for item in items:
        name = str(item["candidate_name"])
        fingerprint = candidate_fingerprint(item.get("candidate_name"), item.get("age"), item.get("education_level"))
        name_key = candidate_identity_key(name)
        if fingerprint in by_fingerprint:
            by_candidate[batch_lookup_key(item)] = by_fingerprint[fingerprint]
        elif fingerprint in by_key:
            by_candidate[batch_lookup_key(item)] = by_key[fingerprint]
        elif not item.get("age") and not item.get("education_level") and name in by_exact_name:
            by_candidate[batch_lookup_key(item)] = by_exact_name[name]
        elif not item.get("age") and not item.get("education_level") and name in by_ref_name:
            by_candidate[batch_lookup_key(item)] = by_ref_name[name]
        elif not item.get("age") and not item.get("education_level") and name_key in by_key:
            by_candidate[batch_lookup_key(item)] = by_key[name_key]
    return by_candidate


def insert_report_record(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    created_at = now_iso()
    body = Path(args.body_file).read_text(encoding="utf-8")
    cur = conn.execute(
        """
        INSERT INTO reports (report_type, period_start, period_end, body, summary_text, sent_status, sent_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (args.report_type, args.period_start, args.period_end, body, args.summary_text, args.sent_status, args.sent_at, created_at),
    )
    conn.commit()
    return dict(conn.execute("SELECT id, report_type, period_start, period_end, sent_status, sent_at, created_at FROM reports WHERE id = ?", (cur.lastrowid,)).fetchone())


def insert_run_event(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    created = args.created_at or now_iso()
    detail_text = read_text_arg(args.detail_text, args.detail_text_file)
    cur = conn.execute(
        """
        INSERT INTO run_events (event_type, job_ref, candidate_ref, status, note, detail_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (args.event_type, args.job_ref, args.candidate_ref, args.status, args.note, detail_text, created),
    )
    conn.commit()
    return dict(conn.execute("SELECT id, event_type, job_ref, candidate_ref, status, created_at FROM run_events WHERE id = ?", (cur.lastrowid,)).fetchone())


def stale_cutoff_iso(minutes: int) -> str:
    return (datetime.now().astimezone() - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def automation_lock(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    current = now_iso()
    stale_before = stale_cutoff_iso(args.stale_minutes)
    if args.action == "acquire":
        cleanup_screening_run_seen(conn, argparse.Namespace(retention_days=14, commit=False))
        active = conn.execute(
            """
            SELECT * FROM automation_runs
            WHERE flow_id = ?
              AND status = 'RUNNING'
              AND heartbeat_at >= ?
            ORDER BY heartbeat_at DESC
            LIMIT 1
            """,
            (args.flow_id, stale_before),
        ).fetchone()
        if active is not None:
            return {
                "flow_id": args.flow_id,
                "status": "blocked",
                "active_run_id": active["run_id"],
                "heartbeat_at": active["heartbeat_at"],
            }
        run_id = args.run_id or f"{args.flow_id}-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            UPDATE automation_runs
            SET status = 'STALE', ended_at = ?, note = COALESCE(note, '') || ' stale_before_new_run'
            WHERE flow_id = ? AND status = 'RUNNING' AND heartbeat_at < ?
            """,
            (current, args.flow_id, stale_before),
        )
        conn.execute(
            """
            INSERT INTO automation_runs (flow_id, run_id, status, started_at, heartbeat_at, note)
            VALUES (?, ?, 'RUNNING', ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              status='RUNNING',
              heartbeat_at=excluded.heartbeat_at,
              ended_at=NULL,
              note=excluded.note
            """,
            (args.flow_id, run_id, current, current, args.note),
        )
        conn.commit()
        return {"flow_id": args.flow_id, "run_id": run_id, "status": "acquired", "heartbeat_at": current}

    run_id = args.run_id
    if args.action == "status" and not run_id:
        rows = conn.execute(
            """
            SELECT run_id, status, started_at, heartbeat_at, ended_at, note
            FROM automation_runs
            WHERE flow_id = ?
            ORDER BY heartbeat_at DESC
            LIMIT 5
            """,
            (args.flow_id,),
        ).fetchall()
        return {
            "flow_id": args.flow_id,
            "runs": " | ".join(
                f"{row['run_id']}:{row['status']}@{row['heartbeat_at']}" for row in rows
            ),
            "count": len(rows),
        }
    if not run_id:
        raise SystemExit("--run-id is required for heartbeat/release")
    row = conn.execute("SELECT * FROM automation_runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return {"flow_id": args.flow_id, "run_id": run_id, "status": "missing"}
    if args.action == "heartbeat":
        conn.execute(
            "UPDATE automation_runs SET heartbeat_at = ?, note = COALESCE(?, note) WHERE run_id = ? AND status = 'RUNNING'",
            (current, args.note, run_id),
        )
        conn.commit()
        return {"flow_id": args.flow_id, "run_id": run_id, "status": "heartbeat", "heartbeat_at": current}
    if args.action == "release":
        final_status = args.status or "COMPLETED"
        conn.execute(
            "UPDATE automation_runs SET status = ?, ended_at = ?, heartbeat_at = ?, note = COALESCE(?, note) WHERE run_id = ?",
            (final_status, current, current, args.note, run_id),
        )
        conn.commit()
        return {"flow_id": args.flow_id, "run_id": run_id, "status": final_status, "ended_at": current}
    return dict(row)


def flow_scheduled_on_day(flow_id: str, day: str) -> bool:
    try:
        weekday = datetime.fromisoformat(day).weekday()
    except ValueError:
        return True
    if flow_id == "boss-1":
        return weekday in {0, 1, 2, 3, 4, 5}
    if flow_id == "boss-2":
        return weekday == 6
    if flow_id == "boss-4":
        return weekday == 0
    return True


def automation_heartbeat_check(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    day = args.day or datetime.now().astimezone().date().isoformat()
    stale_before = stale_cutoff_iso(args.stale_minutes)
    explicit_flow_ids = bool(args.flow_id)
    flow_ids = args.flow_id or [
        "boss-1",
        "boss-2",
        "boss-3",
        "boss-4",
        "xiaozhao-unfinished-tickets",
    ]
    rows: list[str] = []
    ok_count = 0
    stale_count = 0
    missing_count = 0
    completed_count = 0
    for flow_id in flow_ids:
        if not explicit_flow_ids and not flow_scheduled_on_day(flow_id, day):
            rows.append(f"{flow_id}:NOT_SCHEDULED")
            continue
        row = conn.execute(
            """
            SELECT run_id, status, started_at, heartbeat_at, ended_at, note
            FROM automation_runs
            WHERE flow_id = ?
              AND substr(started_at, 1, 10) = ?
            ORDER BY heartbeat_at DESC
            LIMIT 1
            """,
            (flow_id, day),
        ).fetchone()
        if row is None:
            missing_count += 1
            rows.append(f"{flow_id}:MISSING")
            continue
        status = str(row["status"] or "")
        heartbeat_at = str(row["heartbeat_at"] or "")
        if status == "RUNNING" and heartbeat_at >= stale_before:
            check_status = "OK"
            ok_count += 1
        elif status == "RUNNING":
            check_status = "STALE"
            stale_count += 1
        elif status in {"COMPLETED", "SKIPPED"}:
            check_status = status
            completed_count += 1
        else:
            check_status = status or "UNKNOWN"
            stale_count += 1
        rows.append(f"{flow_id}:{check_status}@{heartbeat_at}")
    overall = "OK" if stale_count == 0 and missing_count == 0 else "ATTENTION"
    return {
        "day": day,
        "stale_minutes": args.stale_minutes,
        "status": overall,
        "ok": ok_count,
        "completed": completed_count,
        "stale": stale_count,
        "missing": missing_count,
        "flows": " | ".join(rows),
    }


def wal_checkpoint(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    mode = "TRUNCATE" if args.truncate else "PASSIVE"
    row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
    return {"mode": mode, "busy": row[0], "log": row[1], "checkpointed": row[2]}


def sqlite_health_check(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    day = args.day or datetime.now().astimezone().date().isoformat()
    db_path = Path(args.db)
    required_tables = [
        "jobs",
        "job_requirements",
        "processed_candidates",
        "daily_processed_candidates",
        "forward_records",
        "run_events",
        "automation_runs",
        "reports",
    ]
    existing_tables = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
        ).fetchall()
    }
    missing_tables = [table for table in required_tables if table not in existing_tables]
    integrity = "skipped" if args.skip_integrity else str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
    wal_path = Path(f"{db_path}-wal")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    daily_processed = scalar_int(
        conn,
        "SELECT COUNT(*) FROM daily_processed_candidates WHERE process_date = ?",
        (day,),
    )
    running_automation = scalar_int(
        conn,
        """
        SELECT COUNT(*)
        FROM automation_runs
        WHERE status = 'RUNNING'
          AND heartbeat_at >= ?
        """,
        (stale_cutoff_iso(args.stale_minutes),),
    )
    heartbeat = automation_heartbeat_check(
        conn,
        argparse.Namespace(flow_id=args.flow_id, day=day, stale_minutes=args.stale_minutes),
    )
    status = "OK"
    problems: list[str] = []
    if integrity != "ok" and integrity != "skipped":
        problems.append(f"integrity={integrity}")
    if missing_tables:
        problems.append("missing_tables=" + ",".join(missing_tables))
    if heartbeat["status"] != "OK":
        problems.append("heartbeat=" + heartbeat["status"])
    if problems:
        status = "ATTENTION"
    return {
        "status": status,
        "database_path": str(db_path.resolve()),
        "integrity": integrity,
        "journal_mode": journal_mode,
        "wal_bytes": wal_bytes,
        "required_tables_missing": ",".join(missing_tables),
        "daily_processed": daily_processed,
        "running_automation": running_automation,
        "heartbeat_status": heartbeat["status"],
        "heartbeat_flows": heartbeat["flows"],
        "problems": " | ".join(problems),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"backup_file": str(path), "status": "missing", "integrity": "", "sha256": ""}
    try:
        with sqlite3.connect(str(path), timeout=10) as backup_conn:
            integrity = str(backup_conn.execute("PRAGMA integrity_check").fetchone()[0])
            tables = scalar_int(
                backup_conn,
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('jobs','processed_candidates','reports')",
            )
    except sqlite3.Error as exc:
        return {
            "backup_file": str(path),
            "status": "invalid",
            "integrity": str(exc),
            "sha256": file_sha256(path),
        }
    status = "ok" if integrity == "ok" and tables >= 3 else "attention"
    return {
        "backup_file": str(path),
        "status": status,
        "integrity": integrity,
        "required_table_hits": tables,
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def backup_metadata(source_db: Path, backup_path: Path, sha256: str, label: str, integrity: str) -> dict[str, Any]:
    return {
        "created_at": now_iso(),
        "source_db": str(source_db.resolve()),
        "backup_file": str(backup_path.resolve()),
        "sha256": sha256,
        "bytes": backup_path.stat().st_size,
        "label": label,
        "integrity": integrity,
    }


def ensure_backup_dir_allowed(path: Path) -> None:
    resolved = path.expanduser().resolve()
    forbidden_roots = [
        Path.home() / ".codex",
        Path.home() / ".hermes",
    ]
    for forbidden in forbidden_roots:
        try:
            resolved.relative_to(forbidden.resolve())
            raise SystemExit(f"Backup directory is not allowed under Codex/Hermes path: {resolved}")
        except ValueError:
            pass
    if ".codex" in resolved.parts or ".hermes" in resolved.parts:
        raise SystemExit(f"Backup directory is not allowed under Codex/Hermes path: {resolved}")


def write_backup_sidecars(backup_path: Path, metadata: dict[str, Any]) -> None:
    backup_path.with_suffix(backup_path.suffix + ".sha256").write_text(
        f"{metadata['sha256']}  {backup_path.name}\n",
        encoding="utf-8",
    )
    backup_path.with_suffix(backup_path.suffix + ".json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def cleanup_sqlite_sidecars(path: Path) -> None:
    Path(f"{path}-wal").unlink(missing_ok=True)
    Path(f"{path}-shm").unlink(missing_ok=True)
    Path(f"{path}-journal").unlink(missing_ok=True)


def create_sqlite_backup(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    source_db = Path(args.db)
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", args.label or "auto").strip("-") or "auto"
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    filename = f"xiaozhao-recruitment-{timestamp}-{label}.sqlite3"
    backup_dir = Path(args.backup_dir)
    desktop_dir = Path(args.desktop_backup_dir)
    ensure_backup_dir_allowed(backup_dir)
    ensure_backup_dir_allowed(desktop_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    desktop_dir.mkdir(parents=True, exist_ok=True)

    source_integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    if source_integrity != "ok":
        raise SystemExit(f"Source SQLite integrity_check failed: {source_integrity}")
    checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()

    local_path = backup_dir / filename
    tmp_path = local_path.with_suffix(local_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    with sqlite3.connect(str(tmp_path), timeout=10) as backup_conn:
        conn.backup(backup_conn)
    tmp_verify = verify_backup_file(tmp_path)
    cleanup_sqlite_sidecars(tmp_path)
    if tmp_verify["status"] != "ok":
        tmp_path.unlink(missing_ok=True)
        raise SystemExit(f"Backup verification failed: {tmp_verify}")
    tmp_path.replace(local_path)
    local_sha = file_sha256(local_path)
    local_meta = backup_metadata(source_db, local_path, local_sha, label, str(tmp_verify["integrity"]))
    write_backup_sidecars(local_path, local_meta)

    desktop_path = desktop_dir / filename
    shutil.copy2(local_path, desktop_path)
    desktop_sha = file_sha256(desktop_path)
    desktop_meta = backup_metadata(source_db, desktop_path, desktop_sha, label, str(tmp_verify["integrity"]))
    write_backup_sidecars(desktop_path, desktop_meta)
    if desktop_sha != local_sha:
        raise SystemExit("Desktop backup sha256 mismatch")

    return {
        "status": "ok",
        "source_db": str(source_db.resolve()),
        "local_backup": str(local_path.resolve()),
        "desktop_backup": str(desktop_path.resolve()),
        "sha256": local_sha,
        "bytes": local_path.stat().st_size,
        "checkpoint_busy": checkpoint[0],
        "checkpoint_log": checkpoint[1],
        "checkpointed": checkpoint[2],
        "integrity": str(tmp_verify["integrity"]),
    }


def backup_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("xiaozhao-recruitment-*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)


def list_sqlite_backups(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    local_dir = Path(args.backup_dir)
    desktop_dir = Path(args.desktop_backup_dir)
    local_files = backup_files(local_dir)
    desktop_files = backup_files(desktop_dir)
    return {
        "status": "ok",
        "local_count": len(local_files),
        "desktop_count": len(desktop_files),
        "local_latest": str(local_files[0].resolve()) if local_files else "",
        "desktop_latest": str(desktop_files[0].resolve()) if desktop_files else "",
    }


def verify_sqlite_backup(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    backup_path = Path(args.backup_file) if args.backup_file else None
    if backup_path is None:
        files = backup_files(Path(args.backup_dir))
        if not files:
            return {"status": "missing", "backup_file": "", "integrity": "", "sha256": ""}
        backup_path = files[0]
    result = verify_backup_file(backup_path)
    sidecar = backup_path.with_suffix(backup_path.suffix + ".sha256")
    if sidecar.exists() and result.get("sha256"):
        expected = sidecar.read_text(encoding="utf-8").split()[0]
        result["sha256_sidecar_match"] = str(expected == result["sha256"])
    else:
        result["sha256_sidecar_match"] = ""
    return result


def viewed_resume_count(conn: sqlite3.Connection, job_ref: str, day: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT COALESCE(NULLIF(candidate_ref, ''), '#' || id)) AS count
        FROM run_events
        WHERE event_type = 'online_resume_viewed'
          AND job_ref = ?
          AND substr(created_at, 1, 10) = ?
        """,
        (job_ref, day),
    ).fetchone()
    return int(row["count"] or 0)


def per_job_view_quota(args: argparse.Namespace) -> int:
    tab = str(getattr(args, "recommend_tab", "") or "").strip()
    if tab == "latest":
        return int(getattr(args, "latest_tab_quota", 50))
    return int(getattr(args, "recommend_tab_quota", 40))


def record_online_resume_view(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    event = insert_run_event(
        conn,
        argparse.Namespace(
            event_type="online_resume_viewed",
            job_ref=args.job_ref,
            candidate_ref=args.candidate_ref,
            status="viewed",
            note="online_resume_opened",
            detail_text="",
            detail_text_file=None,
            created_at=args.created_at,
        ),
    )
    day = str(event["created_at"])[:10]
    count = viewed_resume_count(conn, args.job_ref, day)
    quota = per_job_view_quota(args)
    return {
        "id": event["id"],
        "job_ref": args.job_ref,
        "candidate_ref": args.candidate_ref,
        "viewed_count": count,
        "quota": quota,
        "recommend_tab": args.recommend_tab,
        "recommend_tab_quota": args.recommend_tab_quota,
        "latest_tab_quota": args.latest_tab_quota,
        "open_job_count": args.open_job_count,
        "remaining": max(0, quota - count),
        "quota_reached": 1 if count >= quota else 0,
        "day": day,
    }


def view_quota(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    day = args.day or now_iso()[:10]
    refs = [args.job_ref] if args.job_ref else [
        row["job_ref"]
        for row in conn.execute(
            "SELECT DISTINCT job_ref FROM run_events WHERE event_type = 'online_resume_viewed' AND substr(created_at, 1, 10) = ? ORDER BY job_ref",
            (day,),
        ).fetchall()
    ]
    if not refs:
        refs = [row["job_ref"] for row in conn.execute("SELECT job_ref FROM jobs ORDER BY job_ref").fetchall()]
    open_job_count = args.open_job_count or len(refs)
    quota = per_job_view_quota(args)
    rows = []
    for ref in refs:
        count = viewed_resume_count(conn, ref, day)
        rows.append(f"{ref}:{count}/{quota}")
    return {
        "day": day,
        "recommend_tab": args.recommend_tab,
        "recommend_tab_quota": args.recommend_tab_quota,
        "latest_tab_quota": args.latest_tab_quota,
        "open_job_count": open_job_count,
        "quota": quota,
        "jobs": "；".join(rows),
    }


def jd_library_update(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    current = now_iso()
    action = args.action
    job_ref = canonical_job_name(args.job_ref) if args.job_ref else ""
    if action in {"新增", "更新"}:
        if not job_ref:
            raise SystemExit("--job-ref is required for JD add/update")
        jd_text = read_text_arg(args.jd_text, args.jd_text_file)
        if not jd_text.strip():
            raise SystemExit("--jd-text or --jd-text-file is required for JD add/update")
        jd_args = argparse.Namespace(
            job_ref=job_ref,
            job_title=job_ref,
            city=None,
            salary=None,
            experience=None,
            education=None,
            work_address=None,
            jd_text=jd_text,
            jd_text_file=None,
            jd_summary=args.summary or f"飞书{action}JD：{job_ref}",
            page_scrolled=False,
            description_scrolled=False,
            last_jd_read_at="FEISHU_USER_PROVIDED",
        )
        upsert_jd_record(conn, jd_args)
    elif action == "删除":
        if not job_ref:
            raise SystemExit("--job-ref is required for JD delete")
        conn.execute("DELETE FROM job_requirements WHERE job_ref = ?", (job_ref,))
        conn.execute("DELETE FROM job_hard_gates WHERE job_ref = ?", (job_ref,))
        conn.execute("DELETE FROM jd_fts WHERE job_ref = ?", (job_ref,))
        conn.execute("DELETE FROM jobs WHERE job_ref = ?", (job_ref,))
    elif action == "查看":
        rows = conn.execute(
            """
            SELECT j.job_ref,
                   r.requirement_type,
                   r.category,
                   r.label,
                   r.value
            FROM jobs j
            LEFT JOIN job_requirements r ON r.job_ref = j.job_ref
            ORDER BY j.job_ref, r.requirement_type, r.category, r.label
            """
        ).fetchall()
        jobs: dict[str, list[str]] = {}
        for row in rows:
            job_ref = row["job_ref"]
            jobs.setdefault(job_ref, [])
            value = str(row["value"] or row["label"] or "").strip()
            if value and value not in jobs[job_ref]:
                jobs[job_ref].append(value)
        return {"count": len(jobs), "jobs": " | ".join(f"{job_ref}：{'；'.join(values)}" for job_ref, values in jobs.items())}
    else:
        raise SystemExit("--action must be 新增, 更新, 删除, or 查看")
    cur = conn.execute(
        """
        INSERT INTO xiaozhao_jd_updates (
          action, job_ref, original_text, optimized_summary, source, operator, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            job_ref,
            read_text_arg(args.jd_text, args.jd_text_file),
            args.summary,
            args.source,
            args.operator,
            "APPLIED",
            current,
        ),
    )
    conn.commit()
    return {"jd_update_id": cur.lastrowid, "action": action, "job_ref": job_ref, "status": "APPLIED"}


def create_feedback(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    current = now_iso()
    cur = conn.execute(
        """
        INSERT INTO xiaozhao_feishu_feedback (
          original_text, optimized_summary, source, requester, status, created_at
        ) VALUES (?, ?, ?, ?, 'RECORDED', ?)
        """,
        (args.text, args.summary, args.source, args.requester, current),
    )
    feedback_id = int(cur.lastrowid)
    req_summary = args.summary or args.text
    req_cur = conn.execute(
        """
        INSERT INTO xiaozhao_feishu_requirement_tickets (
          original_text, optimized_summary, source, requester, feedback_id,
          status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?)
        """,
        (args.text, req_summary, args.source, args.requester, feedback_id, current, current),
    )
    conn.commit()
    return {"feedback_id": feedback_id, "requirement_ticket_id": req_cur.lastrowid, "status": "RECORDED"}


def ticket_table(kind: str) -> tuple[str, str]:
    if kind == "bug":
        return "xiaozhao_feishu_bug_tickets", "Bug单"
    if kind == "xq":
        return "xiaozhao_feishu_requirement_tickets", "需求单"
    raise SystemExit("--kind must be bug or xq")


def create_ticket(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    table, label = ticket_table(args.kind)
    current = now_iso()
    cur = conn.execute(
        f"""
        INSERT INTO {table} (
          original_text, optimized_summary, source, requester, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?)
        """,
        (args.text, args.summary or args.text, args.source, args.requester, current, current),
    )
    conn.commit()
    return {"ticket_type": label, "ticket_id": cur.lastrowid, "status": "OPEN"}


def list_tickets(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    table, label = ticket_table(args.kind)
    if args.ticket_id:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (args.ticket_id,)).fetchone()
        if row is None:
            return {"ticket_type": label, "ticket_id": args.ticket_id, "found": "false"}
        data = row_to_dict(row)
        return {
            "ticket_type": label,
            "ticket_id": data.get("id"),
            "status": data.get("status"),
            "summary": data.get("optimized_summary") or data.get("original_text"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
        }
    rows = conn.execute(
        f"""
        SELECT id, status, optimized_summary, original_text, created_at, updated_at
        FROM {table}
        WHERE status NOT IN ('COMPLETED', 'CLOSED')
        ORDER BY id ASC
        """
    ).fetchall()
    items = [
        f"{label} #{row['id']}｜{row['status']}｜{row['optimized_summary'] or row['original_text']}"
        for row in rows
    ]
    return {"ticket_type": label, "count": len(rows), "tickets": "；".join(items)}


def update_ticket_status(conn: sqlite3.Connection, args: argparse.Namespace) -> dict[str, Any]:
    table, label = ticket_table(args.kind)
    if args.action in {"accept", "reject"} and args.kind != "xq":
        raise SystemExit("accept/reject actions are only valid for xq requirement tickets")
    current = now_iso()
    status_map = {
        "close": "CLOSED",
        "complete": "COMPLETED" if args.kind == "bug" else "PENDING_ACCEPTANCE",
        "accept": "COMPLETED",
        "reject": "ACCEPTANCE_REJECTED",
    }
    status = status_map[args.action]
    extra_sets: list[str] = []
    params: list[Any] = [status, current]
    if args.action == "close":
        extra_sets.append("closed_at = ?")
        params.append(current)
    if args.action in {"complete", "accept"} and status == "COMPLETED":
        extra_sets.append("completed_at = ?")
        params.append(current)
    if args.action in {"accept", "reject"}:
        extra_sets.append("acceptance_reviewer = ?")
        extra_sets.append("acceptance_result = ?")
        params.extend([args.reviewer, status])
    params.append(args.ticket_id)
    set_sql = ", ".join(["status = ?", "updated_at = ?", *extra_sets])
    cur = conn.execute(f"UPDATE {table} SET {set_sql} WHERE id = ?", tuple(params))
    conn.commit()
    return {
        "ticket_type": label,
        "ticket_id": args.ticket_id,
        "status": status,
        "updated": cur.rowcount,
    }


def add_parsers() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("seed-user-jds")
    sub.add_parser("seed-jd-hard-gates")

    p = sub.add_parser("upsert-jd")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--job-title")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--experience")
    p.add_argument("--education")
    p.add_argument("--work-address")
    p.add_argument("--jd-text")
    p.add_argument("--jd-text-file")
    p.add_argument("--jd-summary")
    p.add_argument("--page-scrolled", action="store_true")
    p.add_argument("--description-scrolled", action="store_true")
    p.add_argument("--last-jd-read-at")

    p = sub.add_parser("prune-jds-current-day")
    p.add_argument("--open-job-ref", action="append", required=True)
    p.add_argument("--today")

    p = sub.add_parser("upsert-resume")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref")
    p.add_argument("--candidate-name")
    p.add_argument("--age", type=int)
    p.add_argument("--target-role")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--years-experience")
    p.add_argument("--education-level")
    p.add_argument("--resume-text")
    p.add_argument("--resume-text-file")
    p.add_argument("--resume-summary")
    p.add_argument("--personal-info")
    p.add_argument("--personal-info-file")
    p.add_argument("--expected-position")
    p.add_argument("--expected-position-file")
    p.add_argument("--education-experience")
    p.add_argument("--education-experience-file")
    p.add_argument("--certificates")
    p.add_argument("--certificates-file")
    p.add_argument("--work-experience")
    p.add_argument("--work-experience-file")
    p.add_argument("--project-experience")
    p.add_argument("--project-experience-file")
    p.add_argument("--professional-skills")
    p.add_argument("--professional-skills-file")
    p.add_argument("--structured-json")
    p.add_argument("--structured-json-file")
    p.add_argument("--page-url")
    p.add_argument("--source", default="boss_online_resume")
    p.add_argument("--read-status", default="success")
    p.add_argument("--run-id")
    p.add_argument("--read-at")
    p.add_argument("--skill", action="append")
    p.add_argument("--language", action="append")

    p = sub.add_parser("upsert-candidate-minimal")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref")
    p.add_argument("--candidate-name")
    p.add_argument("--age", type=int)
    p.add_argument("--target-role")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--years-experience")
    p.add_argument("--education-level")
    p.add_argument("--status")
    p.add_argument("--note")
    p.add_argument("--read-at")

    p = sub.add_parser("insert-match")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref", required=True)
    p.add_argument("--decision-tier", required=True)
    p.add_argument("--hard-pass", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--hard-fail-reasons")
    p.add_argument("--matched-evidence")
    p.add_argument("--missing-evidence")
    p.add_argument("--summary")
    p.add_argument("--recommend-reason")
    p.add_argument("--risk-reason")
    p.add_argument("--matched-at")

    p = sub.add_parser("mark-processed")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref", required=True)
    p.add_argument("--candidate-name")
    p.add_argument("--age", type=int)
    p.add_argument("--education-level")
    p.add_argument("--target-role")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--years-experience")
    p.add_argument("--status", required=True)
    p.add_argument("--note")

    p = sub.add_parser("record-forward")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref")
    p.add_argument("--candidate-name")
    p.add_argument("--candidate-key")
    p.add_argument("--age", type=int)
    p.add_argument("--education-level")
    p.add_argument("--target-role")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--years-experience")
    p.add_argument("--recipient", default="HR")
    p.add_argument("--match-id", type=int)
    p.add_argument("--status", default="SUCCESS")
    p.add_argument("--note")
    p.add_argument("--detail-text")
    p.add_argument("--forwarded-at")
    p.add_argument("--mark-processed", action="store_true")

    p = sub.add_parser("processed-check")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref", required=True)
    p.add_argument("--age", type=int)
    p.add_argument("--education-level")

    p = sub.add_parser("list-age-precheck")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref")
    p.add_argument("--candidate-name")
    p.add_argument("--age", type=int)
    p.add_argument("--target-role")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--years-experience")
    p.add_argument("--education-level")
    p.add_argument("--note")
    p.add_argument("--read-at")

    p = sub.add_parser("list-prefilter")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref")
    p.add_argument("--candidate-name")
    p.add_argument("--age", type=int)
    p.add_argument("--target-role")
    p.add_argument("--city")
    p.add_argument("--salary")
    p.add_argument("--years-experience")
    p.add_argument("--education-level")
    p.add_argument("--note")
    p.add_argument("--read-at")

    p = sub.add_parser("batch-list-prefilter")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate", action="append", required=True, help="Visible row as 姓名|年龄|学历; age/education may be empty when not visible.")
    p.add_argument("--run-id")
    p.add_argument("--read-at")

    p = sub.add_parser("cleanup-screening-run-seen")
    p.add_argument("--retention-days", type=int, default=14)

    p = sub.add_parser("get-latest-jd")
    p.add_argument("--job-ref", required=True)
    p = sub.add_parser("get-jd-hard-gates")
    p.add_argument("--job-ref", required=True)
    p = sub.add_parser("get-resume")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref", required=True)
    p = sub.add_parser("get-match")
    p.add_argument("--match-id", type=int)
    p.add_argument("--job-ref")
    p.add_argument("--candidate-ref")

    p = sub.add_parser("insert-report")
    p.add_argument("--report-type", required=True, choices=["daily", "weekly", "unfinished_tickets"])
    p.add_argument("--period-start", required=True)
    p.add_argument("--period-end", required=True)
    p.add_argument("--body-file", required=True)
    p.add_argument("--summary-text")
    p.add_argument("--sent-status")
    p.add_argument("--sent-at")

    p = sub.add_parser("insert-run-event")
    p.add_argument("--event-type", required=True)
    p.add_argument("--job-ref")
    p.add_argument("--candidate-ref")
    p.add_argument("--status")
    p.add_argument("--note")
    p.add_argument("--detail-text")
    p.add_argument("--detail-text-file")
    p.add_argument("--created-at")

    p = sub.add_parser("automation-lock")
    p.add_argument("--action", required=True, choices=["acquire", "heartbeat", "release", "status"])
    p.add_argument("--flow-id", required=True)
    p.add_argument("--run-id")
    p.add_argument("--status")
    p.add_argument("--note")
    p.add_argument("--stale-minutes", type=int, default=30)

    p = sub.add_parser("automation-heartbeat-check")
    p.add_argument("--flow-id", action="append")
    p.add_argument("--day")
    p.add_argument("--stale-minutes", type=int, default=30)

    p = sub.add_parser("wal-checkpoint")
    p.add_argument("--truncate", action="store_true")

    p = sub.add_parser("health-check")
    p.add_argument("--flow-id", action="append")
    p.add_argument("--day")
    p.add_argument("--stale-minutes", type=int, default=30)
    p.add_argument("--skip-integrity", action="store_true")

    p = sub.add_parser("backup-create")
    p.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    p.add_argument("--desktop-backup-dir", default=str(DEFAULT_DESKTOP_BACKUP_DIR))
    p.add_argument("--label", default="auto")

    p = sub.add_parser("backup-list")
    p.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    p.add_argument("--desktop-backup-dir", default=str(DEFAULT_DESKTOP_BACKUP_DIR))

    p = sub.add_parser("backup-verify")
    p.add_argument("--backup-file")
    p.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))

    p = sub.add_parser("record-online-resume-view")
    p.add_argument("--job-ref", required=True)
    p.add_argument("--candidate-ref", required=True)
    p.add_argument("--created-at")
    p.add_argument("--recommend-tab", choices=["recommend", "latest"], default="latest")
    p.add_argument("--recommend-tab-quota", type=int, default=30)
    p.add_argument("--latest-tab-quota", type=int, default=30)
    p.add_argument("--daily-limit", type=int, default=120, help=argparse.SUPPRESS)
    p.add_argument("--open-job-count", type=int, required=True)

    p = sub.add_parser("view-quota")
    p.add_argument("--job-ref")
    p.add_argument("--day")
    p.add_argument("--recommend-tab", choices=["recommend", "latest"], default="latest")
    p.add_argument("--recommend-tab-quota", type=int, default=30)
    p.add_argument("--latest-tab-quota", type=int, default=30)
    p.add_argument("--daily-limit", type=int, default=120, help=argparse.SUPPRESS)
    p.add_argument("--open-job-count", type=int)

    p = sub.add_parser("jd-library")
    p.add_argument("--action", required=True, choices=["新增", "更新", "删除", "查看"])
    p.add_argument("--job-ref")
    p.add_argument("--jd-text")
    p.add_argument("--jd-text-file")
    p.add_argument("--summary")
    p.add_argument("--source", default="feishu")
    p.add_argument("--operator")

    p = sub.add_parser("record-feedback")
    p.add_argument("--text", required=True)
    p.add_argument("--summary")
    p.add_argument("--source", default="feishu")
    p.add_argument("--requester")

    p = sub.add_parser("create-ticket")
    p.add_argument("--kind", required=True, choices=["bug", "xq"])
    p.add_argument("--text", required=True)
    p.add_argument("--summary")
    p.add_argument("--source", default="feishu")
    p.add_argument("--requester")

    p = sub.add_parser("list-tickets")
    p.add_argument("--kind", required=True, choices=["bug", "xq"])
    p.add_argument("--ticket-id", type=int)

    p = sub.add_parser("update-ticket")
    p.add_argument("--kind", required=True, choices=["bug", "xq"])
    p.add_argument("--ticket-id", type=int, required=True)
    p.add_argument("--action", required=True, choices=["close", "complete", "accept", "reject"])
    p.add_argument("--reviewer")
    return parser


def main() -> None:
    parser = add_parsers()
    args = parser.parse_args()
    with connect(Path(args.db)) as conn:
        if args.command == "init":
            result = {"database_path": str(Path(args.db).resolve()), "status": "ok"}
        elif args.command == "seed-user-jds":
            result = seed_user_provided_jds(conn)
        elif args.command == "seed-jd-hard-gates":
            result = seed_jd_hard_gates(conn)
        elif args.command == "upsert-jd":
            result = upsert_jd_record(conn, args)
        elif args.command == "prune-jds-current-day":
            result = prune_jds_to_current_open_jobs(conn, args.open_job_ref, args.today)
        elif args.command == "upsert-resume":
            result = upsert_resume_record(conn, args)
        elif args.command == "upsert-candidate-minimal":
            result = upsert_candidate_minimal(conn, args)
        elif args.command == "insert-match":
            result = insert_match_record(conn, args)
        elif args.command == "mark-processed":
            result = mark_processed(
                conn,
                args.job_ref,
                args.candidate_ref,
                args.candidate_name,
                args.status,
                args.note,
                args.age,
                args.education_level,
                args.target_role,
                args.city,
                args.salary,
                args.years_experience,
            )
        elif args.command == "record-forward":
            result = record_forward(conn, args)
        elif args.command == "processed-check":
            result = check_processed(conn, args.job_ref, args.candidate_ref, args.age, args.education_level)
        elif args.command == "list-age-precheck":
            result = list_age_precheck(conn, args)
        elif args.command == "list-prefilter":
            result = list_prefilter(conn, args)
        elif args.command == "batch-list-prefilter":
            result = batch_list_prefilter(conn, args)
        elif args.command == "cleanup-screening-run-seen":
            result = cleanup_screening_run_seen(conn, args)
        elif args.command == "get-latest-jd":
            result = get_latest_jd(conn, args.job_ref)
        elif args.command == "get-jd-hard-gates":
            result = get_jd_hard_gates(conn, args.job_ref)
        elif args.command == "get-resume":
            result = get_resume(conn, args.job_ref, args.candidate_ref)
        elif args.command == "get-match":
            result = get_match(conn, args.match_id, args.job_ref, args.candidate_ref)
        elif args.command == "insert-report":
            result = insert_report_record(conn, args)
        elif args.command == "insert-run-event":
            result = insert_run_event(conn, args)
        elif args.command == "automation-lock":
            result = automation_lock(conn, args)
        elif args.command == "automation-heartbeat-check":
            result = automation_heartbeat_check(conn, args)
        elif args.command == "wal-checkpoint":
            result = wal_checkpoint(conn, args)
        elif args.command == "health-check":
            result = sqlite_health_check(conn, args)
        elif args.command == "backup-create":
            result = create_sqlite_backup(conn, args)
        elif args.command == "backup-list":
            result = list_sqlite_backups(conn, args)
        elif args.command == "backup-verify":
            result = verify_sqlite_backup(conn, args)
        elif args.command == "record-online-resume-view":
            result = record_online_resume_view(conn, args)
        elif args.command == "view-quota":
            result = view_quota(conn, args)
        elif args.command == "jd-library":
            result = jd_library_update(conn, args)
        elif args.command == "record-feedback":
            result = create_feedback(conn, args)
        elif args.command == "create-ticket":
            result = create_ticket(conn, args)
        elif args.command == "list-tickets":
            result = list_tickets(conn, args)
        elif args.command == "update-ticket":
            result = update_ticket_status(conn, args)
        else:
            raise SystemExit(f"Unsupported command: {args.command}")
    print(plain_result(**result))


if __name__ == "__main__":
    main()
