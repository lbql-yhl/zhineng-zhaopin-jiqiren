#!/usr/bin/env python3
"""Record and summarize screening performance metrics.

The metrics table stores timings only; it never stores full resume content.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sqlite_store import DEFAULT_DB, connect, plain_result, record_stage_metric  # noqa: E402


def day_bounds(day: str | None) -> tuple[str, str]:
    current = datetime.now().astimezone()
    if day:
        start = datetime.fromisoformat(day).replace(tzinfo=current.tzinfo)
    else:
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def report(conn, day: str | None) -> dict[str, object]:
    start, end = day_bounds(day)
    rows = conn.execute(
        """
        SELECT stage, COUNT(*) AS count,
               ROUND(AVG(duration_ms), 1) AS avg_ms,
               MAX(duration_ms) AS max_ms,
               SUM(cache_hit) AS cache_hits,
               SUM(model_calls) AS model_calls
        FROM screening_stage_metrics
        WHERE created_at >= ? AND created_at < ?
        GROUP BY stage
        ORDER BY SUM(duration_ms) DESC, stage
        """,
        (start, end),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(duration_ms), 0), COALESCE(SUM(cache_hit), 0) FROM screening_stage_metrics WHERE created_at >= ? AND created_at < ?",
        (start, end),
    ).fetchone()
    lines = [
        f"day={start[:10]}",
        f"metric_count={int(total[0] or 0)}",
        f"total_duration_ms={int(total[1] or 0)}",
        f"cache_hit_count={int(total[2] or 0)}",
    ]
    for row in rows:
        lines.append(
            "stage=" + str(row["stage"])
            + f";count={int(row['count'])};avg_ms={row['avg_ms']};max_ms={int(row['max_ms'] or 0)}"
            + f";cache_hits={int(row['cache_hits'] or 0)};model_calls={int(row['model_calls'] or 0)}"
        )
    return {"summary": "\n".join(lines), "stage_count": len(rows), "day": start[:10]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record")
    record.add_argument("--stage", required=True)
    record.add_argument("--duration-ms", required=True, type=int)
    record.add_argument("--run-id")
    record.add_argument("--job-ref")
    record.add_argument("--candidate-ref")
    record.add_argument("--browser-actions", type=int, default=0)
    record.add_argument("--model-calls", type=int, default=0)
    record.add_argument("--cache-hit", action="store_true")
    record.add_argument("--status", default="ok")
    record.add_argument("--note")

    summary = sub.add_parser("report")
    summary.add_argument("--day")

    args = parser.parse_args()
    with connect(Path(args.db)) as conn:
        if args.command == "record":
            result = record_stage_metric(
                conn, stage=args.stage, duration_ms=args.duration_ms, run_id=args.run_id,
                job_ref=args.job_ref, candidate_ref=args.candidate_ref,
                browser_actions=args.browser_actions, model_calls=args.model_calls,
                cache_hit=args.cache_hit, status=args.status, note=args.note,
            )
            conn.commit()
        else:
            result = report(conn, args.day)
    print(plain_result(**result))


if __name__ == "__main__":
    main()
