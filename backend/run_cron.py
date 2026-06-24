from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore
import threading
from album_tracking import get_recently_listened
from last_fm_album_tracking import get_recently_listened as get_lastfm_recently_listened
from monthly_retention import run_lastfm_monthly_retention
from supabase import create_client, Client
import os
from env import load_environment

class RateLimiter:
    def __init__(self, rate, period):
        self.rate = rate
        self.period = period
        self._semaphore = Semaphore(rate)
        self._lock = threading.Lock()
    
    def acquire(self):
        self._semaphore.acquire()
        threading.Timer(self.period, self._semaphore.release).start()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, *args):
        pass


load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

SPOTIFY_RATE_LIMITER = RateLimiter(rate = 5, period = 1.0)
LASTFM_RATE_LIMITER = RateLimiter(rate = 5, period = 1.0)


def _fetch_spotify_users():
    resp = supabase.table("users").select("user_id").execute()
    return [row.get("user_id") for row in (resp.data or []) if row.get("user_id")]

def _fetch_lastfm_users():
    resp = supabase.table("last_fm_users").select("lastfm_username").execute()
    return [row.get("lastfm_username") for row in (resp.data or []) if row.get("lastfm_username")]

def _spotify_task(user_id):
    with SPOTIFY_RATE_LIMITER:
        try:
            get_recently_listened(user_id)
            return user_id, True, ""
        except Exception as exc:
            return user_id, False, str(exc)

def _lastfm_task(username):
    with LASTFM_RATE_LIMITER:
        try:
            get_lastfm_recently_listened(username)
            return username, True, ""
        except Exception as exc:
            return username, False, str(exc)
    
def _run_parallel(label, users, task_fn, max_workers):
    print(f"[cron][{label}] Starting recent listens for {len(users)} user(s)")
    started_at = time.time()
    successes = failures = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(task_fn, u): u for u in users}
        for future in as_completed(futures):
            user, ok, err = future.result()
            if ok:
                successes += 1
                print(f"[cron][{label}] {user} done")
            else:
                failures += 1
                print(f"[cron][{label}] {user} error: {err}")

    duration = time.time() - started_at
    print(f"[cron][{label}] Completed in {duration:.2f}s (ok={successes}, failed={failures})")


def run_cron_once():
    print("Cron job starting...")
    print(f"Running task at {datetime.now()}")

    run_lastfm_monthly_retention(supabase)

    spotify_users = _fetch_spotify_users()
    lastfm_users = _fetch_lastfm_users()

    # Keep per-provider threading, but run providers consecutively to reduce
    # cross-service contention on shared clients/connections.
    _run_parallel("spotify", spotify_users, _spotify_task, max_workers=5)
    _run_parallel("lastfm", lastfm_users, _lastfm_task, max_workers=2)

    print("Task completed successfully")


if __name__ == "__main__":
    try:
        run_cron_once()
    except Exception as e:
        print(f"Error running task: {e}")
