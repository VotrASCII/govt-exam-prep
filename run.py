"""
Module 5 — Scheduler
Manages state and schedules daily pipeline runs at 3:00 PM.
Usage:
  python run.py           # auto-scheduled mode
  python run.py --run-now # immediately process today's day
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import schedule
import time as time_mod

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "data" / "state.json"
TOTAL_DAYS = 12

# Ensure data dir exists
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"current_day": 1}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _run_day(day: int) -> None:
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running Day {day} ...")
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "pipeline" / "daily_runner.py"), "--day", str(day)],
        cwd=str(BASE_DIR),
    )
    if result.returncode != 0:
        print(f"  [ERROR] daily_runner.py exited with code {result.returncode}")
    else:
        print(f"  Day {day} complete.")


def run_current_day() -> bool:
    """Run the current day, increment state. Returns True if more days remain."""
    state = _load_state()
    day = state.get("current_day", 1)

    if day > TOTAL_DAYS:
        print("All 12 months processed. Happy studying! 🎉")
        return False

    _run_day(day)

    state["current_day"] = day + 1
    _save_state(state)

    if state["current_day"] > TOTAL_DAYS:
        print("\nAll 12 months processed. Happy studying! 🎉")
        return False

    print(f"  Next scheduled run: Day {state['current_day']} (tomorrow at 3:00 PM)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="RBI Grade B prep scheduler")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Skip the scheduler and immediately run today's day",
    )
    args = parser.parse_args()

    if args.run_now:
        run_current_day()
        return

    # Auto-scheduled mode: run immediately once, then schedule future runs at 3 PM
    state = _load_state()
    if state.get("current_day", 1) > TOTAL_DAYS:
        print("All 12 months processed. Happy studying! 🎉")
        return

    print("RBI Grade B Prep — Auto Scheduler")
    print(f"State: {state}")
    print("Running today's day immediately, then scheduling at 3:00 PM daily...")

    more = run_current_day()
    if not more:
        return

    def scheduled_job() -> None:
        still_more = run_current_day()
        if not still_more:
            # Cancel the recurring job once complete
            return schedule.CancelJob

    schedule.every().day.at("15:00").do(scheduled_job)

    print("Scheduler active. Press Ctrl+C to exit.")
    while True:
        schedule.run_pending()
        time_mod.sleep(30)


if __name__ == "__main__":
    main()
