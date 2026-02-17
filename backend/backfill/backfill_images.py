import os
import time
import argparse

import spotipy
from supabase import create_client, Client

from env import load_environment
from validate_token import get_valid_token

load_environment()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_API_KEY"))

def backfill_artist_genres(batch_size: int = 50, sleep_seconds: float = 0.15) -> None:
    """
    One-time function to backfill artist genres from Spotify.
    """
    users = supabase.table("users").select("user_id").limit(1).execute()
    if not users.data:
        print("No users found.")
        return

    user_id = users.data[0]["user_id"]
    decrypted_token = get_valid_token(user_id)
    if not decrypted_token:
        print("Could not get valid token.")
        return

    sp = spotipy.Spotify(auth=decrypted_token)

    offset = 0
    updated = 0
    while True:
        response = (
            supabase.table("artists")
            .select("artist_id, genres")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        rows = response.data or []
        if not rows:
            break

        for row in rows:
            artist_id = row.get("artist_id")
            if not artist_id:
                continue

            existing_genres = row.get("genres")
            if existing_genres:
                continue

            try:
                artist = sp.artist(artist_id)
                genres = artist.get("genres", [])
                supabase.table("artists").update({"genres": genres}).eq("artist_id", artist_id).execute()
                updated += 1
            except Exception as exc:
                print(f"Error updating {artist_id}: {exc}")

            time.sleep(sleep_seconds)

        offset += batch_size

    print(f"Updated {updated} artists.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill helper tasks for album/image and Last.fm data."
    )
    parser.add_argument(
        "--track-name-normalization",
        action="store_true",
        help="Backfill track_name_normalized values in Last.fm tables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print pending normalization updates without writing changes.",
    )
    parser.add_argument(
        "--normalization-batch-size",
        type=int,
        default=1000,
        help="Page size for track-name normalization backfill (default: 1000).",
    )
    parser.add_argument(
        "--lastfm-username",
        help="Only normalize listened-track rows for a specific Last.fm username.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for artist genres backfill (default: 50).",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.15,
        help="Seconds to sleep between Spotify artist requests (default: 0.15).",
    )
    args = parser.parse_args()

    if args.track_name_normalization:
        from last_fm_album_tracking import backfill_track_name_normalization

        backfill_track_name_normalization(
            dry_run=args.dry_run,
            batch_size=args.normalization_batch_size,
            lastfm_username=args.lastfm_username,
        )
        return

    backfill_artist_genres(batch_size=args.batch_size, sleep_seconds=args.sleep_seconds)


if __name__ == "__main__":
    main()
