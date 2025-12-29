import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from flask import Flask, request, url_for, redirect, render_template, session
from cryptography.fernet import Fernet
import os
import base64
import time
from supabase import create_client, Client
from album_tracking import *
from validate_token import *

load_dotenv()
app = Flask(__name__)
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
    
    token_info = sp_oauth.get_access_token(code)

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

    return redirect(url_for('profile'))  

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
        return redirect(url_for('login'))

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

    

if __name__ == "__main__":
    app.run(host='127.0.0.1', port=3000, debug=True)