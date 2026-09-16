#!/usr/bin/env python3
"""Store a recommended BOSS/Zhipin online resume in SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "zhipin-boss-recruitment-bot" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from sqlite_store import DEFAULT_DB, connect, get_latest_jd, plain_result, upsert_resume_record  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--job-ref", required=True)
    parser.add_argument("--candidate-ref")
    parser.add_argument("--candidate-name")
    parser.add_argument("--target-role")
    parser.add_argument("--city")
    parser.add_argument("--salary")
    parser.add_argument("--years-experience")
    parser.add_argument("--education-level")
    parser.add_argument("--resume-text")
    parser.add_argument("--resume-text-file")
    parser.add_argument("--resume-summary")
    parser.add_argument("--read-at")
    parser.add_argument("--skill", action="append")
    parser.add_argument("--language", action="append")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with connect(Path(args.db)) as conn:
        result = upsert_resume_record(conn, args)
        try:
            jd = get_latest_jd(conn, result["job_ref"])
            result["open_job_jd_found"] = "yes"
            result["open_job_jd_read_at"] = jd.get("last_jd_read_at")
        except SystemExit:
            result["open_job_jd_found"] = "no"
            result["open_job_jd_read_at"] = ""
    result["database_path"] = str(Path(args.db).resolve())
    result["storage"] = "sqlite"
    print(plain_result(**result))


if __name__ == "__main__":
    main()
