import os
import time
from datetime import datetime, timedelta, timezone

from run_cron import run_cron_once


def _env_bool(name, default):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def main():
    interval_seconds = int(os.getenv("CRON_INTERVAL_SECONDS", "900"))
    run_on_start = _env_bool("CRON_RUN_ON_START", True)

    if interval_seconds < 1:
        raise ValueError("CRON_INTERVAL_SECONDS must be >= 1")

    print(
        "[cron-worker] Starting loop "
        f"(interval_seconds={interval_seconds}, run_on_start={run_on_start})"
    )

    if not run_on_start:
        first_run_at = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
        print(
            "[cron-worker] Delaying first run "
            f"(first_run_utc={first_run_at.isoformat()})"
        )
        time.sleep(interval_seconds)

    while True:
        started_at = time.time()

        try:
            run_cron_once()
        except Exception as exc:
            print(f"[cron-worker] Unexpected crash while running cron: {exc}")

        elapsed = time.time() - started_at
        sleep_seconds = max(5, interval_seconds - elapsed)
        next_run_at = datetime.now(timezone.utc) + timedelta(seconds=sleep_seconds)
        print(
            f"[cron-worker] Sleeping {sleep_seconds:.2f}s "
            f"(next_run_utc={next_run_at.isoformat()})"
        )
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
