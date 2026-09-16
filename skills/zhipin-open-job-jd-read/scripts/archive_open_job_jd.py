#!/usr/bin/env python3
"""Store a BOSS/Zhipin open-job JD in the local SQLite index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "zhipin-boss-recruitment-bot" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

from sqlite_store import DEFAULT_DB, connect, plain_result, upsert_jd_record  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--job-ref", required=True)
    parser.add_argument("--job-title")
    parser.add_argument("--city")
    parser.add_argument("--salary")
    parser.add_argument("--experience")
    parser.add_argument("--education")
    parser.add_argument("--work-address")
    parser.add_argument("--jd-text")
    parser.add_argument("--jd-text-file")
    parser.add_argument("--jd-summary")
    parser.add_argument("--page-scrolled", action="store_true")
    parser.add_argument("--description-scrolled", action="store_true")
    parser.add_argument("--last-jd-read-at")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with connect(Path(args.db)) as conn:
        result = upsert_jd_record(conn, args)
    result["database_path"] = str(Path(args.db).resolve())
    result["storage"] = "sqlite"
    print(plain_result(**result))


if __name__ == "__main__":
    main()
