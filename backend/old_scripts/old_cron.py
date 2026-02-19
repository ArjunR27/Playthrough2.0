from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore
import threading
from album_tracking import get_recently_listened
from last_fm_album_tracking import get_recently_listened as get_lastfm_recently_listened
from supabase import create_client, Client
import os
from env import load_environment

load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))


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
    for user_id in users:
        try:
            get_recently_listened(user_id)
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
    for username in users:
        try:
            get_lastfm_recently_listened(username)
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
    _run_spotify()
    _run_lastfm()
    print("Task completed successfully")
except Exception as e:
    print(f"Error running task: {e}")
