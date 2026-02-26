#!/usr/bin/env python3
"""Run offline learning jobs (daily/weekly)."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime

from prisma import Prisma

from app.services.offline_learning_jobs import run_daily_job, run_weekly_job


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d").date()


async def _run(job: str, target_date: date | None) -> None:
    prisma = Prisma(auto_register=True)
    await prisma.connect()
    try:
        if job == "daily":
            summary = await run_daily_job(prisma, target_date=target_date)
        else:
            summary = await run_weekly_job(prisma, window_end=target_date)
    finally:
        if prisma.is_connected():
            await prisma.disconnect()
    print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run self-learning offline jobs")
    parser.add_argument("job", choices=["daily", "weekly"], help="Job type to execute")
    parser.add_argument("--date", dest="date_str", help="Window date in YYYY-MM-DD (UTC)")
    args = parser.parse_args()
    asyncio.run(_run(args.job, _parse_date(args.date_str)))


if __name__ == "__main__":
    main()
