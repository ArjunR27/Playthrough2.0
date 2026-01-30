import base64
import os
import time
from urllib.parse import urlparse

import spotipy
from cryptography.fernet import Fernet
from env import load_environment
from flask import Flask, jsonify, redirect, request, session, url_for
from supabase import create_client, Client
from flask_cors import CORS

from album_tracking import get_albums_completion, get_album_tracks
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

def _extract_origin_host(origin):
    origin = origin.strip()
    if not origin:
        return ""
    if origin == "*":
        return "*"
    if "://" not in origin:
        origin = f"https://{origin}"
    parsed = urlparse(origin)
    return parsed.netloc.lower()

def _allowed_redirect_hosts():
    allowed = set()
    raw = os.getenv("CORS_ORIGINS")
    if raw:
        for origin in raw.split(","):
            host = _extract_origin_host(origin)
            if host:
                allowed.add(host)
    frontend = os.getenv("FRONTEND_URL")
    if frontend:
        host = _extract_origin_host(frontend)
        if host:
            allowed.add(host)
    return allowed

def _sanitize_return_to(return_to):
    if not return_to:
        return None
    try:
        parsed = urlparse(return_to)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    allowed = _allowed_redirect_hosts()
    if "*" in allowed:
        return return_to
    if parsed.netloc.lower() not in allowed:
        return None
    return return_to

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

def _require_authenticated_user():
    user_id = session.get("user_id")
    if not user_id:
        return None, (jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401)

    if not get_valid_token(user_id):
        return None, (jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401)

    return user_id, None

def _get_primary_wall(owner_id):
    resp = (
        supabase.table("walls")
        .select("wall_id, owner_id, title, created_at")
        .eq("owner_id", owner_id)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]

def _get_or_create_primary_wall(owner_id, title=None):
    wall = _get_primary_wall(owner_id)
    if wall:
        return wall
    payload = {"owner_id": owner_id}
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

def _get_wall_by_id(wall_id):
    resp = (
        supabase.table("walls")
        .select("wall_id, owner_id, title, created_at")
        .eq("wall_id", wall_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]

def _get_wall_items(wall_id):
    items_resp = (
        supabase.table("wall_items")
        .select(
            "album_id, added_at, "
            "albums(album_id, album_name, artist_name, album_type, "
            "album_image, album_image_height, album_image_width, total_tracks)"
        )
        .eq("wall_id", wall_id)
        .order("added_at", desc=False)
        .execute()
    )

    items = []
    for row in items_resp.data or []:
        album = row.get("albums") or {}
        if isinstance(album, list):
            album = album[0] if album else {}
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

def _get_wall_items_for_walls(wall_ids):
    if not wall_ids:
        return {}

    items_resp = (
        supabase.table("wall_items")
        .select(
            "wall_id, album_id, added_at, "
            "albums(album_id, album_name, artist_name, album_type, "
            "album_image, album_image_height, album_image_width, total_tracks)"
        )
        .in_("wall_id", wall_ids)
        .order("added_at", desc=False)
        .execute()
    )

    grouped = {wall_id: [] for wall_id in wall_ids}
    for row in items_resp.data or []:
        album = row.get("albums") or {}
        if isinstance(album, list):
            album = album[0] if album else {}
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

def _build_shared_walls_response(user_id):
    walls_resp = (
        supabase.table("walls")
        .select("wall_id, owner_id, title, created_at, users(display_name)")
        .order("created_at", desc=False)
        .execute()
    )

    walls_data = walls_resp.data or []
    wall_ids = [wall.get("wall_id") for wall in walls_data if wall.get("wall_id")]
    items_by_wall = _get_wall_items_for_walls(wall_ids)

    output = []
    for wall in walls_data:
        owner_meta = wall.get("users") or {}
        if isinstance(owner_meta, list):
            owner_meta = owner_meta[0] if owner_meta else {}
        output.append({
            "wall": {
                "wall_id": wall.get("wall_id"),
                "owner_id": wall.get("owner_id"),
                "owner_display_name": owner_meta.get("display_name"),
                "title": wall.get("title"),
                "created_at": wall.get("created_at"),
                "is_owner": wall.get("owner_id") == user_id,
            },
            "items": items_by_wall.get(wall.get("wall_id"), []),
        })

    return {"walls": output}

def _get_owner_display_name(owner_id):
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

@app.route("/")
def login():
    sp_oauth = get_spotify_oauth()
    raw_return_to = request.args.get("return_to")
    safe_return_to = _sanitize_return_to(raw_return_to)
    auth_url = sp_oauth.get_authorize_url(state=safe_return_to or "")
    print("AUTH URL: " + auth_url)
    return redirect(auth_url)

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

    session['user_id'] = user_data['id']
    
    supabase.table('users').upsert({
        'user_id': user_data['id'],
        'display_name': user_data.get('display_name'),
        'access_token': encrypted_access_token, 
        'refresh_token': encrypted_refresh_token,
        'token_expires_at': token_info['expires_at']
    }).execute()

    state = request.args.get("state") or ""
    safe_return_to = _sanitize_return_to(state)
    return redirect(safe_return_to or frontend_url)

@app.route("/profile")
def profile():
    decrypted_token = get_valid_token(session.get('user_id'))
    if not decrypted_token:
        return jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401
    
    sp = spotipy.Spotify(auth=decrypted_token)
    user_data = sp.current_user()

    return jsonify({
        "id": user_data.get("id"),
        "display_name": user_data.get("display_name"),
        "email": user_data.get("email"),
        "images": user_data.get("images", []),
        "followers": user_data.get("followers", {}).get("total", 0),
        "external_urls": user_data.get("external_urls", {}),
        "country": user_data.get("country"),
        "product": user_data.get("product"),  # free, premium, etc.
    })

@app.route("/recents")
def recently_listened():
    decrypted_token = get_valid_token(session.get('user_id'))
    if not decrypted_token:
        return jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401

    sp = spotipy.Spotify(auth=decrypted_token)
    one_hour_ago = int((time.time() - 3600) * 1000)
    recently_listened = sp.current_user_recently_played(limit=50, after=one_hour_ago)
    items = recently_listened["items"] 
    recents = []
    for item in items:
        recents.append({
            'track_name': item["track"]["name"],
            'artists' : [a["name"] for a in item["track"]["artists"]],
            'album_name': item['track']['album']['name'],
            "album_type": item['track']['album']['album_type'],
            'album_id': item["track"]["album"]["id"],
            "album_image": item["track"]["album"]["images"][0]["url"],
            "album_image_height": item["track"]["album"]["images"][0]["height"],
            "album_image_width": item["track"]["album"]["images"][0]["width"],
            "played_at": item['played_at']
        })

    return jsonify(recents)

@app.route("/live")
def live_listening():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    decrypted_token = get_valid_token(user_id)
    if not decrypted_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=decrypted_token)
    live_listened = sp.currently_playing()
    if not live_listened:
        return f"Not listening to anything right now!"
    return live_listened

