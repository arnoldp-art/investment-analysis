#!/usr/bin/env python3
"""
Daily scheduler — run this once; it will execute tracker.py every day at a
configured time and save an HTML report.

Usage:
    python schedule_daily.py              # runs at 07:30 local time
    python schedule_daily.py --time 08:00 # runs at 08:00 local time
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime


def next_run_seconds(target_time: str) -> float:
    now = datetime.now()
    h, m = map(int, target_time.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        from datetime import timedelta
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", default="07:30", help="Daily run time HH:MM (default 07:30)")
    args = parser.parse_args()

    print(f"Scheduler started — daily report will run at {args.time}")
    print("Press Ctrl+C to stop.\n")

    while True:
        wait = next_run_seconds(args.time)
        h, m = divmod(int(wait), 3600)
        print(f"Next report in {h}h {m//60}m — at {args.time}")
        time.sleep(wait)

        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Running daily report…")
        result = subprocess.run(
            [sys.executable, "tracker.py", "--save"],
            capture_output=False,
        )
        if result.returncode != 0:
            print("Report failed — check output above.")
        else:
            print("Report complete.\n")


if __name__ == "__main__":
    main()
