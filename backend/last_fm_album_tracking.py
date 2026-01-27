import os
import time
from datetime import datetime, timezone

import requests
from celery import Celery, group
from celery.schedules import crontab
from env import load_environment
from supabase import Client, create_client

load_environment()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

last_fm_api_key = os.getenv("LAST_FM_API_KEY")
if not last_fm_api_key:
    raise RuntimeError("LAST_FM_API_KEY is required")

LAST_FM_API_BASE = "https://ws.audioscrobbler.com/2.0/"

celery = Celery("last_fm_album_tracking", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
celery.conf.timezone = "UTC"

celery.conf.beat_schedule = {
    "last-fm-track-listening-every-hour": {
        "task": "last_fm_album_tracking.track_all_users_recently_listened",
        "schedule": crontab(minute=45),
    },
}


def _lastfm_get(params):
    params = {**params, "api_key": last_fm_api_key, "format": "json"}
    response = requests.get(LAST_FM_API_BASE, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise ValueError(data.get("message") or "Last.fm API error")
    return data


def _album_key(artist_name, album_name):
    if not artist_name or not album_name:
        return None
    return f"{artist_name}::{album_name}".strip().lower()


def _image_map(images):
    mapped = {}
    for image in images:
        size = image.get("size")
        url = image.get("#text")
        if size and url:
            mapped[size] = url
    return mapped


@celery.task
def track_all_users_recently_listened():
    users_response = supabase.table("last_fm_users").select("lastfm_username").execute()
    job = group(
        get_recently_listened.s(user["lastfm_username"])
        for user in users_response.data
    )
    job.apply_async()


@celery.task
def get_recently_listened(lastfm_username):
    one_hour_ago = int(time.time() - 3600)
    payload = _lastfm_get({
        "method": "user.getrecenttracks",
        "user": lastfm_username,
        "from": one_hour_ago,
        "to": int(time.time()),
        "limit": 50,
    })

    items = payload.get("recenttracks", {}).get("track", [])
    if isinstance(items, dict):
        items = [items]

    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("last_fm_users").update({
        "last_synced_at": now_iso,
    }).eq("lastfm_username", lastfm_username).execute()

    for item in items:
        artist_name = item.get("artist", {}).get("#text", "")
        artist_mbid = item.get("artist", {}).get("mbid")
        track_name = item.get("name", "")
        track_url = item.get("url")
        album_name = item.get("album", {}).get("#text", "")
        now_playing = item.get("@attr", {}).get("nowplaying") == "true"
        date_uts = item.get("date", {}).get("uts")

        if not date_uts:
            # Skip currently playing items without a timestamp to avoid duplicates.
            continue

        played_at = datetime.fromtimestamp(int(date_uts), tz=timezone.utc).isoformat()
        album_key = _album_key(artist_name, album_name)

        if artist_name:
            artist_payload = {"artist_name": artist_name}
            if artist_mbid:
                artist_payload["artist_mbid"] = artist_mbid
            supabase.table("last_fm_artists").upsert(artist_payload).execute()

        if album_key:
            album_exists = supabase.table("last_fm_albums") \
                .select("album_key") \
                .eq("album_key", album_key) \
                .limit(1) \
                .execute()

            if not album_exists.data:
                try:
                    album_payload = _lastfm_get({
                        "method": "album.getInfo",
                        "artist": artist_name,
                        "album": album_name,
                        "autocorrect": 1,
                    })
                    album_info = album_payload.get("album", {})
                except (requests.RequestException, ValueError):
                    album_info = {}

                images = _image_map(album_info.get("image", []))
                tracks = album_info.get("tracks", {}).get("track", [])
                if isinstance(tracks, dict):
                    tracks = [tracks]

                album_insert = {
                    "album_key": album_key,
                    "album_name": album_info.get("name") or album_name,
                    "artist_name": album_info.get("artist") or artist_name,
                    "album_url": album_info.get("url"),
                    "release_date": (album_info.get("releasedate") or "").strip() or None,
                    "listeners": album_info.get("listeners"),
                    "playcount": album_info.get("playcount"),
                    "image_small": images.get("small"),
                    "image_medium": images.get("medium"),
                    "image_large": images.get("large") or images.get("extralarge"),
                    "total_tracks": len(tracks) if tracks else None,
                }

                supabase.table("last_fm_albums").upsert(album_insert).execute()

                for track in tracks:
                    track_rank = track.get("@attr", {}).get("rank")
                    if not track_rank:
                        continue
                    try:
                        track_number = int(track_rank)
                    except (TypeError, ValueError):
                        continue

                    track_name_value = track.get("name")
                    if not track_name_value:
                        continue

                    duration_value = track.get("duration")
                    duration_sec = None
                    if duration_value and str(duration_value).isdigit():
                        duration_sec = int(duration_value)

                    supabase.table("last_fm_album_tracks").upsert({
                        "album_key": album_key,
                        "track_number": track_number,
                        "track_name": track_name_value,
                        "track_url": track.get("url"),
                        "duration_sec": duration_sec,
                    }).execute()

                    track_artist = track.get("artist", {})
                    track_artist_name = track_artist.get("name") or track_artist.get("#text") or artist_name
                    if track_artist_name:
                        supabase.table("last_fm_artists").upsert({
                            "artist_name": track_artist_name,
                        }).execute()
                        supabase.table("last_fm_track_artists").upsert({
                            "album_key": album_key,
                            "track_number": track_number,
                            "artist_name": track_artist_name,
                            "artist_order": 1,
                        }).execute()

        listened_payload = {
            "lastfm_username": lastfm_username,
            "played_at": played_at,
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": album_name or None,
            "track_url": track_url,
            "now_playing": now_playing,
        }
        if album_key:
            listened_payload["album_key"] = album_key

        supabase.table("last_fm_listened_tracks").upsert(listened_payload).execute()


def get_albums_completion(lastfm_username):
    resp = supabase.rpc("get_last_fm_album_completion", {"p_lastfm_username": lastfm_username}).execute()
    output = []
    for row in resp.data:
        output.append({
            "album_id": row.get("album_key"),
            "album_name": row.get("album_name"),
            "artist": row.get("primary_artist"),
            "listened": row.get("listened"),
            "total": row.get("total"),
            "percentage": (row.get("listened") or 0) / (row.get("total") or 1),
            "album_image": row.get("album_image"),
        })
    return output


def get_album_tracks(lastfm_username, album_key):
    resp = supabase.rpc(
        "get_last_fm_album_tracks",
        {"p_lastfm_username": lastfm_username, "p_album_key": album_key}
    ).execute()

    output = []
    for row in resp.data:
        track_number = row.get("track_number")
        track_id = f"{album_key}:{track_number}" if track_number is not None else None
        output.append({
            "track_id": track_id,
            "track_name": row.get("track_name"),
            "track_number": track_number,
            "is_listened": row.get("is_listened"),
        })

    return output
