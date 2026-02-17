import argparse

from env import load_environment
from last_fm_album_tracking import backfill_missing_lastfm_tracks


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Last.fm album tracklists using Last.fm or Spotify fallback."
    )
    parser.add_argument(
        "--album-key",
        help="Only backfill a single album_key (e.g. 'keshi::requiem').",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of albums to process.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.25,
        help="Seconds to sleep between albums (default: 0.25).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be processed without making changes.",
    )
    args = parser.parse_args()

    backfill_missing_lastfm_tracks(
        album_key=args.album_key,
        limit=args.limit,
        sleep_s=args.sleep,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    load_environment()
    main()
