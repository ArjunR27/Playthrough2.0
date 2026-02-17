import os
import time
import re
import string
import unicodedata
from datetime import datetime, timezone
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from celery import Celery, group
from celery.schedules import crontab
from env import load_environment
from resolve_singles_mapping import resolve_album_for_track
from supabase import create_client, Client

load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

last_fm_api_key = os.getenv("LAST_FM_API_KEY")
if not last_fm_api_key:
    raise RuntimeError("LAST_FM_API_KEY is required")

LAST_FM_API_BASE = "https://ws.audioscrobbler.com/2.0/"

_spotify_app_client = None

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

def _normalize_apostrophes(value):
    if not value:
        return value
    return value.replace("’", "'").replace("‘", "'")

def _normalize_to_alnum(value):
    if not value:
        return None
    value = _normalize_apostrophes(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = "".join(ch for ch in value if ch.isalnum() or ch.isspace())
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value or None

def _normalize_track_name(track_name, album_name=None):
    """Normalize track names by stripping featuring suffixes for matching."""
    if not track_name:
        return None
    name = _normalize_apostrophes(track_name).strip().lower()
    collaborator_prefix = r"(?:feat\.?|ft\.?|featuring|with|w/)"
    # Remove trailing "(feat...)" / "(with...)" or "[feat...]" / "[with...]" blocks
    name = re.sub(
        rf"\s*[\(\[]\s*{collaborator_prefix}\s+.*?[\)\]]\s*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    # Remove trailing "- feat...", "– with...", ", featuring..." style suffixes
    name = re.sub(
        rf"\s*[-–—,:]\s*{collaborator_prefix}\s+.*$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    # Remove trailing artist-credit parentheses, e.g. "(EI8HT & Offset)".
    # Keep musical version tags like "(remix)" or "(live)".
    version_terms = r"(?:remix|mix|edit|version|live|acoustic|instrumental|demo|radio|extended|deluxe|score|soundtrack)"
    artist_like_terms = r"(?:[,&/]|(?:\band\b)|(?:feat\.?|ft\.?|featuring|with|w/))"
    while True:
        match = re.search(r"\s*[\(\[]([^\)\]]+)[\)\]]\s*$", name)
        if not match:
            break
        content = match.group(1).strip().lower()
        if re.search(version_terms, content):
            break
        if not re.search(artist_like_terms, content):
            break
        name = name[:match.start()].rstrip()

    # Some scrobbles append album title into track name; trim from first album-title hit.
    if album_name:
        album_fragment = _normalize_apostrophes(album_name).strip().lower()
        if album_fragment:
            album_idx = name.find(album_fragment)
            if album_idx > 0:
                trimmed = name[:album_idx].rstrip(" -–—,:")
                if trimmed:
                    name = trimmed

    name = re.sub(r"\s+", " ", name).strip()
    return _normalize_to_alnum(name)

def _normalize_album_name(name):
    if not name:
        return None
    return _normalize_to_alnum(name)

def _normalize_artist_name(name):
    if not name:
        return None
    return _normalize_to_alnum(name)


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_lastfm_artist_name(value):
    if isinstance(value, dict):
        for key in ("name", "#text", "artist"):
            candidate = _clean_text(value.get(key))
            if candidate:
                return candidate
        return None
    return _clean_text(value)


def _extract_spotify_artist_name(artists):
    if not isinstance(artists, list):
        return None
    for artist in artists:
        if not isinstance(artist, dict):
            continue
        candidate = _clean_text(artist.get("name"))
        if candidate:
            return candidate
    return None


def _extract_lastfm_album_artist(album_data):
    if not isinstance(album_data, dict):
        return None
    return _extract_lastfm_artist_name(album_data.get("artist"))


def _extract_spotify_album_artist(spotify_album):
    if not isinstance(spotify_album, dict):
        return None
    return _extract_spotify_artist_name(spotify_album.get("artists") or [])


def _lastfm_get_album_info(artist_name, album_name):
    artist_name = _clean_text(artist_name)
    album_name = _clean_text(album_name)
    if not artist_name or not album_name:
        return None
    try:
        payload = _lastfm_get({
            "method": "album.getinfo",
            "artist": artist_name,
            "album": album_name
        })
    except (requests.RequestException, ValueError):
        return None
    album_data = payload.get("album", {}) if isinstance(payload, dict) else {}
    return album_data if isinstance(album_data, dict) else None


def _lastfm_album_tracks(album_data):
    if not isinstance(album_data, dict):
        return []
    tracks_data = album_data.get("tracks", {})
    if not isinstance(tracks_data, dict):
        return []
    tracks = tracks_data.get("track", [])
    if isinstance(tracks, dict):
        return [tracks]
    if isinstance(tracks, list):
        return tracks
    return []


def _lastfm_album_track_match_state(album_data, track_name):
    """
    Returns:
    - True: track exists in album tracklist (or no track provided)
    - False: tracklist exists and track is missing
    - None: tracklist unavailable, cannot verify
    """
    if not track_name:
        return True
    target_track_norm = _normalize_track_name(track_name)
    if not target_track_norm:
        return True
    tracks = _lastfm_album_tracks(album_data)
    if not tracks:
        return None
    for track in tracks:
        if not isinstance(track, dict):
            continue
        name_norm = _normalize_track_name(track.get("name", ""))
        if name_norm == target_track_norm:
            return True
    return False


def _resolve_identity_cache_key(artist_hint, album_name, track_name):
    artist_norm = _normalize_artist_name(artist_hint) or ""
    album_norm = _normalize_album_name(album_name) or ""
    # Track-level fallback is only needed when album title cannot be trusted/found.
    track_norm = _normalize_track_name(track_name) if not album_norm else None
    return artist_norm, album_norm, track_norm or ""


def resolve_canonical_lastfm_album_identity(artist_hint, album_name, track_name=None, cache=None):
    """
    Resolve a canonical Last.fm album identity using:
    1) Last.fm album metadata
    2) Spotify album metadata
    3) fallback to the scrobble artist
    """
    artist_hint = _clean_text(artist_hint)
    album_name = _clean_text(album_name)
    track_name = _clean_text(track_name)
    cache = cache if cache is not None else {}

    cache_key = _resolve_identity_cache_key(artist_hint, album_name, track_name)
    if cache_key in cache:
        return dict(cache[cache_key])

    resolved_album_name = album_name
    candidate_album_artist = None

    # Resolve candidate album/artist from track metadata; only trust candidate artist
    # when its album agrees with the current resolved album title (if provided).
    if artist_hint and track_name:
        resolved_album, resolved_artist = resolve_album_for_track(
            artist_hint,
            track_name,
            lastfm_get=_lastfm_get,
            spotify_client=_get_spotify_app_client,
            normalize_track_name=_normalize_track_name,
            normalize_artist_name=_normalize_artist_name,
            track_name_normalized=_normalize_track_name(track_name),
            return_artist=True,
        )
        resolved_album = _clean_text(resolved_album)
        resolved_artist = _clean_text(resolved_artist)
        if not resolved_album_name and resolved_album:
            resolved_album_name = resolved_album
        if resolved_artist:
            if not resolved_album_name or (
                resolved_album
                and _normalize_album_name(resolved_album) == _normalize_album_name(resolved_album_name)
            ):
                candidate_album_artist = resolved_artist

    if not resolved_album_name:
        result = {
            "artist_name": artist_hint,
            "album_name": None,
            "album_key": None,
            "source": "fallback",
        }
        cache[cache_key] = dict(result)
        return result

    canonical_artist = None
    source = "fallback"

    lookup_artists = []
    for lookup_artist in (candidate_album_artist, artist_hint):
        if not lookup_artist:
            continue
        lookup_artist_norm = _normalize_artist_name(lookup_artist)
        if any(_normalize_artist_name(existing) == lookup_artist_norm for existing in lookup_artists):
            continue
        lookup_artists.append(lookup_artist)

    album_data = None
    unverified_album_data = None
    for lookup_artist in lookup_artists:
        candidate_album_data = _lastfm_get_album_info(lookup_artist, resolved_album_name)
        if not candidate_album_data:
            continue
        track_match = _lastfm_album_track_match_state(candidate_album_data, track_name)
        if track_match is True:
            album_data = candidate_album_data
            break
        if track_match is None and not unverified_album_data:
            # Keep as fallback only after Spotify lookup attempts.
            unverified_album_data = candidate_album_data

    if album_data:
        canonical_artist = _extract_lastfm_album_artist(album_data)
        album_name_from_metadata = _clean_text(album_data.get("name"))
        if album_name_from_metadata:
            resolved_album_name = album_name_from_metadata
        if canonical_artist:
            source = "lastfm"

    if not canonical_artist:
        spotify_album = _spotify_find_album(artist_hint, resolved_album_name, strict_artist_match=True)
        if (
            not spotify_album
            and candidate_album_artist
            and _normalize_artist_name(candidate_album_artist) != _normalize_artist_name(artist_hint)
        ):
            spotify_album = _spotify_find_album(
                candidate_album_artist,
                resolved_album_name,
                strict_artist_match=True,
            )
        if not spotify_album:
            spotify_album = _spotify_find_album(artist_hint, resolved_album_name, strict_artist_match=False)
        if not spotify_album and candidate_album_artist:
            spotify_album = _spotify_find_album(
                candidate_album_artist,
                resolved_album_name,
                strict_artist_match=False,
            )

        if spotify_album:
            canonical_artist = _extract_spotify_album_artist(spotify_album)
            album_name_from_spotify = _clean_text(spotify_album.get("name"))
            if album_name_from_spotify:
                resolved_album_name = album_name_from_spotify
            if canonical_artist:
                source = "spotify"

    if not canonical_artist and unverified_album_data:
        canonical_artist = _extract_lastfm_album_artist(unverified_album_data)
        album_name_from_unverified = _clean_text(unverified_album_data.get("name"))
        if album_name_from_unverified:
            resolved_album_name = album_name_from_unverified
        if canonical_artist:
            source = "lastfm_unverified"

    if not canonical_artist:
        canonical_artist = candidate_album_artist or artist_hint
        source = "fallback"

    result = {
        "artist_name": canonical_artist,
        "album_name": resolved_album_name,
        "album_key": _album_key(canonical_artist, resolved_album_name),
        "source": source,
    }
    cache[cache_key] = dict(result)
    return result


def _rpc_data(resp, label):
    """Extract data from a Supabase RPC response or raise a helpful error."""
    error = getattr(resp, "error", None)
    if error:
        raise RuntimeError(f"Supabase RPC {label} failed: {error}")
    data = getattr(resp, "data", None)
    return data or []

def _get_spotify_app_client():
    global _spotify_app_client
    if _spotify_app_client:
        return _spotify_app_client
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[last_fm_album_tracking] Spotify client credentials missing; skipping fallback")
        return None
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        _spotify_app_client = spotipy.Spotify(auth_manager=auth_manager)
        return _spotify_app_client
    except Exception as exc:
        print(f"[last_fm_album_tracking] Failed to init Spotify client: {exc}")
        return None

def _spotify_find_album(artist_name, album_name, strict_artist_match=True):
    sp = _get_spotify_app_client()
    if not sp:
        return None
    if not album_name:
        return None
    query = f"album:{album_name}"
    if strict_artist_match and artist_name:
        query += f" artist:{artist_name}"
    try:
        results = sp.search(q=query, type="album", limit=20)
    except Exception as exc:
        print(f"[last_fm_album_tracking] Spotify search failed for {artist_name} - {album_name}: {exc}")
        return None

    albums = results.get("albums", {}).get("items", []) if isinstance(results, dict) else []
    target_album = None
    fallback_album = None
    target_album_norm = _normalize_album_name(album_name)
    target_artist_norm = _normalize_artist_name(artist_name)

    for item in albums:
        if _normalize_album_name(item.get("name")) != target_album_norm:
            continue
        if not fallback_album:
            fallback_album = item
        artists = item.get("artists") or []
        if target_artist_norm and any(
            _normalize_artist_name((artist or {}).get("name")) == target_artist_norm
            for artist in artists
            if isinstance(artist, dict)
        ):
            target_album = item
            break
        if not strict_artist_match:
            target_album = item
            break

    if not target_album or not target_album.get("id"):
        if strict_artist_match:
            return None
        target_album = fallback_album
    if not target_album or not target_album.get("id"):
        return None

    try:
        return sp.album(target_album["id"])
    except Exception as exc:
        print(f"[last_fm_album_tracking] Spotify album fetch failed for {target_album.get('id')}: {exc}")
        return None

def _spotify_collect_tracks(sp, spotify_album):
    tracks_data = spotify_album.get("tracks") or {}
    items = list(tracks_data.get("items") or [])
    while tracks_data.get("next"):
        try:
            tracks_data = sp.next(tracks_data)
        except Exception as exc:
            print(f"[last_fm_album_tracking] Spotify pagination failed: {exc}")
            break
        items.extend(tracks_data.get("items") or [])
    return items

def _upsert_album_tracks_from_spotify(album_key, spotify_album):
    if not spotify_album:
        return 0
    sp = _get_spotify_app_client()
    if not sp:
        return 0
    tracks = _spotify_collect_tracks(sp, spotify_album)
    if not tracks:
        return 0

    sorted_tracks = sorted(
        tracks,
        key=lambda t: (
            t.get("disc_number") or 0,
            t.get("track_number") or 0,
        ),
    )

    track_rows = []
    for idx, track in enumerate(sorted_tracks, start=1):
        duration_ms = track.get("duration_ms")
        duration_sec = None
        if duration_ms is not None:
            try:
                duration_sec = int(duration_ms) // 1000
            except (ValueError, TypeError):
                duration_sec = None

        track_rows.append({
            "album_key": album_key,
            "track_number": idx,
            "track_name": track.get("name", ""),
            "track_name_normalized": _normalize_track_name(track.get("name", "")),
            "track_url": None,
            "duration_sec": duration_sec,
        })

    if track_rows:
        supabase.table("last_fm_album_tracks").upsert(track_rows).execute()

    supabase.table("last_fm_albums").update({
        "total_tracks": len(sorted_tracks)
    }).eq("album_key", album_key).execute()

    return len(sorted_tracks)

def _get_album_track_count(album_key):
    try:
        resp = (
            supabase.table("last_fm_album_tracks")
            .select("track_number", count="exact", head=True)
            .eq("album_key", album_key)
            .execute()
        )
        if getattr(resp, "count", None) is not None:
            return resp.count or 0
    except TypeError:
        pass
    resp = supabase.table("last_fm_album_tracks")\
        .select("track_number")\
        .eq("album_key", album_key)\
        .execute()
    return len(resp.data or [])

def _insert_lastfm_album_tracks(album_key, tracks, artist_name, seen_artists=None):
    track_rows = []
    track_artist_rows = []
    local_artists = set()
    for idx, track in enumerate(tracks, start=1):
        track_artist = track.get("artist", {})
        if isinstance(track_artist, dict):
            track_artist_name = track_artist.get("name", artist_name)
        else:
            track_artist_name = artist_name

        duration = track.get("duration")
        if duration:
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = None

        track_rows.append({
            "album_key": album_key,
            "track_number": idx,
            "track_name": track.get("name", ""),
            "track_name_normalized": _normalize_track_name(track.get("name", "")),
            "track_url": track.get("url"),
            "duration_sec": duration
        })

        track_artist_rows.append({
            'album_key': album_key,
            'track_number': idx,
            'artist_name': track_artist_name,
            'artist_order': 1
        })
        if track_artist_name:
            local_artists.add(track_artist_name)

    if track_rows:
        supabase.table("last_fm_album_tracks").upsert(track_rows).execute()
    if local_artists:
        supabase.table("last_fm_artists").upsert([
            {"artist_name": artist} for artist in local_artists
        ]).execute()
    if track_artist_rows:
        supabase.table('last_fm_track_artists').upsert(track_artist_rows).execute()

    if seen_artists is None:
        seen_artists = set()
    for artist in local_artists:
        if artist not in seen_artists:
            _upsert_artist(artist)
            seen_artists.add(artist)

    return len(track_rows)

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
    twenty_five_minutes = int(time.time() - 1500)
    
    try:
        payload = _lastfm_get({
            "method": "user.getrecenttracks",
            "user": username,
            "from": twenty_five_minutes,
            "limit": 50,
        })
    except (requests.RequestException, ValueError) as e:
        print(f"Error fetching recent tracks for {username}: {e}")
        return

    items = payload.get("recenttracks", {}).get("track", [])
    if isinstance(items, dict):
        items = [items]

    seen_artists = set()
    album_cache = {}
    canonical_identity_cache = {}
    logged_key_rewrites = set()

    for item in items:
        # Skip currently playing tracks (they don't have a timestamp yet)
        if item.get("@attr", {}).get("nowplaying") == "true":
            continue

        artist_name = _extract_lastfm_artist_name(item.get("artist"))
        album_name = _extract_lastfm_artist_name(item.get("album"))
        track_name = _clean_text(item.get("name")) or ""
        track_url = _clean_text(item.get("url")) or ""

        if not artist_name or not track_name:
            continue

        canonical_identity = resolve_canonical_lastfm_album_identity(
            artist_name,
            album_name,
            track_name,
            cache=canonical_identity_cache,
        )
        canonical_artist_name = canonical_identity.get("artist_name") or artist_name
        canonical_album_name = canonical_identity.get("album_name") or album_name
        album_key = canonical_identity.get("album_key")
        if not canonical_album_name or not album_key:
            continue
        track_name_normalized = _normalize_track_name(track_name, album_name=canonical_album_name)

        old_key = _album_key(artist_name, canonical_album_name)
        if old_key and old_key != album_key:
            rewrite = (old_key, album_key)
            if rewrite not in logged_key_rewrites:
                print(
                    "[last_fm_album_tracking] canonical album_key rewrite "
                    f"source={canonical_identity.get('source')} old={old_key} new={album_key}"
                )
                logged_key_rewrites.add(rewrite)

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

        # Ensure both track and canonical album artists exist.
        for candidate_artist in (artist_name, canonical_artist_name):
            if candidate_artist and candidate_artist not in seen_artists:
                _upsert_artist(candidate_artist)
                seen_artists.add(candidate_artist)

        if album_key in album_cache:
            album_state = album_cache[album_key]
        else:
            album_resp = supabase.table("last_fm_albums")\
                .select('album_key, total_tracks')\
                .eq('album_key', album_key)\
                .limit(1)\
                .execute()
            album_row = album_resp.data[0] if album_resp.data else None
            album_state = {
                "exists": bool(album_row),
                "total_tracks": album_row.get("total_tracks") if album_row else None,
                "track_count": _get_album_track_count(album_key) if album_row else 0,
                "backfill_attempted": False,
            }
            album_cache[album_key] = album_state

        album_exists = album_state["exists"]
        total_tracks = album_state["total_tracks"]
        track_count = album_state["track_count"]

        if not album_exists:
            album_state["backfill_attempted"] = True
            album_data = _lastfm_get_album_info(canonical_artist_name, canonical_album_name) or {}
            album_images = album_data.get("image", []) if album_data else images

            # Get tracks list - can be dict or list
            tracks_data = album_data.get("tracks", {}) if album_data else {}
            tracks = tracks_data.get("track", []) if isinstance(tracks_data, dict) else []
            if isinstance(tracks, dict):
                tracks = [tracks]

            # Insert album
            supabase.table('last_fm_albums').upsert({
                'album_key': album_key,
                'album_name': canonical_album_name,
                'artist_name': canonical_artist_name,
                'album_url': album_data.get("url"),
                'listeners': album_data.get("listeners"),
                'playcount': album_data.get("playcount"),
                'image_small': _get_image_url(album_images, ["small"]),
                'image_medium': _get_image_url(album_images, ["medium"]),
                'image_large': _get_image_url(album_images, ["large"]),
                'image_extralarge': _get_image_url(album_images, ["extralarge"]),
                'image_mega': _get_image_url(album_images, ["mega"]),
                'total_tracks': len(tracks) if tracks else None
            }).execute()

            # Insert album tracks
            if tracks:
                count = _insert_lastfm_album_tracks(
                    album_key,
                    tracks,
                    canonical_artist_name,
                    seen_artists,
                )
                album_state["track_count"] = count
                album_state["total_tracks"] = count
            else:
                spotify_album = _spotify_find_album(
                    canonical_artist_name,
                    canonical_album_name,
                    strict_artist_match=False,
                )
                if spotify_album:
                    count = _upsert_album_tracks_from_spotify(album_key, spotify_album)
                    album_state["track_count"] = count
                    album_state["total_tracks"] = count
            album_state["exists"] = True
        else:
            if track_count == 0:
                if not album_state.get("backfill_attempted"):
                    album_state["backfill_attempted"] = True
                    album_data = _lastfm_get_album_info(canonical_artist_name, canonical_album_name) or {}
                    tracks_data = album_data.get("tracks", {}) if album_data else {}
                    tracks = tracks_data.get("track", []) if isinstance(tracks_data, dict) else []
                    if isinstance(tracks, dict):
                        tracks = [tracks]

                    if tracks:
                        count = _insert_lastfm_album_tracks(
                            album_key,
                            tracks,
                            canonical_artist_name,
                            seen_artists,
                        )
                        supabase.table('last_fm_albums').update({
                            'total_tracks': count
                        }).eq('album_key', album_key).execute()
                        album_state["track_count"] = count
                        album_state["total_tracks"] = count
                    else:
                        spotify_album = _spotify_find_album(
                            canonical_artist_name,
                            canonical_album_name,
                            strict_artist_match=False,
                        )
                        if spotify_album:
                            count = _upsert_album_tracks_from_spotify(album_key, spotify_album)
                            album_state["track_count"] = count
                            album_state["total_tracks"] = count
            elif not total_tracks or total_tracks == 0:
                supabase.table('last_fm_albums').update({
                    'total_tracks': track_count
                }).eq('album_key', album_key).execute()
                album_state["total_tracks"] = track_count

        # Record listened track
        supabase.table('last_fm_listened_tracks').upsert({
            'lastfm_username': username,
            'played_at': played_at.isoformat(),
            'track_name': track_name,
            'track_name_normalized': track_name_normalized,
            'artist_name': artist_name,
            'album_name': canonical_album_name,
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


def get_album_tracks(username, album_key):
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

def backfill_track_name_normalization(dry_run=False, batch_size=1000, lastfm_username=None):
    """
    One-time function to backfill normalized track names for matching.
    """
    scope_label = lastfm_username or "all users"
    print(
        "Backfilling normalized track names "
        f"with batch_size={batch_size} scope={scope_label}."
    )
    album_track_updates = 0
    album_track_checked = 0
    album_offset = 0
    if lastfm_username:
        print(
            "Skipping last_fm_album_tracks normalization for user-scoped run "
            "because album tracks are shared across users."
        )
    else:
        while True:
            tracks_resp = supabase.table('last_fm_album_tracks')\
                .select('album_key, track_number, track_name, track_name_normalized')\
                .order('album_key')\
                .order('track_number')\
                .range(album_offset, album_offset + batch_size - 1)\
                .execute()
            tracks = tracks_resp.data or []
            if not tracks:
                break
            album_track_checked += len(tracks)
            for row in tracks:
                normalized = _normalize_track_name(row.get("track_name"))
                if normalized and normalized != row.get("track_name_normalized"):
                    album_track_updates += 1
                    if dry_run:
                        print(
                            "[dry-run] last_fm_album_tracks "
                            f"album_key={row.get('album_key')} "
                            f"track_number={row.get('track_number')} "
                            f"{row.get('track_name_normalized')} -> {normalized}"
                        )
                        continue
                    supabase.table('last_fm_album_tracks').update({
                        'track_name_normalized': normalized
                    }).eq('album_key', row.get('album_key'))\
                     .eq('track_number', row.get('track_number'))\
                     .execute()
            if len(tracks) < batch_size:
                break
            album_offset += batch_size

    listened_track_updates = 0
    listened_track_checked = 0
    listen_offset = 0
    while True:
        listens_query = supabase.table('last_fm_listened_tracks')\
            .select('lastfm_username, played_at, track_name, album_name, track_name_normalized')\
            .order('lastfm_username')\
            .order('played_at')\
            .order('track_name')\
            .range(listen_offset, listen_offset + batch_size - 1)
        if lastfm_username:
            listens_query = listens_query.eq('lastfm_username', lastfm_username)
        listens_resp = listens_query.execute()
        listens = listens_resp.data or []
        if not listens:
            break
        listened_track_checked += len(listens)
        for row in listens:
            normalized = _normalize_track_name(
                row.get("track_name"),
                album_name=row.get("album_name"),
            )
            if normalized and normalized != row.get("track_name_normalized"):
                listened_track_updates += 1
                if dry_run:
                    print(
                        "[dry-run] last_fm_listened_tracks "
                        f"user={row.get('lastfm_username')} "
                        f"played_at={row.get('played_at')} "
                        f"{row.get('track_name_normalized')} -> {normalized}"
                    )
                    continue
                supabase.table('last_fm_listened_tracks').update({
                    'track_name_normalized': normalized
                }).eq('lastfm_username', row.get('lastfm_username'))\
                 .eq('played_at', row.get('played_at'))\
                 .eq('track_name', row.get('track_name'))\
                 .execute()
        if len(listens) < batch_size:
            break
        listen_offset += batch_size

    if dry_run:
        print(
            "Dry run complete. "
            f"Checked {album_track_checked} album tracks and "
            f"{listened_track_checked} listened tracks. "
            f"Would update {album_track_updates} album tracks and "
            f"{listened_track_updates} listened tracks."
        )
    else:
        print(
            "Track-name normalization backfill complete. "
            f"Checked {album_track_checked} album tracks and "
            f"{listened_track_checked} listened tracks. "
            f"Updated {album_track_updates} album tracks and "
            f"{listened_track_updates} listened tracks."
        )


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _int_or_zero(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _split_album_key(album_key):
    if not album_key or "::" not in album_key:
        return None, None
    artist_name, album_name = album_key.split("::", 1)
    return artist_name.strip() or None, album_name.strip() or None


def _merge_lastfm_album_track_rows(target_rows, source_rows, new_key):
    merged = {}
    collisions = 0

    for row in target_rows or []:
        track_number = row.get("track_number")
        if track_number is None:
            continue
        merged[track_number] = {
            "album_key": new_key,
            "track_number": track_number,
            "track_name": row.get("track_name"),
            "track_name_normalized": row.get("track_name_normalized"),
            "track_url": row.get("track_url"),
            "duration_sec": row.get("duration_sec"),
        }

    for row in source_rows or []:
        track_number = row.get("track_number")
        if track_number is None:
            continue
        candidate = {
            "album_key": new_key,
            "track_number": track_number,
            "track_name": row.get("track_name"),
            "track_name_normalized": row.get("track_name_normalized"),
            "track_url": row.get("track_url"),
            "duration_sec": row.get("duration_sec"),
        }
        existing = merged.get(track_number)
        if not existing:
            merged[track_number] = candidate
            continue
        collisions += 1
        for field in ("track_name", "track_name_normalized", "track_url", "duration_sec"):
            if _is_blank(existing.get(field)) and not _is_blank(candidate.get(field)):
                existing[field] = candidate.get(field)

    return [merged[idx] for idx in sorted(merged.keys())], collisions


def _merge_lastfm_track_artist_rows(target_rows, source_rows, new_key):
    merged = {}
    collisions = 0

    for row in target_rows or []:
        track_number = row.get("track_number")
        artist_order = row.get("artist_order")
        if track_number is None or artist_order is None:
            continue
        merged[(track_number, artist_order)] = {
            "album_key": new_key,
            "track_number": track_number,
            "artist_name": row.get("artist_name"),
            "artist_order": artist_order,
        }

    for row in source_rows or []:
        track_number = row.get("track_number")
        artist_order = row.get("artist_order")
        if track_number is None or artist_order is None:
            continue
        key = (track_number, artist_order)
        candidate = {
            "album_key": new_key,
            "track_number": track_number,
            "artist_name": row.get("artist_name"),
            "artist_order": artist_order,
        }
        existing = merged.get(key)
        if not existing:
            merged[key] = candidate
            continue
        collisions += 1
        if _is_blank(existing.get("artist_name")) and not _is_blank(candidate.get("artist_name")):
            existing["artist_name"] = candidate.get("artist_name")

    return [merged[idx] for idx in sorted(merged.keys())], collisions


def _merge_lastfm_album_rows(target_row, source_row, new_key, canonical_artist, canonical_album_name):
    metadata_fields = (
        "album_url",
        "listeners",
        "playcount",
        "image_small",
        "image_medium",
        "image_large",
        "image_extralarge",
        "image_mega",
    )
    merged = {}

    if target_row:
        merged.update(target_row)
    if source_row:
        for field, value in source_row.items():
            if field not in merged or _is_blank(merged.get(field)):
                merged[field] = value

    merged["album_key"] = new_key
    merged["artist_name"] = canonical_artist or merged.get("artist_name")
    merged["album_name"] = canonical_album_name or merged.get("album_name")

    for field in metadata_fields:
        target_value = target_row.get(field) if target_row else None
        source_value = source_row.get(field) if source_row else None
        merged[field] = target_value if not _is_blank(target_value) else source_value

    total_tracks = max(
        _int_or_zero(target_row.get("total_tracks") if target_row else 0),
        _int_or_zero(source_row.get("total_tracks") if source_row else 0),
    )
    merged["total_tracks"] = total_tracks if total_tracks > 0 else None

    return merged


def _ensure_lastfm_artist_exists(artist_name, dry_run=False, context_label=None):
    artist_name = _clean_text(artist_name)
    if not artist_name:
        return
    if dry_run:
        if context_label:
            print(
                "[dry-run] ensure last_fm_artists row "
                f"artist={artist_name} context={context_label}"
            )
        return
    supabase.table('last_fm_artists').upsert({
        'artist_name': artist_name
    }).execute()


def backfill_canonical_lastfm_album_keys(
    lastfm_username=None,
    dry_run=False,
    batch_size=500,
    limit=None,
    sleep_s=0.25,
):
    """
    Recompute canonical album keys for listened tracks and migrate related Last.fm tables.
    """
    mode = "dry-run" if dry_run else "apply"
    scope = lastfm_username or "ALL users"
    print(
        "[last_fm_album_tracking] canonical album-key backfill "
        f"mode={mode} scope={scope} batch_size={batch_size} limit={limit}"
    )
    if lastfm_username:
        print(
            "[last_fm_album_tracking] note: --lastfm-username scopes mismatch discovery only; "
            "migrations for touched keys apply across all users."
        )

    identity_cache = {}
    key_votes = {}
    pair_meta = {}
    scanned_rows = 0
    offset = 0
    stopped_by_limit = False

    while True:
        query = supabase.table('last_fm_listened_tracks')\
            .select('lastfm_username, played_at, track_name, artist_name, album_name, album_key')\
            .order('lastfm_username')\
            .order('played_at')\
            .order('track_name')\
            .range(offset, offset + batch_size - 1)
        if lastfm_username:
            query = query.eq('lastfm_username', lastfm_username)
        listens_resp = query.execute()
        rows = listens_resp.data or []
        if not rows:
            break

        for row in rows:
            if limit and scanned_rows >= limit:
                stopped_by_limit = True
                break
            scanned_rows += 1
            current_key = row.get("album_key")
            artist_name = row.get("artist_name")
            album_name = row.get("album_name")
            track_name = row.get("track_name")
            if not current_key or not artist_name or not album_name:
                continue

            canonical = resolve_canonical_lastfm_album_identity(
                artist_name,
                album_name,
                track_name,
                cache=identity_cache,
            )
            expected_key = canonical.get("album_key")
            if not expected_key or expected_key == current_key:
                continue

            votes = key_votes.setdefault(current_key, {})
            votes[expected_key] = votes.get(expected_key, 0) + 1
            pair_meta[(current_key, expected_key)] = {
                "artist_name": canonical.get("artist_name"),
                "album_name": canonical.get("album_name") or album_name,
                "source": canonical.get("source"),
            }

        if stopped_by_limit or len(rows) < batch_size:
            break
        offset += batch_size

    if not key_votes:
        print(
            "[last_fm_album_tracking] canonical album-key backfill: "
            f"no mismatched keys found after scanning {scanned_rows} listened rows."
        )
        return

    raw_mapping = {}
    mapping_collisions = 0
    for old_key, candidates in key_votes.items():
        ranked = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
        best_new_key, best_votes = ranked[0]
        raw_mapping[old_key] = best_new_key
        if len(ranked) > 1:
            mapping_collisions += 1
            alternatives = ", ".join([f"{key}:{votes}" for key, votes in ranked[:3]])
            print(
                "[last_fm_album_tracking] canonical mapping collision "
                f"old={old_key} picked={best_new_key}:{best_votes} candidates={alternatives}"
            )

    def _final_key_for(key):
        visited = set()
        current = key
        while current in raw_mapping and raw_mapping[current] != current and current not in visited:
            visited.add(current)
            current = raw_mapping[current]
        return current

    key_mapping = {}
    mapping_meta = {}
    for old_key in raw_mapping.keys():
        final_key = _final_key_for(old_key)
        if final_key == old_key:
            continue
        key_mapping[old_key] = final_key
        direct_meta = pair_meta.get((old_key, final_key), {})
        artist_from_key, album_from_key = _split_album_key(final_key)
        mapping_meta[old_key] = {
            "artist_name": direct_meta.get("artist_name") or artist_from_key,
            "album_name": direct_meta.get("album_name") or album_from_key,
            "source": direct_meta.get("source") or "derived",
        }

    if not key_mapping:
        print(
            "[last_fm_album_tracking] canonical album-key backfill: "
            "all detected mappings collapsed to identity (no changes)."
        )
        return

    summary = {
        "scanned_rows": scanned_rows,
        "mappings": len(key_mapping),
        "mapping_collisions": mapping_collisions,
        "listened_rows_updated": 0,
        "album_track_rows_migrated": 0,
        "album_track_collisions": 0,
        "track_artist_rows_migrated": 0,
        "track_artist_collisions": 0,
        "album_rows_migrated": 0,
        "album_rows_retained": 0,
    }

    print(
        "[last_fm_album_tracking] canonical album-key backfill will process "
        f"{len(key_mapping)} key migrations."
    )

    for old_key, new_key in sorted(key_mapping.items()):
        meta = mapping_meta.get(old_key, {})
        canonical_artist = meta.get("artist_name")
        canonical_album_name = meta.get("album_name")
        source_label = meta.get("source")

        print(
            "[last_fm_album_tracking] migrating album_key "
            f"old={old_key} new={new_key} source={source_label}"
        )

        # Ensure target album row exists before updating FK-bound dependent tables.
        album_fields = (
            'album_key, album_name, artist_name, album_url, listeners, playcount, '
            'image_small, image_medium, image_large, image_extralarge, image_mega, total_tracks'
        )
        source_album_resp = supabase.table('last_fm_albums')\
            .select(album_fields)\
            .eq('album_key', old_key)\
            .limit(1)\
            .execute()
        target_album_resp = supabase.table('last_fm_albums')\
            .select(album_fields)\
            .eq('album_key', new_key)\
            .limit(1)\
            .execute()
        source_album = source_album_resp.data[0] if source_album_resp.data else None
        target_album = target_album_resp.data[0] if target_album_resp.data else None

        if not target_album:
            base_artist, base_album_name = _split_album_key(new_key)
            seed_artist = canonical_artist or base_artist
            seed_album_name = canonical_album_name or base_album_name
            _ensure_lastfm_artist_exists(
                seed_artist,
                dry_run=dry_run,
                context_label=f"seed album {new_key}",
            )
            if dry_run:
                print(
                    "[dry-run] ensure last_fm_albums target row "
                    f"old={old_key} new={new_key} source_exists={bool(source_album)}"
                )
            else:
                if source_album:
                    seed_album = _merge_lastfm_album_rows(
                        None,
                        source_album,
                        new_key,
                        seed_artist,
                        seed_album_name,
                    )
                else:
                    seed_album = {
                        "album_key": new_key,
                        "artist_name": seed_artist,
                        "album_name": seed_album_name,
                    }
                supabase.table('last_fm_albums').upsert(seed_album).execute()

        # 1) Move listened rows first (optionally scoped to one username)
        listened_query = supabase.table('last_fm_listened_tracks')\
            .select('lastfm_username, played_at, track_name')\
            .eq('album_key', old_key)
        listened_rows = listened_query.execute().data or []
        listened_count = len(listened_rows)
        summary["listened_rows_updated"] += listened_count
        targeted_listened_count = None
        if lastfm_username:
            targeted_listened_rows = supabase.table('last_fm_listened_tracks')\
                .select('lastfm_username, played_at, track_name')\
                .eq('album_key', old_key)\
                .eq('lastfm_username', lastfm_username)\
                .execute().data or []
            targeted_listened_count = len(targeted_listened_rows)

        if dry_run:
            if listened_count:
                if targeted_listened_count is None:
                    print(
                        f"[dry-run] last_fm_listened_tracks old={old_key} new={new_key} rows={listened_count}"
                    )
                else:
                    print(
                        "[dry-run] last_fm_listened_tracks "
                        f"old={old_key} new={new_key} rows_total={listened_count} "
                        f"rows_targeted_user={targeted_listened_count}"
                    )
        elif listened_count:
            update_query = supabase.table('last_fm_listened_tracks').update({'album_key': new_key})\
                .eq('album_key', old_key)
            update_query.execute()

        # 2) Merge album tracks by track_number
        source_tracks = supabase.table('last_fm_album_tracks')\
            .select('album_key, track_number, track_name, track_name_normalized, track_url, duration_sec')\
            .eq('album_key', old_key)\
            .execute().data or []
        target_tracks = supabase.table('last_fm_album_tracks')\
            .select('album_key, track_number, track_name, track_name_normalized, track_url, duration_sec')\
            .eq('album_key', new_key)\
            .execute().data or []
        if source_tracks:
            merged_tracks, track_collisions = _merge_lastfm_album_track_rows(
                target_tracks,
                source_tracks,
                new_key,
            )
            summary["album_track_rows_migrated"] += len(source_tracks)
            summary["album_track_collisions"] += track_collisions
            if dry_run:
                print(
                    "[dry-run] last_fm_album_tracks "
                    f"old={old_key} new={new_key} source_rows={len(source_tracks)} "
                    f"merged_rows={len(merged_tracks)} collisions={track_collisions}"
                )
            else:
                if merged_tracks:
                    supabase.table('last_fm_album_tracks').upsert(merged_tracks).execute()
                supabase.table('last_fm_album_tracks').delete().eq('album_key', old_key).execute()

        # 3) Merge track artists by (track_number, artist_order)
        source_track_artists = supabase.table('last_fm_track_artists')\
            .select('album_key, track_number, artist_name, artist_order')\
            .eq('album_key', old_key)\
            .execute().data or []
        target_track_artists = supabase.table('last_fm_track_artists')\
            .select('album_key, track_number, artist_name, artist_order')\
            .eq('album_key', new_key)\
            .execute().data or []
        if source_track_artists:
            merged_track_artists, track_artist_collisions = _merge_lastfm_track_artist_rows(
                target_track_artists,
                source_track_artists,
                new_key,
            )
            summary["track_artist_rows_migrated"] += len(source_track_artists)
            summary["track_artist_collisions"] += track_artist_collisions
            if dry_run:
                print(
                    "[dry-run] last_fm_track_artists "
                    f"old={old_key} new={new_key} source_rows={len(source_track_artists)} "
                    f"merged_rows={len(merged_track_artists)} collisions={track_artist_collisions}"
                )
            else:
                if merged_track_artists:
                    supabase.table('last_fm_track_artists').upsert(merged_track_artists).execute()
                supabase.table('last_fm_track_artists').delete().eq('album_key', old_key).execute()

        # 4) Merge album metadata row itself
        album_fields = (
            'album_key, album_name, artist_name, album_url, listeners, playcount, '
            'image_small, image_medium, image_large, image_extralarge, image_mega, total_tracks'
        )
        source_album_resp = supabase.table('last_fm_albums')\
            .select(album_fields)\
            .eq('album_key', old_key)\
            .limit(1)\
            .execute()
        target_album_resp = supabase.table('last_fm_albums')\
            .select(album_fields)\
            .eq('album_key', new_key)\
            .limit(1)\
            .execute()
        source_album = source_album_resp.data[0] if source_album_resp.data else None
        target_album = target_album_resp.data[0] if target_album_resp.data else None
        if source_album or target_album:
            merged_album = _merge_lastfm_album_rows(
                target_album,
                source_album,
                new_key,
                canonical_artist,
                canonical_album_name,
            )
            if source_album:
                summary["album_rows_migrated"] += 1
            if dry_run:
                print(
                    "[dry-run] last_fm_albums "
                    f"old={old_key} new={new_key} source_exists={bool(source_album)} "
                    f"target_exists={bool(target_album)}"
                )
            else:
                _ensure_lastfm_artist_exists(
                    merged_album.get("artist_name"),
                    dry_run=False,
                    context_label=f"merge album {new_key}",
                )
                supabase.table('last_fm_albums').upsert(merged_album).execute()
                if source_album:
                    remaining_refs = supabase.table('last_fm_listened_tracks')\
                        .select('lastfm_username')\
                        .eq('album_key', old_key)\
                        .limit(1)\
                        .execute().data or []
                    if remaining_refs:
                        summary["album_rows_retained"] += 1
                        print(
                            "[last_fm_album_tracking] retaining old album row due to remaining refs "
                            f"old={old_key}"
                        )
                    else:
                        supabase.table('last_fm_albums').delete().eq('album_key', old_key).execute()

        if sleep_s:
            time.sleep(sleep_s)

    prefix = "Would update" if dry_run else "Updated"
    print(
        "[last_fm_album_tracking] canonical album-key backfill complete. "
        f"Scanned {summary['scanned_rows']} listened rows. "
        f"Mappings={summary['mappings']} collisions={summary['mapping_collisions']}. "
        f"{prefix} listened_rows={summary['listened_rows_updated']} "
        f"album_track_rows={summary['album_track_rows_migrated']} "
        f"album_track_collisions={summary['album_track_collisions']} "
        f"track_artist_rows={summary['track_artist_rows_migrated']} "
        f"track_artist_collisions={summary['track_artist_collisions']} "
        f"album_rows={summary['album_rows_migrated']} "
        f"album_rows_retained={summary['album_rows_retained']}."
    )


def backfill_missing_lastfm_tracks(album_key=None, limit=None, sleep_s=0.25, dry_run=False):
    """
    One-time function to backfill tracklists for albums missing tracks or total_tracks.
    """
    query = supabase.table('last_fm_albums')\
        .select('album_key, album_name, artist_name, total_tracks')
    if album_key:
        query = query.eq('album_key', album_key)
    if limit:
        query = query.limit(limit)
    albums = query.execute()

    rows = albums.data or []
    if not rows:
        print("No albums found.")
        return

    print(f"Found {len(rows)} albums to check for missing tracks.")
    seen_artists = set()
    for album in rows:
        album_key = album.get("album_key")
        album_name = album.get("album_name")
        artist_name = album.get("artist_name")
        total_tracks = album.get("total_tracks") or 0
        track_count = _get_album_track_count(album_key)

        if total_tracks > 0 and track_count > 0:
            continue

        if dry_run:
            print(f"[dry-run] Would backfill {album_name} by {artist_name} (album_key={album_key})")
            continue

        try:
            album_info = _lastfm_get({
                "method": "album.getinfo",
                "artist": artist_name,
                "album": album_name
            })
            album_data = album_info.get("album", {})
            tracks_data = album_data.get("tracks", {})
            tracks = tracks_data.get("track", [])
            if isinstance(tracks, dict):
                tracks = [tracks]

            if tracks:
                count = _insert_lastfm_album_tracks(album_key, tracks, artist_name, seen_artists)
                supabase.table('last_fm_albums').update({
                    'total_tracks': count
                }).eq('album_key', album_key).execute()
                print(f"Backfilled tracks from Last.fm for {album_name} by {artist_name}")
                if sleep_s:
                    time.sleep(sleep_s)
                continue
        except Exception as e:
            print(f"Error fetching Last.fm tracks for {album_name} by {artist_name}: {e}")

        spotify_album = _spotify_find_album(artist_name, album_name)
        if spotify_album:
            count = _upsert_album_tracks_from_spotify(album_key, spotify_album)
            if count:
                print(f"Backfilled tracks from Spotify for {album_name} by {artist_name}")
        if sleep_s:
            time.sleep(sleep_s)
