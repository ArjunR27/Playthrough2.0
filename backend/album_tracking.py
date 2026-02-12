import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from env import load_environment
from supabase import create_client, Client
import os
import time
from validate_token import get_valid_token

load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

def _get_playthrough_user_id(spotify_user_id):
    resp = (
        supabase.table("users")
        .select("playthrough_user_id")
        .eq("user_id", spotify_user_id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0].get("playthrough_user_id")

# this needs to be improved, with more users this will still update one at a time?
# maybe have to thread each user or something along those lines
def track_all_users_recently_listened():
    users_response = supabase.table('users').select('user_id').execute()
    users = users_response.data or []
    print(f"[album_tracking] Starting recent listens for {len(users)} user(s)")
    for user in users:
        user_id = user["user_id"]
        print(f"[album_tracking] user_id={user_id} starting")
        try:
            get_recently_listened(user_id)
            print(f"[album_tracking] user_id={user_id} done")
        except SpotifyException as exc:
            status = getattr(exc, "http_status", None)
            if status == 403:
                print(
                    "[album_tracking] user_id=%s skipped (403 not registered in Spotify app)"
                    % user_id
                )
                continue
            print(f"[album_tracking] user_id={user_id} Spotify error: {exc}")
        except Exception as exc:
            print(f"[album_tracking] user_id={user_id} unexpected error: {exc}")
    print("[album_tracking] Finished recent listens run")

# get 50 tracks within last 1 hour
def get_recently_listened(user_id):
    decrypted_token = get_valid_token(user_id)
    playthrough_user_id = _get_playthrough_user_id(user_id)
    if not playthrough_user_id:
        print(f"Missing playthrough_user_id for user_id {user_id}")
        return
    sp = spotipy.Spotify(auth=decrypted_token)
    known_artist_ids: set[str] = set()

    one_hour_ago = int((time.time() - 3600) * 1000)
    recently_listened = sp.current_user_recently_played(limit=50, after=one_hour_ago)

    items = recently_listened["items"]
    print(f"[album_tracking] user_id={user_id} recent_items={len(items)} since_ms={one_hour_ago}")
    if not items:
        print(f"[album_tracking] user_id={user_id} no recent listens found")
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
        album_image = album["images"][0]["url"]
        album_image_height = album["images"][0]["height"]
        album_image_width = album["images"][0]["width"]

        album_exists = supabase.table("albums")\
            .select('album_id')\
            .eq('album_id', album_id)\
            .limit(1)\
            .execute()
        
        if not album_exists.data:
            print(f"[album_tracking] inserting album album_id={album_id} album_name={album_name}")
            album_info = sp.album(album_id)
            supabase.table('albums').upsert({
                'album_id': album_id,
                'album_name': album_name,
                'album_type': album_type,
                'artist_id': artist_id,
                'artist_name': artist_name,
                'total_tracks': total_tracks,
                'album_image': album_image,
                'album_image_height': album_image_height,
                'album_image_width': album_image_width
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
            print(f"[album_tracking] album exists album_id={album_id} ensuring track_id={track_id}")
            supabase.table("album_tracks").upsert({
                "album_id": album_id,
                "track_id": track_id,
                "track_name": track_name,
                "track_number": item["track"]["track_number"],
            }).execute()

        print(f"[album_tracking] upsert listened_tracks track_id={track_id} track_name={track_name} album_name={album_name}")
        supabase.table('listened_tracks').upsert({
            'user_id': user_id,
            'playthrough_user_id': playthrough_user_id,
            'track_id': track_id,
            'track_name': track_name,
            'album_type': album_type,
            'album_name': album_name,
            'album_id': album_id
        }).execute()

        for idx, artist in enumerate(artists):
            artist_id = artist["id"]
            artist_name = artist["name"]
            if artist_id not in known_artist_ids:
                existing = (
                    supabase.table("artists")
                    .select("artist_id")
                    .eq("artist_id", artist_id)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    known_artist_ids.add(artist_id)
                else:
                    try:
                        artist_info = sp.artist(artist_id)
                        genres = artist_info.get("genres", [])
                        supabase.table("artists").upsert({
                            "artist_id": artist_id,
                            "artist_name": artist_name,
                            "genres": genres,
                        }).execute()
                        known_artist_ids.add(artist_id)
                    except Exception as exc:
                        print(f"Error fetching genres for {artist_id}: {exc}")

            supabase.table('track_artists').upsert({
                'track_id': track_id,
                'artist_id': artist['id'],
                'artist_order': idx
            }).execute()
         
def backfill_album_images():
    """
    One-time function to backfill album images for albums missing image data.
    """
    # Get all albums missing image data
    albums = supabase.table('albums')\
        .select('album_id, album_name')\
        .or_('album_image.is.null,album_image_height.is.null,album_image_width.is.null')\
        .execute()
    
    if not albums.data:
        print("No albums need image backfilling.")
        return
    
    print(f"Found {len(albums.data)} albums missing image data.")
    
    # Get first user's token for Spotify API access
    users = supabase.table('users').select('user_id').limit(1).execute()
    if not users.data:
        print("No users found.")
        return
    
    user_id = users.data[0]['user_id']
    decrypted_token = get_valid_token(user_id)
    if not decrypted_token:
        print("Could not get valid token.")
        return
    
    sp = spotipy.Spotify(auth=decrypted_token)
    
    # Update each album
    for album in albums.data:
        album_id = album['album_id']
        try:
            album_info = sp.album(album_id)
            
            album_image = None
            album_image_height = None
            album_image_width = None
            
            if album_info.get('images') and len(album_info['images']) > 0:
                album_image = album_info['images'][0]['url']
                album_image_height = album_info['images'][0].get('height')
                album_image_width = album_info['images'][0].get('width')
            
            supabase.table('albums').update({
                'album_image': album_image,
                'album_image_height': album_image_height,
                'album_image_width': album_image_width
            }).eq('album_id', album_id).execute()
            
            print(f"Updated {album['album_name']}")
            time.sleep(0.1)  # Small delay to avoid rate limiting
            
        except Exception as e:
            print(f"Error updating {album['album_name']}: {e}")
    
    print("Backfill complete!")

    
def get_albums_completion(user_id):
    # this is an rpc call to a query i created in supabase that gives me what i want
    # way faster
    resp = supabase.rpc('get_album_completion', {'p_user_id': user_id}).execute()
    output = []
    for row in resp.data:
        total = row['total']
        listened = row['listened']
        percentage = listened / total if total else 0
        output.append({
            'album_id': row['album_id'],
            'album_name': row['album_name'],
            'artist': row['primary_artist'],
            'listened': listened,
            'total': total,
            'percentage': percentage,
            'album_image': row['album_image'],
            })
    return output

def get_albums_completion_sorted(user_id):
    # this is an rpc call to a query i created in supabase that gives me what i want
    # way faster
    resp = supabase.rpc('get_album_completion', {'p_user_id': user_id}).execute()
    output = []
    for row in resp.data:
        total = row['total']
        listened = row['listened']
        percentage = listened / total if total else 0
        if percentage < 1.0:
            output.append({
                'album_id': row['album_id'],
                'album_name': row['album_name'],
                'artist': row['primary_artist'],
                'listened': listened,
                'total': total,
                'percentage': listened / total,
                'album_image': row['album_image'],
            })
    return sorted(output, key=lambda album: album['percentage'], reverse=True)


def get_album_tracks(user_id: str, album_id: str):
    resp = supabase.rpc(
        'get_album_tracks',
        {'p_user_id': user_id, 'p_album_id': album_id}
    ).execute()

    output = []
    for row in resp.data:
        output.append({
            'track_id': row['track_id'],
            'track_name': row['track_name'],
            'track_number': row['track_number'],
            'is_listened': row['is_listened'],
        })

    return output
