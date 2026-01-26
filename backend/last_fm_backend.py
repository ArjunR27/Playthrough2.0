import base64
import os
import time
from cryptography.fernet import Fernet
from env import load_environment
from flask import Flask, jsonify, redirect, request, session, url_for
from supabase import create_client, Client
from flask_cors import CORS

import requests
import json
import string
import hashlib

load_environment()
app = Flask(__name__)
secret_key_b64 = os.getenv("FLASK_SECRET_KEY")
if not secret_key_b64:
    raise RuntimeError("FLASK_SECRET_KEY is required")

app.config["SECRET_KEY"] = base64.b64decode(secret_key_b64)
last_fm_api_key = os.getenv("LAST_FM_API_KEY")
user = "taper27"

recently_listened_template = string.Template(
    "http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks"
    "&user=$user"
    "&api_key=$last_fm_api_key"
    "&from=$from_time"
    "&to=$to_time"
    "&format=json"
)

@app.route("/")
def index():
    return "OK"

@app.route("/recents")
def recently_listened():
    one_hour_ago = int(time.time() - 3600)
    recently_listened = recently_listened_template.substitute(
    user=user,
    last_fm_api_key=last_fm_api_key,
    from_time=one_hour_ago,              # seconds since epoch (Last.fm expects seconds)
    to_time=int(time.time()),            # seconds, not ms
    )
    response = requests.get(recently_listened)
    payload = response.json()
    pretty_json_string = json.dumps(payload, indent=4)
    items = payload.get("recenttracks", {}).get("track", [])
    if isinstance(items, dict):
        items = [items]
    recents = []
    for item in items:
        artist_name = item.get("artist", {}).get("#text", "")
        album_name = item.get("album", {}).get("#text", ""),
        track_name = item.get("name", "")
        images = item.get("image", [])
        medium_image = ""
        fallback_image = ""
        for image in images:
            if image.get("size") == "medium":
                medium_image = image.get("#text", "")
            if image.get("size") == "large":
                fallback_image = image.get("#text", "")
        if not medium_image:
            medium_image = fallback_image
        album_id = item.get("album", {}).get("mbid", "")
        # if the album is really niche lol
        if not album_id:
            surrogate_source = f"{artist_name}::{album_name}".lower().strip()
            surrogate_id = hashlib.sha256(surrogate_source.encode("utf-8")).hexdigest()
            album_id = surrogate_id
        recents.append({
            "track_name": track_name,
            "artists": [artist_name],
            "album_name": album_name,
            "album_type": "album",
            "album_id": album_id,
            "album_image": medium_image,
            "album_image_height": 640,
            "album_image_width": 640,
            "played_at": item.get("date", {}).get("#text", ""),
        })
    return jsonify(recents)

if __name__ == "__main__":
    host = '0.0.0.0'
    port = '3000'
    app.run(host=host, port=port)