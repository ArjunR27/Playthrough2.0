from album_tracking import backfill_album_images
from last_fm_album_tracking import backfill_album_info, backfill_artist_info

if __name__ == "__main__":
    backfill_album_info()
    backfill_artist_info()
