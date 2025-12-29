import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import os
import time
from supabase import create_client, Client
from flask import session

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
encryption_key = os.getenv("ENCRYPTION_KEY_DEV")
cipher = Fernet(encryption_key.encode())

def get_spotify_oauth():
    sp_oauth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope="user-read-recently-played user-read-playback-state",
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
        }).eq("user_id", user_id).execute()

        return new_token_info['access_token']

    return decrypted_access_token