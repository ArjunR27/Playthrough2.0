import os
import time

import spotipy
from supabase import create_client, Client

from album_tracking import backfill_album_images
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

if __name__ == "__main__":
    backfill_artist_genres()
