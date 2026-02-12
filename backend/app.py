import base64
import hashlib
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import spotipy
import requests
from cryptography.fernet import Fernet
from env import load_environment
from flask import Flask, jsonify, redirect, request, session
from supabase import create_client, Client
from flask_cors import CORS

from album_tracking import get_albums_completion, get_albums_completion_sorted, get_album_tracks
from last_fm_album_tracking import (
    get_albums_completion as get_lastfm_albums_completion,
    get_album_tracks as get_lastfm_album_tracks,
)
from validate_token import get_spotify_oauth, get_valid_token
load_environment()

def _parse_cors_origins():
    raw = os.getenv("CORS_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        return [frontend_url.rstrip("/")]
    return ["http://127.0.0.1:8080", "http://localhost:8080"]

def _is_production():
    app_env = os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development"
    return app_env.lower() == "production"

app = Flask(__name__)
CORS(app, origins=_parse_cors_origins(), supports_credentials=True)

secret_key_b64 = os.getenv("FLASK_SECRET_KEY")
if not secret_key_b64:
    raise RuntimeError("FLASK_SECRET_KEY is required")
app.config["SECRET_KEY"] = base64.b64decode(secret_key_b64)

is_prod = _is_production()
app.config["SESSION_COOKIE_SAMESITE"] = "None" if is_prod else "Lax"
app.config["SESSION_COOKIE_SECURE"] = is_prod
app.config["PREFERRED_URL_SCHEME"] = "https" if is_prod else "http"

frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:8080").rstrip("/")

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
encryption_key = os.getenv("ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY_DEV")
if not encryption_key:
    raise RuntimeError("ENCRYPTION_KEY is required")
cipher = Fernet(encryption_key.encode())

last_fm_api_key = os.getenv("LAST_FM_API_KEY")
last_fm_api_secret = os.getenv("LAST_FM_SHARED_SECRET")
last_fm_callback_url = os.getenv("LAST_FM_CALLBACK_URL")
LAST_FM_API_BASE = "https://ws.audioscrobbler.com/2.0/"
LAST_FM_SIGNUP_URL = "https://www.last.fm/join"

def _lastfm_get(params):
    if not last_fm_api_key:
        raise RuntimeError("LAST_FM_API_KEY is required")
    params = {**params, "api_key": last_fm_api_key, "format": "json"}
    response = requests.get(LAST_FM_API_BASE, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise ValueError(data.get("message") or "Last.fm API error")
    return data

def _lastfm_api_sig(params, secret):
    if not secret:
        raise RuntimeError("LAST_FM_API_SECRET (or LAST_FM_SHARED_SECRET) is required")
    pieces = []
    for key in sorted(params.keys()):
        pieces.append(f"{key}{params[key]}")
    raw = "".join(pieces) + secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def _lastfm_get_signed(params):
    if not last_fm_api_key:
        raise RuntimeError("LAST_FM_API_KEY is required")
    if not last_fm_api_secret:
        raise RuntimeError("LAST_FM_API_SECRET is required")
    params = {**params, "api_key": last_fm_api_key}
    api_sig = _lastfm_api_sig(params, last_fm_api_secret)
    params = {**params, "api_sig": api_sig, "format": "json"}
    response = requests.get(LAST_FM_API_BASE, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise ValueError(data.get("message") or "Last.fm API error")
    return data

def _get_image_url(images, preferred_sizes):
    for size in preferred_sizes:
        for image in images:
            if image.get("size") == size and image.get("#text"):
                return image.get("#text")
    return ""

def _parse_registered_at(registered):
    if not isinstance(registered, dict):
        return None
    unixtime = registered.get("unixtime")
    if not unixtime:
        return None
    try:
        return datetime.fromtimestamp(int(unixtime), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None

def _album_key(artist_name, album_name):
    if not artist_name or not album_name:
        return None
    return f"{artist_name}::{album_name}".strip().lower()

def _unauthorized_response():
    return jsonify({
        "error": "unauthorized",
        "login_url": frontend_url,
    }), 401

def _require_authenticated_user():
    provider = session.get("provider")
    if not provider:
        if session.get("user_id"):
            provider = "spotify"
            session["provider"] = provider
        elif session.get("lastfm_username"):
            provider = "lastfm"
            session["provider"] = provider

    if provider == "spotify":
        user_id = session.get("user_id")
        if not user_id:
            return None, _unauthorized_response()
        if not get_valid_token(user_id):
            return None, _unauthorized_response()
        return {"provider": "spotify", "user_id": user_id}, None

    if provider == "lastfm":
        username = session.get("lastfm_username")
        if not username:
            return None, _unauthorized_response()
        if not _get_lastfm_session_key(username):
            return None, _unauthorized_response()
        return {"provider": "lastfm", "user_id": username, "lastfm_username": username}, None

    return None, _unauthorized_response()

def _get_primary_wall(owner_id, provider):
    resp = (
        supabase.table("walls")
        .select("wall_id, owner_id, title, created_at")
        .eq("owner_id", owner_id)
        .eq("provider", provider)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]

def _get_playthrough_user_id(spotify_user_id):
    resp = (
        supabase.table("users")
        .select("playthrough_user_id")
        .eq("user_id", spotify_user_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0].get("playthrough_user_id")

def _get_lastfm_playthrough_user_id(username):
    resp = (
        supabase.table("last_fm_users")
        .select("playthrough_user_id")
        .eq("lastfm_username", username)
        .limit(1)
        .execute()
    )
    if resp.data and resp.data[0].get("playthrough_user_id"):
        return resp.data[0].get("playthrough_user_id")

    playthrough_user_id = str(uuid.uuid4())
    supabase.table("last_fm_users").upsert({
        "lastfm_username": username,
        "playthrough_user_id": playthrough_user_id,
    }).execute()
    return playthrough_user_id

def _get_playthrough_user_id_for_provider(owner_id, provider):
    if provider == "spotify":
        return _get_playthrough_user_id(owner_id)
    if provider == "lastfm":
        return _get_lastfm_playthrough_user_id(owner_id)
    return None

def _get_lastfm_session_key(username):
    resp = (
        supabase.table("last_fm_users")
        .select("session_key_encrypted")
        .eq("lastfm_username", username)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0].get("session_key_encrypted")

def _get_or_create_primary_wall(owner_id, provider, title=None):
    wall = _get_primary_wall(owner_id, provider)
    if wall:
        return wall
    playthrough_user_id = _get_playthrough_user_id_for_provider(owner_id, provider)
    if not playthrough_user_id:
        print(f"Missing playthrough_user_id for owner_id {owner_id} provider={provider}")
        return None
    payload = {
        "owner_id": owner_id,
        "playthrough_user_id": playthrough_user_id,
        "provider": provider,
    }
    if title is not None:
        payload["title"] = title
    try:
        resp = supabase.table("walls").insert(payload).execute()
    except Exception as exc:
        print(f"Error creating wall for {owner_id}: {exc}")
        return None
    if not resp.data:
        return None
    return resp.data[0]

def _get_wall_by_id(wall_id, provider):
    resp = (
        supabase.table("walls")
        .select("wall_id, owner_id, title, created_at")
        .eq("wall_id", wall_id)
        .eq("provider", provider)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]

def _fetch_lastfm_album_meta(album_keys):
    if not album_keys:
        return {}
    resp = (
        supabase.table("last_fm_albums")
        .select("album_key, album_name, artist_name, image_large, image_extralarge, image_mega, total_tracks")
        .in_("album_key", album_keys)
        .execute()
    )
    meta = {}
    for row in resp.data or []:
        meta[row.get("album_key")] = row
    return meta

def _fetch_spotify_album_meta(album_ids):
    if not album_ids:
        return {}
    resp = (
        supabase.table("albums")
        .select(
            "album_id, album_name, artist_name, album_type, "
            "album_image, album_image_height, album_image_width, total_tracks"
        )
        .in_("album_id", album_ids)
        .execute()
    )
    meta = {}
    for row in resp.data or []:
        meta[row.get("album_id")] = row
    return meta

def _pick_lastfm_album_image(album):
    if not album:
        return None
    return (
        album.get("image_mega")
        or album.get("image_extralarge")
        or album.get("image_large")
    )

def _get_wall_items(wall_id, provider):
    if provider == "spotify":
        items_resp = (
            supabase.table("wall_items")
            .select("album_id, added_at")
            .eq("wall_id", wall_id)
            .eq("provider", provider)
            .order("added_at", desc=False)
            .order("album_id", desc=False)
            .execute()
        )

        album_ids = [row.get("album_id") for row in items_resp.data or [] if row.get("album_id")]
        album_meta = _fetch_spotify_album_meta(list(dict.fromkeys(album_ids)))
        items = []
        for row in items_resp.data or []:
            album = album_meta.get(row.get("album_id")) or {}
            items.append({
                "album_id": row.get("album_id"),
                "added_at": row.get("added_at"),
                "album_name": album.get("album_name"),
                "artist_name": album.get("artist_name"),
                "album_type": album.get("album_type"),
                "album_image": album.get("album_image"),
                "album_image_height": album.get("album_image_height"),
                "album_image_width": album.get("album_image_width"),
                "total_tracks": album.get("total_tracks"),
            })
        return items

    items_resp = (
        supabase.table("wall_items")
        .select("album_id, added_at")
        .eq("wall_id", wall_id)
        .eq("provider", provider)
        .order("added_at", desc=False)
        .order("album_id", desc=False)
        .execute()
    )

    album_keys = [row.get("album_id") for row in items_resp.data or [] if row.get("album_id")]
    album_meta = _fetch_lastfm_album_meta(list(dict.fromkeys(album_keys)))

    items = []
    for row in items_resp.data or []:
        album = album_meta.get(row.get("album_id")) or {}
        items.append({
            "album_id": row.get("album_id"),
            "added_at": row.get("added_at"),
            "album_name": album.get("album_name"),
            "artist_name": album.get("artist_name"),
            "album_type": "album",
            "album_image": _pick_lastfm_album_image(album),
            "album_image_height": None,
            "album_image_width": None,
            "total_tracks": album.get("total_tracks"),
        })
    return items

def _get_wall_items_for_walls(wall_ids, provider):
    if not wall_ids:
        return {}

    if provider == "spotify":
        items_resp = (
            supabase.table("wall_items")
            .select("wall_id, album_id, added_at")
            .in_("wall_id", wall_ids)
            .eq("provider", provider)
            .order("added_at", desc=False)
            .order("album_id", desc=False)
            .execute()
        )

        album_ids = [row.get("album_id") for row in items_resp.data or [] if row.get("album_id")]
        album_meta = _fetch_spotify_album_meta(list(dict.fromkeys(album_ids)))
        grouped = {wall_id: [] for wall_id in wall_ids}
        for row in items_resp.data or []:
            album = album_meta.get(row.get("album_id")) or {}
            grouped.setdefault(row.get("wall_id"), []).append({
                "album_id": row.get("album_id"),
                "added_at": row.get("added_at"),
                "album_name": album.get("album_name"),
                "artist_name": album.get("artist_name"),
                "album_type": album.get("album_type"),
                "album_image": album.get("album_image"),
                "album_image_height": album.get("album_image_height"),
                "album_image_width": album.get("album_image_width"),
                "total_tracks": album.get("total_tracks"),
            })
        return grouped

    items_resp = (
        supabase.table("wall_items")
        .select("wall_id, album_id, added_at")
        .in_("wall_id", wall_ids)
        .eq("provider", provider)
        .order("added_at", desc=False)
        .order("album_id", desc=False)
        .execute()
    )

    album_keys = [row.get("album_id") for row in items_resp.data or [] if row.get("album_id")]
    album_meta = _fetch_lastfm_album_meta(list(dict.fromkeys(album_keys)))

    grouped = {wall_id: [] for wall_id in wall_ids}
    for row in items_resp.data or []:
        album = album_meta.get(row.get("album_id")) or {}
        grouped.setdefault(row.get("wall_id"), []).append({
            "album_id": row.get("album_id"),
            "added_at": row.get("added_at"),
            "album_name": album.get("album_name"),
            "artist_name": album.get("artist_name"),
            "album_type": "album",
            "album_image": _pick_lastfm_album_image(album),
            "album_image_height": None,
            "album_image_width": None,
            "total_tracks": album.get("total_tracks"),
        })

    return grouped

def _build_shared_walls_response(user_id, provider):
    walls_resp = (
        supabase.table("walls")
        .select("wall_id, owner_id, title, created_at")
        .eq("provider", provider)
        .order("created_at", desc=False)
        .execute()
    )

    walls_data = walls_resp.data or []
    wall_ids = [wall.get("wall_id") for wall in walls_data if wall.get("wall_id")]
    items_by_wall = _get_wall_items_for_walls(wall_ids, provider)

    display_name_by_owner = {}
    owner_ids = [wall.get("owner_id") for wall in walls_data if wall.get("owner_id")]
    if owner_ids:
        if provider == "spotify":
            owner_resp = (
                supabase.table("users")
                .select("user_id, display_name")
                .in_("user_id", owner_ids)
                .execute()
            )
            for row in owner_resp.data or []:
                display_name_by_owner[row.get("user_id")] = row.get("display_name")
        else:
            owner_resp = (
                supabase.table("last_fm_users")
                .select("lastfm_username, display_name")
                .in_("lastfm_username", owner_ids)
                .execute()
            )
            for row in owner_resp.data or []:
                display_name_by_owner[row.get("lastfm_username")] = row.get("display_name")

    output = []
    for wall in walls_data:
        owner_display_name = display_name_by_owner.get(wall.get("owner_id"))

        output.append({
            "wall": {
                "wall_id": wall.get("wall_id"),
                "owner_id": wall.get("owner_id"),
                "owner_display_name": owner_display_name,
                "title": wall.get("title"),
                "created_at": wall.get("created_at"),
                "is_owner": wall.get("owner_id") == user_id,
            },
            "items": items_by_wall.get(wall.get("wall_id"), []),
        })

    return {"walls": output}

def _get_owner_display_name(owner_id, provider):
    if provider == "spotify":
        resp = (
            supabase.table("users")
            .select("user_id, display_name")
            .eq("user_id", owner_id)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        return resp.data[0].get("display_name")

    resp = (
        supabase.table("last_fm_users")
        .select("lastfm_username, display_name")
        .eq("lastfm_username", owner_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0].get("display_name")

def _upsert_lastfm_user_from_profile(username, session_key_encrypted=None):
    try:
        payload = _lastfm_get({"method": "user.getInfo", "user": username})
    except (requests.RequestException, ValueError, RuntimeError):
        return None, (jsonify({"error": "lastfm_unavailable"}), 502)

    if payload.get("error"):
        return None, (jsonify({
            "error": "user_not_found",
            "signup_url": LAST_FM_SIGNUP_URL,
        }), 404)

    user_info = payload.get("user", {})
    images = user_info.get("image", [])
    avatar_url = _get_image_url(images, ["extralarge", "large", "medium", "small"])
    resolved_username = user_info.get("name", username)
    playthrough_user_id = _get_lastfm_playthrough_user_id(resolved_username)

    update_payload = {
        "lastfm_username": resolved_username,
        "display_name": user_info.get("realname") or resolved_username,
        "profile_url": user_info.get("url"),
        "playcount": user_info.get("playcount"),
        "registered_at": _parse_registered_at(user_info.get("registered")),
        "country": user_info.get("country"),
        "avatar_url": avatar_url,
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "playthrough_user_id": playthrough_user_id,
    }
    if session_key_encrypted:
        update_payload["session_key_encrypted"] = session_key_encrypted
        update_payload["session_key_created_at"] = datetime.now(timezone.utc).isoformat()

    supabase.table("last_fm_users").upsert(update_payload).execute()

    return user_info, None

@app.route("/")
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    print("AUTH URL: " + auth_url)
    return redirect(auth_url)

@app.route("/api/auth/login", methods=["POST", "GET"])
def auth_login():
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or request.args.get("provider") or "").strip().lower()
    if provider not in {"spotify", "lastfm"}:
        return jsonify({"error": "provider_required"}), 400

    if provider == "spotify":
        sp_oauth = get_spotify_oauth()
        auth_url = sp_oauth.get_authorize_url()
        return jsonify({"login_url": auth_url})

    if not last_fm_api_key:
        return jsonify({"error": "lastfm_unavailable"}), 500
    if not last_fm_callback_url:
        return jsonify({"error": "lastfm_callback_required"}), 500

    state = uuid.uuid4().hex
    session["lastfm_state"] = state

    parsed = urlparse(last_fm_callback_url)
    query = dict(parse_qsl(parsed.query))
    query["state"] = state
    callback_with_state = urlunparse(parsed._replace(query=urlencode(query)))

    auth_url = (
        "https://www.last.fm/api/auth/?"
        + urlencode({"api_key": last_fm_api_key, "cb": callback_with_state})
    )
    return jsonify({"login_url": auth_url})

@app.route("/api/auth/callback")
def callback_page():
    code = request.args.get('code')
    sp_oauth = get_spotify_oauth()
    
    token_info = sp_oauth.get_access_token(code, check_cache=False)

    # Populate Users Table
    encrypted_access_token = cipher.encrypt(token_info['access_token'].encode()).decode()
    encrypted_refresh_token = cipher.encrypt(token_info['refresh_token'].encode()).decode()
    sp = spotipy.Spotify(auth=token_info['access_token'])
    user_data = sp.current_user()

    session['provider'] = "spotify"
    session['user_id'] = user_data['id']
    
    supabase.table('users').upsert({
        'user_id': user_data['id'],
        'display_name': user_data.get('display_name'),
        'access_token': encrypted_access_token, 
        'refresh_token': encrypted_refresh_token,
        'token_expires_at': token_info['expires_at']
    }).execute()

    return redirect(frontend_url)

@app.route("/api/auth/lastfm/callback")
def lastfm_callback():
    token = request.args.get("token", "").strip()
    state = request.args.get("state", "").strip()
    expected_state = session.get("lastfm_state")

    if expected_state and state != expected_state:
        return redirect(f"{frontend_url}/?auth=error")

    if not token:
        return redirect(f"{frontend_url}/?auth=error")

    try:
        payload = _lastfm_get_signed({
            "method": "auth.getSession",
            "token": token,
        })
    except (requests.RequestException, ValueError, RuntimeError):
        return redirect(f"{frontend_url}/?auth=error")

    session_info = payload.get("session", {})
    username = session_info.get("name")
    session_key = session_info.get("key")
    if not username or not session_key:
        return redirect(f"{frontend_url}/?auth=error")

    encrypted_session_key = cipher.encrypt(session_key.encode()).decode()
    _, error_response = _upsert_lastfm_user_from_profile(username, encrypted_session_key)
    if error_response:
        return redirect(f"{frontend_url}/?auth=error")

    session["provider"] = "lastfm"
    session["lastfm_username"] = username

    return redirect(f"{frontend_url}/wall?auth=success")

@app.route("/profile")
def profile():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response

    provider = context["provider"]
    if provider == "spotify":
        decrypted_token = get_valid_token(context.get("user_id"))
        if not decrypted_token:
            return _unauthorized_response()

        sp = spotipy.Spotify(auth=decrypted_token)
        user_data = sp.current_user()

        return jsonify({
            "provider": "spotify",
            "id": user_data.get("id"),
            "display_name": user_data.get("display_name"),
            "email": user_data.get("email"),
            "images": user_data.get("images", []),
            "followers": user_data.get("followers", {}).get("total", 0),
            "external_urls": user_data.get("external_urls", {}),
            "country": user_data.get("country"),
            "product": user_data.get("product"),  # free, premium, etc.
        })

    username = context.get("lastfm_username") or context.get("user_id")
    try:
        payload = _lastfm_get({"method": "user.getInfo", "user": username})
    except (requests.RequestException, ValueError, RuntimeError):
        return jsonify({"error": "lastfm_unavailable"}), 502

    user_info = payload.get("user", {})
    images = []
    for image in user_info.get("image", []):
        url = image.get("#text")
        if url:
            images.append({"url": url, "height": None, "width": None})

    return jsonify({
        "provider": "lastfm",
        "id": user_info.get("name", username),
        "display_name": user_info.get("realname") or user_info.get("name"),
        "images": images,
        "external_urls": {"lastfm": user_info.get("url")},
        "country": user_info.get("country"),
        "playcount": user_info.get("playcount"),
        "registered_at": user_info.get("registered", {}).get("#text"),
    })

@app.route("/recents")
def recently_listened():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response

    provider = context["provider"]
    if provider == "spotify":
        decrypted_token = get_valid_token(context.get("user_id"))
        if not decrypted_token:
            return _unauthorized_response()

        sp = spotipy.Spotify(auth=decrypted_token)
        one_hour_ago = int((time.time() - 1500) * 1000)
        recently_listened = sp.current_user_recently_played(limit=50, after=one_hour_ago)
        items = recently_listened["items"]
        recents = []
        for item in items:
            recents.append({
                "track_name": item["track"]["name"],
                "artists": [a["name"] for a in item["track"]["artists"]],
                "album_name": item["track"]["album"]["name"],
                "album_type": item["track"]["album"]["album_type"],
                "album_id": item["track"]["album"]["id"],
                "album_image": item["track"]["album"]["images"][0]["url"],
                "album_image_height": item["track"]["album"]["images"][0]["height"],
                "album_image_width": item["track"]["album"]["images"][0]["width"],
                "played_at": item["played_at"],
            })
        return jsonify(recents)

    username = context.get("lastfm_username") or context.get("user_id")
    one_hour_ago = int(time.time() - 3600)
    try:
        payload = _lastfm_get({
            "method": "user.getrecenttracks",
            "user": username,
            "from": one_hour_ago,
            "to": int(time.time()),
            "limit": 50,
        })
    except (requests.RequestException, ValueError, RuntimeError):
        return jsonify({"error": "lastfm_unavailable"}), 502

    items = payload.get("recenttracks", {}).get("track", [])
    if isinstance(items, dict):
        items = [items]

    recents = []
    for item in items:
        artist_name = item.get("artist", {}).get("#text", "")
        album_name = item.get("album", {}).get("#text", "")
        track_name = item.get("name", "")
        images = item.get("image", [])
        album_image = _get_image_url(images, ["mega", "extralarge", "large", "medium", "small"])
        played_at = item.get("date", {}).get("#text", "")
        album_key = _album_key(artist_name, album_name)

        recents.append({
            "track_name": track_name,
            "artists": [artist_name],
            "album_name": album_name,
            "album_type": "album",
            "album_id": album_key or "",
            "album_image": album_image,
            "album_image_height": None,
            "album_image_width": None,
            "played_at": played_at,
        })

    return jsonify(recents)

@app.route("/live")
def live_listening():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response

    provider = context["provider"]
    if provider == "spotify":
        decrypted_token = get_valid_token(context.get("user_id"))
        if not decrypted_token:
            return _unauthorized_response()

        sp = spotipy.Spotify(auth=decrypted_token)
        live_listened = sp.currently_playing()
        if not live_listened:
            return "Not listening to anything right now!"
        return live_listened

    username = context.get("lastfm_username") or context.get("user_id")
    try:
        payload = _lastfm_get({
            "method": "user.getrecenttracks",
            "user": username,
            "limit": 1,
        })
    except (requests.RequestException, ValueError, RuntimeError):
        return jsonify({"error": "lastfm_unavailable"}), 502

    items = payload.get("recenttracks", {}).get("track", [])
    if isinstance(items, dict):
        items = [items]

    if not items:
        return "Not listening to anything right now!"

    first = items[0]
    nowplaying = first.get("@attr", {}).get("nowplaying") == "true"
    if not nowplaying:
        return "Not listening to anything right now!"

    return first

@app.route("/tracking")
def album_tracker():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response

    provider = context["provider"]
    filter_value = request.args.get("filter")

    if provider == "spotify":
        if filter_value == "unfinished":
            albums = get_albums_completion_sorted(context["user_id"])
        else:
            albums = get_albums_completion(context["user_id"])
        return jsonify(albums)

    username = context.get("lastfm_username") or context.get("user_id")
    try:
        albums = get_lastfm_albums_completion(username)
    except Exception:
        app.logger.exception("Failed to fetch Last.fm album completion for %s", username)
        return jsonify({"error": "tracking_unavailable"}), 502
    album_keys = [album.get("album_key") for album in albums if album.get("album_key")]
    album_meta = _fetch_lastfm_album_meta(list(dict.fromkeys(album_keys)))

    output = []
    for album in albums:
        meta = album_meta.get(album.get("album_key")) if album_meta else None
        output.append({
            "album_id": album.get("album_key"),
            "album_name": album.get("album_name"),
            "artist": album.get("artist"),
            "listened": album.get("listened"),
            "total": album.get("total"),
            "percentage": album.get("percentage"),
            "album_image": _pick_lastfm_album_image(meta) or album.get("album_image"),
        })

    if filter_value == "unfinished":
        output = [entry for entry in output if (entry.get("percentage") or 0) < 1.0]
        output = sorted(output, key=lambda album: album.get("percentage") or 0, reverse=True)

    return jsonify(output)

@app.route("/album-tracks")
def album_tracks():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response

    provider = context["provider"]
    album_id = request.args.get("album_id") or request.args.get("album_key")
    if not album_id:
        return jsonify({
            "error": "album_id is required"
        }), 400

    if provider == "spotify":
        tracks = get_album_tracks(context["user_id"], album_id)
        return jsonify(tracks)

    username = context.get("lastfm_username") or context.get("user_id")
    try:
        tracks = get_lastfm_album_tracks(username, album_id)
    except Exception:
        app.logger.exception("Failed to fetch Last.fm tracks for %s", album_id)
        return jsonify({"error": "tracks_unavailable"}), 502
    return jsonify(tracks)

@app.route("/api/walls", methods=["GET"])
def get_wall():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response
    provider = context["provider"]
    user_id = context["user_id"]

    if request.args.get("all") in {"1", "true", "yes"} or request.args.get("scope") == "all":
        return jsonify(_build_shared_walls_response(user_id, provider))

    wall_id = request.args.get("wall_id")
    target_user_id = request.args.get("user_id") or user_id

    wall = None
    if wall_id:
        wall = _get_wall_by_id(wall_id, provider)
    else:
        wall = _get_primary_wall(target_user_id, provider)

    if not wall:
        return jsonify({"wall": None, "items": []}), 200

    owner_display_name = _get_owner_display_name(wall["owner_id"], provider)
    items = _get_wall_items(wall["wall_id"], provider)

    return jsonify({
        "wall": {
            "wall_id": wall["wall_id"],
            "owner_id": wall["owner_id"],
            "owner_display_name": owner_display_name,
            "title": wall.get("title"),
            "created_at": wall.get("created_at"),
        },
        "items": items,
    })

@app.route("/api/shared-walls", methods=["GET"])
@app.route("/api/shared_walls", methods=["GET"])
def get_shared_walls():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response
    return jsonify(_build_shared_walls_response(context["user_id"], context["provider"]))

@app.route("/api/walls/items", methods=["POST"])
def add_wall_item():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response
    provider = context["provider"]
    user_id = context["user_id"]

    data = request.get_json(silent=True) or {}
    album_ids = data.get("album_ids")
    album_id = data.get("album_id") or request.args.get("album_id")
    if album_ids is not None:
        if not isinstance(album_ids, list):
            return jsonify({"error": "album_ids must be a list"}), 400
        album_ids = [entry for entry in album_ids if entry]
        album_ids = list(dict.fromkeys(album_ids))
        if not album_ids:
            return jsonify({"error": "album_ids is required"}), 400
    elif not album_id:
        return jsonify({"error": "album_id is required"}), 400

    wall_id = data.get("wall_id")
    if wall_id:
        wall = _get_wall_by_id(wall_id, provider)
        if not wall:
            return jsonify({"error": "wall not found"}), 404
        if wall["owner_id"] != user_id:
            return jsonify({"error": "forbidden"}), 403
    else:
        wall = _get_or_create_primary_wall(user_id, provider)

    if not wall:
        return jsonify({"error": "unable to create wall"}), 500

    try:
        if album_ids is not None:
            payload = [
                {"wall_id": wall["wall_id"], "album_id": entry, "provider": provider}
                for entry in album_ids
            ]
        else:
            payload = {
                "wall_id": wall["wall_id"],
                "album_id": album_id,
                "provider": provider,
            }
        resp = supabase.table("wall_items").upsert(payload).execute()
    except Exception as exc:
        print(f"Error adding wall item(s) to {wall['wall_id']}: {exc}")
        return jsonify({
            "error": "failed to add wall item",
            "detail": str(exc),
        }), 500

    return jsonify({
        "message": "added",
        "wall_id": wall["wall_id"],
        "album_id": album_id,
        "album_ids": album_ids,
    }), 200

@app.route("/api/walls/items", methods=["DELETE"])
def remove_wall_item():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response
    provider = context["provider"]
    user_id = context["user_id"]

    data = request.get_json(silent=True) or {}
    wall_id = request.args.get("wall_id") or data.get("wall_id")
    if wall_id:
        wall = _get_wall_by_id(wall_id, provider)
        if not wall:
            return jsonify({"error": "wall not found"}), 404
        if wall["owner_id"] != user_id:
            return jsonify({"error": "forbidden"}), 403
    else:
        wall = _get_primary_wall(user_id, provider)

    if not wall:
        return jsonify({"error": "wall not found"}), 404

    album_id = request.args.get("album_id") or data.get("album_id")
    delete_query = (
        supabase.table("wall_items")
        .delete()
        .eq("wall_id", wall["wall_id"])
        .eq("provider", provider)
    )
    if album_id:
        delete_query = delete_query.eq("album_id", album_id)

    delete_query.execute()

    return jsonify({
        "message": "removed" if album_id else "cleared",
        "wall_id": wall["wall_id"],
        "album_id": album_id,
    }), 200

@app.route("/api/walls", methods=["PATCH"])
def update_wall():
    context, error_response = _require_authenticated_user()
    if error_response:
        return error_response
    provider = context["provider"]
    user_id = context["user_id"]

    data = request.get_json(silent=True) or {}
    title = data.get("title")
    if title is None:
        return jsonify({"error": "title is required"}), 400

    wall_id = data.get("wall_id") or request.args.get("wall_id")
    if wall_id:
        wall = _get_wall_by_id(wall_id, provider)
        if not wall:
            return jsonify({"error": "wall not found"}), 404
        if wall["owner_id"] != user_id:
            return jsonify({"error": "forbidden"}), 403
    else:
        wall = _get_or_create_primary_wall(user_id, provider)

    if not wall:
        return jsonify({"error": "unable to create wall"}), 500

    supabase.table("walls")\
        .update({"title": title})\
        .eq("wall_id", wall["wall_id"])\
        .eq("provider", provider)\
        .execute()

    return jsonify({
        "message": "updated",
        "wall_id": wall["wall_id"],
        "title": title,
    }), 200

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route("/health")
def health_check():
    return jsonify({"status": "ok"}), 200

    

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    app.run(host=host, port=port)
