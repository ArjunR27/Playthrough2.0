from datetime import datetime

from last_fm_album_tracking import get_recently_listened

LASTFM_USERNAME = "taper27"


def main():
    print("Cron job starting...")
    print(f"Running task at {datetime.now()}")
    print(f"[cron][lastfm] Starting recent listens for username={LASTFM_USERNAME}")

    try:
        get_recently_listened(LASTFM_USERNAME, log_tracks=True)
        print(f"[cron][lastfm] username={LASTFM_USERNAME} done")
        print("Task completed successfully")
    except Exception as exc:
        print(f"[cron][lastfm] username={LASTFM_USERNAME} error: {exc}")
        raise


if __name__ == "__main__":
    main()
