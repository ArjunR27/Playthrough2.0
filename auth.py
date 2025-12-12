from dotenv import load_dotenv
from urllib.parse import urlencode
import base64
import requests

load_dotenv()

def get_auth_url(client_id, redirect_uri):
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "user-read-recently-played user-read-playback-state"
    }

    auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
    return auth_url

def get_user_access_token(client_id, client_secret, code, redirect_uri):
    token_url = "https://accounts.spotify.com/api/token"
    client_creds = f"{client_id}:{client_secret}"
    client_creds_b64 = base64.b64encode(client_creds.encode()).decode()
    headers = {
        "Authorization": f"Basic {client_creds_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    

    response = requests.post(token_url, headers=headers, data=data)

    print("Status Code:", response.status_code)
    print("Response:", response.json())
    
    response.raise_for_status()
    return response.json()["access_token"]

