import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import base64
from auth import *
from urllib.parse import urlparse, parse_qs
import json

load_dotenv()

SPOTIFY_API_BASE = "https://api.spotify.com/v1"

def get_access_token(client_id, client_secret):
    token_url = "https://accounts.spotify.com/api/token"
    client_creds = f"{client_id}:{client_secret}"
    client_creds_b64 = base64.b64encode(client_creds.encode()).decode()

    headers = {
        "Authorization": f"Basic {client_creds_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials"
    }

    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()

    token_info = response.json()
    return token_info["access_token"]

def get_album(access_token):
    url = f"{SPOTIFY_API_BASE}/albums/4aawyAB9vmqN3uQ7FjRGTy"
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    return response.json()

def get_recently_played(access_token):
    url = f"{SPOTIFY_API_BASE}/me/player/recently-played"
    time_now_utc = datetime.now(timezone.utc)
    previous_day = (time_now_utc - timedelta(hours=24)).timestamp()
    unix_timestamp = int(previous_day)
    
    print(unix_timestamp)
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = requests.get(url, headers=headers, params={"after": unix_timestamp})
    with open("recently_played.json", "w") as json_file:
        json.dump(response.json(), json_file, indent=4)
    return response.json()


def main():
    ## Getting credentials
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    access_token = get_access_token(client_id, client_secret)
    url = get_auth_url(client_id, redirect_uri)
    print(url)

    redirect_response = input("Paste redirect url here: ").strip()

    code = parse_qs(urlparse(redirect_response).query)['code'][0]

    access_token_oauth = get_user_access_token(client_id, client_secret, code, redirect_uri)
    print(get_recently_played(access_token_oauth))


if __name__ == "__main__":
    main()


