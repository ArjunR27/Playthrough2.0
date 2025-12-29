import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from supabase import create_client, Client
import os
import time
from celery import Celery
from celery.schedules import crontab
from validate_token import *

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
celery = Celery("album_tracking", broker="redis://localhost:6379/0")
celery.conf.timezone = 'UTC'

celery.conf.beat_schedule = {
    'track-listening-every-hour': {
        'task': 'album_tracking.track_all_users_recently_listened',
        'schedule': crontab(minute=45),
        # 'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
}

# this is added to the redis queue
# when the time is up the queue is the task is popped from redis queue
# then celery uses the scheduler to determine if the task should be run
    ## beat schedules the task on the queue every 0th minute of each hour --> tells the worker to run
    ## worker = runs the task below. 

@celery.task
def track_all_users_recently_listened():
    users_response = supabase.table('users').select('user_id').execute()
    for user in users_response.data:
        get_recently_listened(user['user_id'])

# get 50 tracks within last 1 hour
@celery.task
def get_recently_listened(user_id):
    decrypted_token = get_valid_token(user_id)
    sp = spotipy.Spotify(auth=decrypted_token)

    one_hour_ago = int((time.time() - 3600) * 1000)
    recently_listened = sp.current_user_recently_played(limit=50, after=one_hour_ago)

    items = recently_listened["items"]
    for item in items:
        track_name = item["track"]["name"]
        track_id = item["track"]["id"]
        artists = item["track"]["artists"]
        album_type = item["track"]["album"]["album_type"]
        album_id = item["track"]["album"]["id"]
        album_name = item["track"]["album"]["name"]

        supabase.table('listened_tracks').upsert({
            'user_id': user_id,
            'track_id': track_id,
            'track_name': track_name,
            'album_type': album_type,
            'album_name': album_name,
            'album_id': album_id
        }).execute()

        for idx, artist in enumerate(artists):
            supabase.table('artists').upsert({
                'artist_id': artist['id'],
                'artist_name': artist['name']
            }).execute()

            supabase.table('track_artists').upsert({
                'track_id': track_id,
                'artist_id': artist['id'],
                'artist_order': idx
            }).execute()
