import os
import time
import re
from datetime import datetime, timezone
import requests
from celery import Celery, group
from celery.schedules import crontab
from env import load_environment
from supabase import create_client, Client

load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

last_fm_api_key = os.getenv("LAST_FM_API_KEY")
if not last_fm_api_key:
    raise RuntimeError("LAST_FM_API_KEY is required")

LAST_FM_API_BASE = "https://ws.audioscrobbler.com/2.0/"

def _lastfm_get(params):
    """Helper function to make Last.fm API requests"""
    params = {**params, "api_key": last_fm_api_key, "format": "json"}
    response = requests.get(LAST_FM_API_BASE, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise ValueError(data.get("message") or "Last.fm API error")
    return data


def _get_image_url(images, preferred_sizes):
    """Extract image URL from Last.fm image array"""
    for size in preferred_sizes:
        for image in images:
            if image.get("size") == size and image.get("#text"):
                return image.get("#text")
    return None


def _album_key(artist_name, album_name):
    """Generate consistent album key from artist and album name"""
    if not artist_name or not album_name:
        return None
    return f"{artist_name}::{album_name}".strip().lower()

def _normalize_track_name(track_name):
    """Normalize track names by stripping featuring suffixes for matching."""
    if not track_name:
        return None
    name = track_name.strip().lower()
    # Remove trailing "(feat...)" or "[feat...]" blocks
    name = re.sub(
        r"\s*[\(\[]\s*(feat\.?|ft\.?|featuring)\s+.*?[\)\]]\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    # Remove trailing "- feat..." or "– feat..." suffixes
    name = re.sub(
        r"\s*[-–—]\s*(feat\.?|ft\.?|featuring)\s+.*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+", " ", name).strip()
    return name or None


def _rpc_data(resp, label):
    """Extract data from a Supabase RPC response or raise a helpful error."""
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Supabase RPC {label} failed: {error}")
    data = getattr(resp, "data", None)
    return data or []


def _upsert_artist(artist_name):
    """Fetch artist info from Last.fm and upsert to database"""
    if not artist_name:
        return
    
    try:
        artist_info = _lastfm_get({
            "method": "artist.getinfo",
            "artist": artist_name
        })
        
        artist_data = artist_info.get("artist", {})
        artist_images = artist_data.get("image", [])
        
        supabase.table('last_fm_artists').upsert({
            'artist_name': artist_name,
            'artist_mbid': artist_data.get("mbid") or None,
            'artist_url': artist_data.get("url"),
            'listeners': artist_data.get("stats", {}).get("listeners"),
            'playcount': artist_data.get("stats", {}).get("playcount"),
            'image_small': _get_image_url(artist_images, ["small"]),
            'image_medium': _get_image_url(artist_images, ["medium"]),
            'image_large': _get_image_url(artist_images, ["large"]),
            'image_extralarge': _get_image_url(artist_images, ["extralarge"])
        }).execute()
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching artist info for {artist_name}: {e}")
        # Create minimal artist entry if API call fails
        supabase.table('last_fm_artists').upsert({
            'artist_name': artist_name
        }).execute()


def track_all_users_recently_listened_sync():
    """Synchronous tracker for environments without Celery workers."""
    users_response = supabase.table('last_fm_users').select('lastfm_username').execute()
    users = users_response.data or []
    print(f"[last_fm_album_tracking] Starting recent listens for {len(users)} user(s)")
    for user in users:
        username = user.get("lastfm_username")
        if not username:
            continue
        try:
            get_recently_listened(username)
            print(f"[last_fm_album_tracking] username={username} done")
        except Exception as exc:
            print(f"[last_fm_album_tracking] username={username} error: {exc}")
    print("[last_fm_album_tracking] Finished recent listens run")


def get_recently_listened(username):
    """Get tracks listened to in the last hour for a specific user"""
    one_hour_ago = int(time.time() - 3600)
    
    try:
        payload = _lastfm_get({
            "method": "user.getrecenttracks",
            "user": username,
            "from": one_hour_ago,
            "limit": 50,
        })
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching recent tracks for {username}: {e}")
        return

    items = payload.get("recenttracks", {}).get("track", [])
    if isinstance(items, dict):
        items = [items]

    for item in items:
        # Skip currently playing tracks (they don't have a timestamp yet)
        if item.get("@attr", {}).get("nowplaying") == "true":
            continue

        # Parse artist - it can be a string or an object with #text
        artist_obj = item.get("artist", {})
        if isinstance(artist_obj, dict):
            artist_name = artist_obj.get("#text", "")
        else:
            artist_name = str(artist_obj)
        
        # Parse album - it can be a string or an object with #text
        album_obj = item.get("album", {})
        if isinstance(album_obj, dict):
            album_name = album_obj.get("#text", "")
        else:
            album_name = str(album_obj)
            
        track_name = item.get("name", "")
        track_url = item.get("url", "")
        
        if not artist_name or not album_name or not track_name:
            continue

        album_key = _album_key(artist_name, album_name)
        if not album_key:
            continue

        # Parse played_at timestamp
        date_dict = item.get("date", {})
        played_at = None
        if "uts" in date_dict:
            try:
                played_at = datetime.fromtimestamp(int(date_dict["uts"]), tz=timezone.utc)
            except (TypeError, ValueError):
                played_at = datetime.now(timezone.utc)
        else:
            played_at = datetime.now(timezone.utc)

        images = item.get("image", [])

        # Ensure artist exists with full info
        _upsert_artist(artist_name)

        # Check if album exists
        album_exists = supabase.table("last_fm_albums")\
            .select('album_key')\
            .eq('album_key', album_key)\
            .limit(1)\
            .execute()
        
        if not album_exists.data:
            # Fetch full album info from Last.fm
            try:
                album_info = _lastfm_get({
                    "method": "album.getinfo",
                    "artist": artist_name,
                    "album": album_name
                })
                
                album_data = album_info.get("album", {})
                album_images = album_data.get("image", [])
                
                # Get tracks list - can be dict or list
                tracks_data = album_data.get("tracks", {})
                tracks = tracks_data.get("track", [])
                if isinstance(tracks, dict):
                    tracks = [tracks]
                
                # Insert album
                supabase.table('last_fm_albums').upsert({
                    'album_key': album_key,
                    'album_name': album_name,
                    'artist_name': artist_name,
                    'album_url': album_data.get("url"),
                    'listeners': album_data.get("listeners"),
                    'playcount': album_data.get("playcount"),
                    'image_small': _get_image_url(album_images, ["small"]),
                    'image_medium': _get_image_url(album_images, ["medium"]),
                    'image_large': _get_image_url(album_images, ["large"]),
                    'image_extralarge': _get_image_url(album_images, ["extralarge"]),
                    'image_mega': _get_image_url(album_images, ["mega"]),
                    'total_tracks': len(tracks)
                }).execute()

                # Insert album tracks
                for idx, track in enumerate(tracks, start=1):
                    track_artist = track.get("artist", {})
                    # Artist in track can be a string or an object with name field
                    if isinstance(track_artist, dict):
                        track_artist_name = track_artist.get("name", artist_name)
                    else:
                        track_artist_name = artist_name
                    
                    # Get duration - Last.fm returns it in seconds
                    duration = track.get("duration")
                    if duration:
                        try:
                            duration = int(duration)
                        except (ValueError, TypeError):
                            duration = None
                    
                    supabase.table("last_fm_album_tracks").upsert({
                        "album_key": album_key,
                        "track_number": idx,
                        "track_name": track.get("name", ""),
                        "track_name_normalized": _normalize_track_name(track.get("name", "")),
                        "track_url": track.get("url"),
                        "duration_sec": duration
                    }).execute()

                    # Ensure track artist exists with full info
                    _upsert_artist(track_artist_name)

                    # Insert track artist relationship
                    supabase.table('last_fm_track_artists').upsert({
                        'album_key': album_key,
                        'track_number': idx,
                        'artist_name': track_artist_name,
                        'artist_order': 1
                    }).execute()

            except (requests.RequestException, ValueError) as e:
                print(f"Error fetching album info for {album_name} by {artist_name}: {e}")
                # Create minimal album entry even if API call fails
                supabase.table('last_fm_albums').upsert({
                    'album_key': album_key,
                    'album_name': album_name,
                    'artist_name': artist_name,
                    'image_small': _get_image_url(images, ["small"]),
                    'image_medium': _get_image_url(images, ["medium"]),
                    'image_large': _get_image_url(images, ["large"]),
                    'image_extralarge': _get_image_url(images, ["extralarge"]),
                    'image_mega': _get_image_url(images, ["mega"])
                }).execute()

        # Record listened track
        supabase.table('last_fm_listened_tracks').upsert({
            'lastfm_username': username,
            'played_at': played_at.isoformat(),
            'track_name': track_name,
            'track_name_normalized': _normalize_track_name(track_name),
            'artist_name': artist_name,
            'album_name': album_name,
            'track_url': track_url,
            'album_key': album_key,
            'now_playing': False
        }).execute()


def get_albums_completion(username):
    """Get album completion statistics for a user"""
    resp = supabase.rpc('get_last_fm_album_completion', {'p_lastfm_username': username}).execute()
    data = _rpc_data(resp, "get_last_fm_album_completion")
    output = []
    for row in data:
        listened = row.get('listened') or 0
        total = row.get('total') or 0
        output.append({
            'album_key': row.get('album_key'),
            'album_name': row.get('album_name'),
            'artist': row.get('primary_artist'),
            'listened': listened,
            'total': total,
            'percentage': listened / total if total else 0,
            'album_image': row.get('album_image'),
        })
    return output


def get_album_tracks(username: str, album_key: str):
    """Get all tracks for an album with listened status for a user"""
    resp = supabase.rpc(
        'get_last_fm_album_tracks',
        {'p_lastfm_username': username, 'p_album_key': album_key}
    ).execute()
    data = _rpc_data(resp, "get_last_fm_album_tracks")

    output = []
    for row in data:
        output.append({
            'track_number': row.get('track_number'),
            'track_name': row.get('track_name'),
            'is_listened': row.get('is_listened'),
        })

    return output


def backfill_album_info():
    """
    One-time function to backfill album information for albums missing data.
    """
    # Get all albums missing total_tracks or image data
    albums = supabase.table('last_fm_albums')\
        .select('album_key, album_name, artist_name')\
        .or_('total_tracks.is.null,image_large.is.null,image_extralarge.is.null,image_mega.is.null')\
        .execute()
    
    if not albums.data:
        print("No albums need backfilling.")
        return
    
    print(f"Found {len(albums.data)} albums missing data.")
    
    # Update each album
    for album in albums.data:
        album_key = album['album_key']
        artist_name = album['artist_name']
        album_name = album['album_name']
        
        try:
            album_info = _lastfm_get({
                "method": "album.getinfo",
                "artist": artist_name,
                "album": album_name
            })
            
            album_data = album_info.get("album", {})
            album_images = album_data.get("image", [])
            
            # Get tracks count
            tracks_data = album_data.get("tracks", {})
            tracks = tracks_data.get("track", [])
            if isinstance(tracks, dict):
                tracks = [tracks]
            
            supabase.table('last_fm_albums').update({
                'album_url': album_data.get("url"),
                'listeners': album_data.get("listeners"),
                'playcount': album_data.get("playcount"),
                'image_small': _get_image_url(album_images, ["small"]),
                'image_medium': _get_image_url(album_images, ["medium"]),
                'image_large': _get_image_url(album_images, ["large"]),
                'image_extralarge': _get_image_url(album_images, ["extralarge"]),
                'image_mega': _get_image_url(album_images, ["mega"]),
                'total_tracks': len(tracks)
            }).eq('album_key', album_key).execute()
            
            print(f"Updated {album_name} by {artist_name}")
            time.sleep(0.25)  # Rate limiting
            
        except Exception as e:
            print(f"Error updating {album_name} by {artist_name}: {e}")
    
    print("Backfill complete!")


def backfill_artist_info():
    """
    One-time function to backfill artist information for artists missing data.
    """
    # Get all artists missing metadata (only have artist_name)
    artists = supabase.table('last_fm_artists')\
        .select('artist_name')\
        .or_('artist_url.is.null,listeners.is.null,image_large.is.null')\
        .execute()
    
    if not artists.data:
        print("No artists need backfilling.")
        return
    
    print(f"Found {len(artists.data)} artists missing data.")
    
    # Update each artist
    for artist in artists.data:
        artist_name = artist['artist_name']
        
        try:
            artist_info = _lastfm_get({
                "method": "artist.getinfo",
                "artist": artist_name
            })
            
            artist_data = artist_info.get("artist", {})
            artist_images = artist_data.get("image", [])
            
            supabase.table('last_fm_artists').update({
                'artist_mbid': artist_data.get("mbid") or None,
                'artist_url': artist_data.get("url"),
                'listeners': artist_data.get("stats", {}).get("listeners"),
                'playcount': artist_data.get("stats", {}).get("playcount"),
                'image_small': _get_image_url(artist_images, ["small"]),
                'image_medium': _get_image_url(artist_images, ["medium"]),
                'image_large': _get_image_url(artist_images, ["large"]),
                'image_extralarge': _get_image_url(artist_images, ["extralarge"])
            }).eq('artist_name', artist_name).execute()
            
            print(f"Updated {artist_name}")
            time.sleep(0.25)  # Rate limiting
            
        except Exception as e:
            print(f"Error updating {artist_name}: {e}")
    
    print("Artist backfill complete!")

def backfill_track_name_normalization():
    """
    One-time function to backfill normalized track names for matching.
    """
    tracks_resp = supabase.table('last_fm_album_tracks')\
        .select('album_key, track_number, track_name, track_name_normalized')\
        .execute()
    tracks = tracks_resp.data or []
    print(f"Found {len(tracks)} album tracks to check.")
    for row in tracks:
        normalized = _normalize_track_name(row.get("track_name"))
        if normalized and normalized != row.get("track_name_normalized"):
            supabase.table('last_fm_album_tracks').update({
                'track_name_normalized': normalized
            }).eq('album_key', row.get('album_key'))\
             .eq('track_number', row.get('track_number'))\
             .execute()

    listens_resp = supabase.table('last_fm_listened_tracks')\
        .select('lastfm_username, played_at, track_name, track_name_normalized')\
        .execute()
    listens = listens_resp.data or []
    print(f"Found {len(listens)} listened tracks to check.")
    for row in listens:
        normalized = _normalize_track_name(row.get("track_name"))
        if normalized and normalized != row.get("track_name_normalized"):
            supabase.table('last_fm_listened_tracks').update({
                'track_name_normalized': normalized
            }).eq('lastfm_username', row.get('lastfm_username'))\
             .eq('played_at', row.get('played_at'))\
             .eq('track_name', row.get('track_name'))\
             .execute()

    print("Track-name normalization backfill complete.")
