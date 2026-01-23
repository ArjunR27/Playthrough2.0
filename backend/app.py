import base64
import os
import time

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

@app.route("/")
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
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

    return redirect(frontend_url)

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
