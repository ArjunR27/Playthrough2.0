import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from supabase import create_client, Client
import os
import time
from celery import Celery
from celery.schedules import crontab
from backend.validate_token import get_valid_token

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))
celery = Celery("backend.album_tracking", broker="redis://localhost:6379/0")
celery.conf.timezone = 'UTC'


# this is added to the redis queue
# when the time is up the queue is the task is popped from redis queue
# then celery uses the scheduler to determine if the task should be run
    ## beat schedules the task on the queue every 0th minute of each hour --> tells the worker to run
    ## worker = runs the task below. 

celery.conf.beat_schedule = {
    'track-listening-every-hour': {
        'task': 'backend.album_tracking.track_all_users_recently_listened',
        'schedule': crontab(minute=45)
        # 'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
}

# this needs to be improved, with more users this will still update one at a time?
# maybe have to thread each user or something along those lines
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
        album = item["track"]["album"]
        album_id = album["id"]
        album_name = album["name"]
        album_type = album["album_type"]
        primary_artist = album["artists"][0]
        artist_id = primary_artist["id"]
        artist_name = primary_artist["name"]
        total_tracks = album["total_tracks"]

        album_exists = supabase.table("albums")\
            .select('album_id')\
            .eq('album_id', album_id)\
            .limit(1)\
            .execute()
        
        if not album_exists.data:
            album_info = sp.album(album_id)
            supabase.table('albums').upsert({
                'album_id': album_id,
                'album_name': album_name,
                'album_type': album_type,
                'artist_id': artist_id,
                'artist_name': artist_name,
                'total_tracks': total_tracks
            }).execute()

            for track in album_info["tracks"]["items"]:
                supabase.table("album_tracks").upsert({
                    "album_id": album_id,
                    "track_id": track["id"],
                    "track_name": track["name"],
                    "track_number": track["track_number"],
                }).execute()
         
        else:
            # ensure the current track exists even if the rest of the album was preloaded
            supabase.table("album_tracks").upsert({
                "album_id": album_id,
                "track_id": track_id,
                "track_name": track_name,
                "track_number": item["track"]["track_number"],
            }).execute()

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
         

def get_albums_completion(user_id):
    # this is an rpc call to a query i created in supabase that gives me what i want
    # way faster
    resp = supabase.rpc('get_album_completion', {'p_user_id': user_id}).execute()
    output = []
    for row in resp.data:
        output.append({
            'album_id': row['album_id'],
            'album_name': row['album_name'],
            'artist': row['primary_artist'],
            'listened': row['listened'],
            'total': row['total'],
            'percentage': row['listened'] / row['total'],
            'album_image': row['album_image'],
        })
    return output
