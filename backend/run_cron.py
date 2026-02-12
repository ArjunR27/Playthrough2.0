from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time

from album_tracking import get_recently_listened
from last_fm_album_tracking import get_recently_listened as get_lastfm_recently_listened
from supabase import create_client, Client
import os
from env import load_environment

load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

SPOTIFY_WORKERS = 4
LASTFM_WORKERS = 4

def _fetch_spotify_users():
    resp = supabase.table("users").select("user_id").execute()
    return [row.get("user_id") for row in (resp.data or []) if row.get("user_id")]

def _fetch_lastfm_users():
    resp = supabase.table("last_fm_users").select("lastfm_username").execute()
    return [row.get("lastfm_username") for row in (resp.data or []) if row.get("lastfm_username")]

def _run_spotify():
    users = _fetch_spotify_users()
    print(f"[cron][spotify] Starting recent listens for {len(users)} user(s)")
    started_at = time.time()
    successes = 0
    failures = 0
    with ThreadPoolExecutor(max_workers=SPOTIFY_WORKERS) as executor:
        futures = {executor.submit(get_recently_listened, user_id): user_id for user_id in users}
        for future in as_completed(futures):
            user_id = futures[future]
            try:
                future.result()
                successes += 1
                print(f"[cron][spotify] user_id={user_id} done")
            except Exception as exc:
                failures += 1
                print(f"[cron][spotify] user_id={user_id} error: {exc}")
    duration = time.time() - started_at
    print(f"[cron][spotify] Completed in {duration:.2f}s (ok={successes}, failed={failures})")

def _run_lastfm():
    users = _fetch_lastfm_users()
    print(f"[cron][lastfm] Starting recent listens for {len(users)} user(s)")
    started_at = time.time()
    successes = 0
    failures = 0
    with ThreadPoolExecutor(max_workers=LASTFM_WORKERS) as executor:
        futures = {executor.submit(get_lastfm_recently_listened, username): username for username in users}
        for future in as_completed(futures):
            username = futures[future]
            try:
                future.result()
                successes += 1
                print(f"[cron][lastfm] username={username} done")
            except Exception as exc:
                failures += 1
                print(f"[cron][lastfm] username={username} error: {exc}")
    duration = time.time() - started_at
    print(f"[cron][lastfm] Completed in {duration:.2f}s (ok={successes}, failed={failures})")

print("Cron job starting...")
print(f"Running task at {datetime.now()}")

try:
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_run_spotify),
            executor.submit(_run_lastfm),
        ]
        for future in as_completed(futures):
            future.result()
    print("Task completed successfully")
except Exception as e:
    print(f"Error running task: {e}")
