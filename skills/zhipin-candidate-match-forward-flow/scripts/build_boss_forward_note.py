#!/usr/bin/env python3
"""Deprecated no-op for the old BOSS forwarding note path.

Current workflow forwards only the resume and intentionally leaves the BOSS
forwarding message empty.
"""

from __future__ import annotations

import argparse


def compose() -> str:
    return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--match-id", type=int)
    parser.add_argument("--job-ref")
    parser.add_argument("--candidate-ref")
    return parser.parse_args()


def main() -> None:
    parse_args()
    print(compose())


if __name__ == "__main__":
    main()