@app.route("/tracking")
def album_tracker():
    decrypted_token = get_valid_token(session.get('user_id'))
    if not decrypted_token:
        return jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401
    
    albums = get_albums_completion(session['user_id'])
    return jsonify(albums)

@app.route("/album-tracks")
def album_tracks():
    decrypted_token = get_valid_token(session.get('user_id'))
    if not decrypted_token:
        return jsonify({
            "error": "unauthorized",
            "login_url": url_for("login", _external=True),
        }), 401
    
    album_id = request.args.get('album_id')
    if not album_id:
        return jsonify({
            "error": "album_id is required"
        }), 400
    
    tracks = get_album_tracks(session['user_id'], album_id)
    return jsonify(tracks)

@app.route("/api/walls", methods=["GET"])
def get_wall():
    user_id, error = _require_authenticated_user()
    if error:
        return error

    if request.args.get("all") in {"1", "true", "yes"} or request.args.get("scope") == "all":
        return jsonify(_build_shared_walls_response(user_id))

    wall_id = request.args.get("wall_id")
    target_user_id = request.args.get("user_id") or user_id

    wall = None
    if wall_id:
        wall = _get_wall_by_id(wall_id)
    else:
        wall = _get_primary_wall(target_user_id)

    if not wall:
        return jsonify({"wall": None, "items": []}), 200

    owner_display_name = _get_owner_display_name(wall["owner_id"])
    items = _get_wall_items(wall["wall_id"])

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
    user_id, error = _require_authenticated_user()
    if error:
        return error
    return jsonify(_build_shared_walls_response(user_id))

@app.route("/api/walls/items", methods=["POST"])
def add_wall_item():
    user_id, error = _require_authenticated_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    album_id = data.get("album_id") or request.args.get("album_id")
    if not album_id:
        return jsonify({"error": "album_id is required"}), 400

    wall_id = data.get("wall_id")
    if wall_id:
        wall = _get_wall_by_id(wall_id)
        if not wall:
            return jsonify({"error": "wall not found"}), 404
        if wall["owner_id"] != user_id:
            return jsonify({"error": "forbidden"}), 403
    else:
        wall = _get_or_create_primary_wall(user_id)

    if not wall:
        return jsonify({"error": "unable to create wall"}), 500

    try:
        resp = supabase.table("wall_items").upsert({
            "wall_id": wall["wall_id"],
            "album_id": album_id,
        }).execute()
    except Exception as exc:
        print(f"Error adding wall item {album_id} to {wall['wall_id']}: {exc}")
        return jsonify({
            "error": "failed to add wall item",
            "detail": str(exc),
        }), 500

    return jsonify({
        "message": "added",
        "wall_id": wall["wall_id"],
        "album_id": album_id,
    }), 200

@app.route("/api/walls/items", methods=["DELETE"])
def remove_wall_item():
    user_id, error = _require_authenticated_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    wall_id = request.args.get("wall_id") or data.get("wall_id")
    if wall_id:
        wall = _get_wall_by_id(wall_id)
        if not wall:
            return jsonify({"error": "wall not found"}), 404
        if wall["owner_id"] != user_id:
            return jsonify({"error": "forbidden"}), 403
    else:
        wall = _get_primary_wall(user_id)

    if not wall:
        return jsonify({"error": "wall not found"}), 404

    album_id = request.args.get("album_id") or data.get("album_id")
    delete_query = (
        supabase.table("wall_items")
        .delete()
        .eq("wall_id", wall["wall_id"])
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
    user_id, error = _require_authenticated_user()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    title = data.get("title")
    if title is None:
        return jsonify({"error": "title is required"}), 400

    wall_id = data.get("wall_id") or request.args.get("wall_id")
    if wall_id:
        wall = _get_wall_by_id(wall_id)
        if not wall:
            return jsonify({"error": "wall not found"}), 404
        if wall["owner_id"] != user_id:
            return jsonify({"error": "forbidden"}), 403
    else:
        wall = _get_or_create_primary_wall(user_id)

    if not wall:
        return jsonify({"error": "unable to create wall"}), 500

    supabase.table("walls")\
        .update({"title": title})\
        .eq("wall_id", wall["wall_id"])\
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
