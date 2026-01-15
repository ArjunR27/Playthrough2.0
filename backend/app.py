import base64
import os
import time

import spotipy
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, session, url_for
from supabase import create_client, Client
from flask_cors import CORS

from backend.album_tracking import get_albums_completion
from backend.validate_token import get_spotify_oauth, get_valid_token
load_dotenv()
app = Flask(__name__)
CORS(app, origins='http://127.0.0.1:8080', supports_credentials=True)
app.config["SECRET_KEY"] = base64.b64decode(os.getenv("FLASK_SECRET_KEY"))

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
encryption_key = os.getenv("ENCRYPTION_KEY_DEV")
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

    return redirect('http://127.0.0.1:8080')

@app.route("/profile")
def profile():
    decrypted_token = get_valid_token(session.get('user_id'))
    if not decrypted_token:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=decrypted_token)
    user_data = sp.current_user()

    return f"Hello {user_data['display_name']}. You are authorized!"

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
    decrypted_token = get_valid_token(session['user_id'])
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

    

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=3000, debug=True)
