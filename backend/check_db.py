#!/usr/bin/env python3
# check_db.py - Run this to check database status

import sqlite3
import os
from pathlib import Path

db_path = "cb_meetings.db"

print(f"Checking database: {db_path}")
print(f"Database exists: {Path(db_path).exists()}")
print(f"Database size: {os.path.getsize(db_path) if Path(db_path).exists() else 0} bytes")

# Check for WAL files
wal_path = f"{db_path}-wal"
shm_path = f"{db_path}-shm"
print(f"WAL file exists: {Path(wal_path).exists()}")
print(f"SHM file exists: {Path(shm_path).exists()}")

try:
    # Try to connect
    conn = sqlite3.connect(db_path, timeout=5.0)
    print("✓ Successfully connected to database")
    
    # Check journal mode
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    print(f"Journal mode: {mode}")
    
    # Count videos
    cursor.execute("SELECT COUNT(*) FROM processed_videos")
    total_videos = cursor.fetchone()[0]
    print(f"Total videos: {total_videos}")
    
    # Count by status
    cursor.execute("SELECT status, COUNT(*) FROM processed_videos GROUP BY status")
    status_counts = cursor.fetchall()
    print("Videos by status:")
    for status, count in status_counts:
        print(f"  {status}: {count}")
    
    # Check CB7 specifically
    cursor.execute("SELECT COUNT(*) FROM processed_videos WHERE cb_number = 7")
    cb7_count = cursor.fetchone()[0]
    print(f"CB7 videos: {cb7_count}")
    
    # Check if any are being processed
    cursor.execute("SELECT video_id, title FROM processed_videos WHERE status = 'processing' LIMIT 5")
    processing = cursor.fetchall()
    if processing:
        print("\nCurrently processing:")
        for vid, title in processing:
            print(f"  {vid}: {title[:50]}...")
    
    conn.close()
    print("\n✓ Database check complete")
    
except Exception as e:
    print(f"\n✗ Database error: {e}")
    import traceback
    traceback.print_exc()