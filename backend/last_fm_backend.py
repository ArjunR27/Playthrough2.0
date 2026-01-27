import base64
import os
import time
from datetime import datetime, timezone

import requests
from env import load_environment
from flask import Flask, jsonify, redirect, request, session, url_for
from flask_cors import CORS
from supabase import Client, create_client

from last_fm_album_tracking import get_albums_completion, get_album_tracks

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

last_fm_api_key = os.getenv("LAST_FM_API_KEY")
if not last_fm_api_key:
    raise RuntimeError("LAST_FM_API_KEY is required")

LAST_FM_API_BASE = "https://ws.audioscrobbler.com/2.0/"
LAST_FM_SIGNUP_URL = "https://www.last.fm/join"


def _lastfm_get(params):
    params = {**params, "api_key": last_fm_api_key, "format": "json"}
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


def _handle_username_login(username):
    try:
        payload = _lastfm_get({"method": "user.getInfo", "user": username})
    except (requests.RequestException, ValueError):
        return jsonify({"error": "lastfm_unavailable"}), 502

    if payload.get("error"):
        return jsonify({
            "error": "user_not_found",
            "signup_url": LAST_FM_SIGNUP_URL,
        }), 404

    user_info = payload.get("user", {})
    images = user_info.get("image", [])
    avatar_url = _get_image_url(images, ["extralarge", "large", "medium", "small"])

    supabase.table("last_fm_users").upsert({
        "lastfm_username": user_info.get("name", username),
        "display_name": user_info.get("realname") or user_info.get("name"),
        "profile_url": user_info.get("url"),
        "playcount": user_info.get("playcount"),
        "registered_at": _parse_registered_at(user_info.get("registered")),
        "country": user_info.get("country"),
        "avatar_url": avatar_url,
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    session["lastfm_username"] = user_info.get("name", username)
    return redirect(url_for("recently_listened", _external=True))


def _get_session_username():
    username = session.get("lastfm_username")
    if not username:
        return None, (jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401)
    return username, None


@app.route("/")
def login():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({
            "error": "username_required",
            "signup_url": LAST_FM_SIGNUP_URL,
        }), 400
    return _handle_username_login(username)


@app.route("/api/auth/callback")
def callback_page():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({
            "error": "username_required",
            "signup_url": LAST_FM_SIGNUP_URL,
        }), 400
    return _handle_username_login(username)


@app.route("/auth/lastfm")
def lastfm_auth():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({
            "error": "username_required",
            "signup_url": LAST_FM_SIGNUP_URL,
        }), 400
    try:
        payload = _lastfm_get({"method": "user.getInfo", "user": username})
    except (requests.RequestException, ValueError):
        return jsonify({"error": "lastfm_unavailable"}), 502
    if payload.get("error"):
        return jsonify({
            "error": "user_not_found",
            "signup_url": LAST_FM_SIGNUP_URL,
        }), 404
    user_info = payload.get("user", {})
    return jsonify({
        "status": "ok",
        "username": user_info.get("name", username),
        "profile_url": user_info.get("url"),
        "playcount": user_info.get("playcount"),
    })


@app.route("/profile")
def profile():
    username, error_response = _get_session_username()
    if error_response:
        return error_response

    try:
        payload = _lastfm_get({"method": "user.getInfo", "user": username})
    except (requests.RequestException, ValueError):
        return jsonify({"error": "lastfm_unavailable"}), 502

    user_info = payload.get("user", {})
    return jsonify({
        "username": user_info.get("name", username),
        "display_name": user_info.get("realname") or user_info.get("name"),
        "profile_url": user_info.get("url"),
        "playcount": user_info.get("playcount"),
        "country": user_info.get("country"),
        "images": user_info.get("image", []),
        "registered_at": user_info.get("registered", {}).get("#text"),
    })


@app.route("/recents")
def recently_listened():
    username, error_response = _get_session_username()
    if error_response:
        return error_response

    one_hour_ago = int(time.time() - 3600)
    try:
        payload = _lastfm_get({
            "method": "user.getrecenttracks",
            "user": username,
            "from": one_hour_ago,
            "to": int(time.time()),
            "limit": 50,
        })
    except (requests.RequestException, ValueError):
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
        album_image = _get_image_url(images, ["extralarge", "large", "medium", "small"])
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
    username, error_response = _get_session_username()
    if error_response:
        return error_response

    try:
        payload = _lastfm_get({
            "method": "user.getrecenttracks",
            "user": username,
            "limit": 1,
        })
    except (requests.RequestException, ValueError):
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
    username, error_response = _get_session_username()
    if error_response:
        return error_response

    albums = get_albums_completion(username)
    return jsonify(albums)


@app.route("/album-tracks")
def album_tracks():
    username, error_response = _get_session_username()
    if error_response:
        return error_response

    album_key = request.args.get("album_key") or request.args.get("album_id")
    if not album_key:
        return jsonify({
            "error": "album_key is required",
        }), 400

    tracks = get_album_tracks(username, album_key)
    return jsonify(tracks)


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
