import time
from datetime import datetime
from album_tracking import track_all_users_recently_listened

print("Cron job starting...")
while True:
    print(f"Running task at {datetime.now()}")
    try:
        track_all_users_recently_listened()
        print("Task completed successfully")
    except Exception as e:
        print(f"Error running task: {e}")
        
        # Sleep for 60 seconds to avoid running multiple times in the same minute
        time.sleep(60)
    
    # Check every 30 seconds
    time.sleep(30)