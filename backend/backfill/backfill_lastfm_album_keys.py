import argparse

from env import load_environment
from last_fm_album_tracking import backfill_canonical_lastfm_album_keys


def main():
    parser = argparse.ArgumentParser(
        description="Backfill canonical Last.fm album keys across listened/albums/tracks tables."
    )
    parser.add_argument(
        "--lastfm-username",
        help="Only discover mismatched keys from a single Last.fm username.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Page size for scanning listened rows (default: 500).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional cap on listened rows scanned while discovering mismatches.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.25,
        help="Seconds to sleep between key migrations (default: 0.25).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned key migrations without writing changes.",
    )
    args = parser.parse_args()

    backfill_canonical_lastfm_album_keys(
        lastfm_username=args.lastfm_username,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        limit=args.limit,
        sleep_s=args.sleep,
    )


if __name__ == "__main__":
    load_environment()
    main()
