from datetime import datetime
import argparse

from env import load_environment


def _parse_spotify_release_date(release_date, precision):
    if not release_date:
        return None
    try:
        if precision == "year":
            return datetime(int(release_date), 1, 1)
        if precision == "month":
            year, month = release_date.split("-")
            return datetime(int(year), int(month), 1)
        return datetime.fromisoformat(release_date)
    except Exception:
        return None


def resolve_album_for_track(
    artist_name,
    track_name,
    *,
    lastfm_get,
    spotify_client,
    normalize_track_name,
    normalize_artist_name,
    track_name_normalized=None,
    return_artist=False,
):
    if not artist_name or not track_name:
        return (None, None) if return_artist else None

    try:
        track_info = lastfm_get({
            "method": "track.getInfo",
            "artist": artist_name,
            "track": track_name
        })
        track_data = track_info.get("track", {}) if isinstance(track_info, dict) else {}
        album_data = track_data.get("album", {}) if isinstance(track_data, dict) else {}
        album_title = album_data.get("title") or album_data.get("name")
        album_artist = album_data.get("artist")
        if isinstance(album_artist, dict):
            album_artist = album_artist.get("name") or album_artist.get("#text")
        if album_title:
            if return_artist:
                return album_title, album_artist
            return album_title
    except Exception as exc:
        print(f"Error fetching track info for {track_name} by {artist_name}: {exc}")

    sp = spotify_client()
    if not sp:
        return (None, None) if return_artist else None

    query = f"track:{track_name} artist:{artist_name}"
    try:
        results = sp.search(q=query, type="track", limit=10)
    except Exception as exc:
        print(f"[last_fm_album_tracking] Spotify track search failed for {artist_name} - {track_name}: {exc}")
        return None

    tracks = results.get("tracks", {}).get("items", []) if isinstance(results, dict) else []
    target_track_norm = track_name_normalized or normalize_track_name(track_name)
    target_artist_norm = normalize_artist_name(artist_name)

    candidates = []
    for item in tracks:
        if normalize_track_name(item.get("name")) != target_track_norm:
            continue
        artists = item.get("artists") or []
        if not any(normalize_artist_name(artist.get("name")) == target_artist_norm for artist in artists):
            continue
        album = item.get("album") or {}
        album_type = (album.get("album_type") or "").lower()
        if album_type != "album":
            continue
        release_dt = _parse_spotify_release_date(
            album.get("release_date"),
            album.get("release_date_precision"),
        )
        album_artists = album.get("artists") or []
        album_artist_name = None
        if album_artists:
            album_artist_name = (album_artists[0] or {}).get("name")
        candidates.append((release_dt, album.get("name"), album_artist_name))

    if not candidates:
        return (None, None) if return_artist else None

    candidates.sort(key=lambda item: item[0] or datetime.max)
    best_match = candidates[0]
    if return_artist:
        return best_match[1], best_match[2]
    return best_match[1]


def _cli():
    parser = argparse.ArgumentParser(
        description="Resolve a single track to an album using Last.fm + Spotify fallback."
    )
    parser.add_argument("--artist", required=True, help="Artist name")
    parser.add_argument("--track", required=True, help="Track name")
    args = parser.parse_args()

    from last_fm_album_tracking import (
        _lastfm_get,
        _get_spotify_app_client,
        _normalize_track_name,
        _normalize_artist_name,
    )

    album = resolve_album_for_track(
        args.artist,
        args.track,
        lastfm_get=_lastfm_get,
        spotify_client=_get_spotify_app_client,
        normalize_track_name=_normalize_track_name,
        normalize_artist_name=_normalize_artist_name,
    )
    if album:
        print(album)
    else:
        print("No confident album match found.")


if __name__ == "__main__":
    load_environment()
    _cli()
