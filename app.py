import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from flask import Flask, request, url_for, redirect, render_template
from cryptography.fernet import Fernet
import os
import base64
import time
from supabase import create_client, Client

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = base64.b64decode(os.getenv("FLASK_SECRET_KEY"))
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
encryption_key = os.getenv("ENCRYPTION_KEY_DEV")
cipher = Fernet(encryption_key.encode())

USER_DATA = {}

def get_spotify_oauth():
    sp_oauth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="user-read-recently-played user-read-playback-state",
        cache_path=None
        )
    return sp_oauth

def get_valid_token(user_id):
    response = supabase.table('users').select("access_token", "refresh_token", "token_expires_at").eq("user_id", user_id).execute()
    if not response.data:
        return None
    
    data = response.data[0]
    decrypted_access_token = cipher.decrypt(data['access_token'].encode()).decode()
    decrypted_refresh_token = cipher.decrypt(data['refresh_token'].encode()).decode()
    token_expires_at = data['token_expires_at']

    if time.time() > (token_expires_at - 60):
        sp_oauth = get_spotify_oauth()

        token_info = {
            'access_token': decrypted_access_token,
            'refresh_token': decrypted_refresh_token,
            'expires_at': token_expires_at
        }

        new_token_info = sp_oauth.refresh_access_token(decrypted_refresh_token)

        encrypted_access_token = cipher.encrypt(new_token_info['access_token'].encode()).decode()
        encrypted_refresh_token = cipher.encrypt(new_token_info['refresh_token'].encode()).decode()

        supabase.table('users').update({
            'access_token': encrypted_access_token,
            'refresh_token': encrypted_refresh_token,
            'token_expires_at': new_token_info['expires_at']
        }).eq("user_id", USER_DATA['id']).execute()

        return new_token_info['access_token']

    return decrypted_access_token

@app.route("/")
def login():
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    print("AUTH URL: " + auth_url)
    return redirect(auth_url)

@app.route("/api/auth/callback")
def callback_page():
    global USER_DATA
    code = request.args.get('code')
    sp_oauth = get_spotify_oauth()
    
    token_info = sp_oauth.get_access_token(code)

    # Populate Users Table
    encrypted_access_token = cipher.encrypt(token_info['access_token'].encode()).decode()
    encrypted_refresh_token = cipher.encrypt(token_info['refresh_token'].encode()).decode()
    sp = spotipy.Spotify(auth=token_info['access_token'])
    USER_DATA = sp.current_user()
    
    supabase.table('users').upsert({
        'user_id': USER_DATA['id'],
        'display_name': USER_DATA.get('display_name'),
        'access_token': encrypted_access_token, 
        'refresh_token': encrypted_refresh_token,
        'token_expires_at': token_info['expires_at']
    }).execute()

    return redirect(url_for('profile'))  

@app.route("/profile")
def profile():
    decrypted_token = get_valid_token(USER_DATA['id'])
    if not decrypted_token:
        return redirect(url_for('login'))
    
    sp = spotipy.Spotify(auth=decrypted_token)
    user_data = sp.current_user()

    return f"Hello {user_data['display_name']}. You are authorized!"

@app.route("/recents")
def recently_listened():
    decrypted_token = get_valid_token(USER_DATA['id'])
    if not decrypted_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=decrypted_token)
    recently_listened = sp.current_user_recently_played(limit=50)
    items = recently_listened["items"] 

    recent = ""
    for item in items:
        track_name = item["track"]["name"]
        artists = item["track"]["artists"]
        album = item["track"]["album"]
        if album["album_type"] == "album":
            artist_names = ""
            for artist in artists:
                artist_names += artist["name"] + ", "
            
            recent += f"Album: {album["name"]}, Artist: {artist_names}, Track: {track_name}, <br>"
    return recent

@app.route("/live")
def live_listening():
    decrypted_token = get_valid_token(USER_DATA['id'])
    if not decrypted_token:
        return redirect(url_for('login'))

    sp = spotipy.Spotify(auth=decrypted_token)
    live_listened = sp.currently_playing()
    if not live_listened:
        return f"Not listening to anything right now!"
    
    return live_listened

    

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=3000, debug=True)