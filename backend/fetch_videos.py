import yt_dlp
import sqlite3
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import re
import traceback
import contextlib
import time

logger = logging.getLogger(__name__)

class CBChannelFetcher:
    """Fetch and track videos from Community Board YouTube channels"""
    
    CB_CHANNELS = {
        'cb7': {
            'name': 'Manhattan CB7', 'url': 'https://www.youtube.com/@manhattancbseven4610',
            'channel_id': '@manhattancbseven4610', 'district': 'Manhattan', 'number': 7
        },
        **{f'cb{i}': {'name': f'Manhattan CB{i}', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': i} 
           for i in list(range(1, 7)) + list(range(8, 13))}
    }
    
    def __init__(self, db_path: str = "cb_meetings.db"):
        self.db_path = Path(db_path)

    @contextlib.contextmanager
    def get_db_connection(self, read_only=False):
        """Provides a database connection as a context manager."""
        conn = None
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                if read_only:
                    db_uri = f"file:{self.db_path}?mode=ro&immutable=1"
                    conn = sqlite3.connect(db_uri, uri=True, timeout=30.0)
                else:
                    conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level='IMMEDIATE')
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=30000")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=10000")
                    conn.execute("PRAGMA temp_store=MEMORY")
                
                conn.row_factory = sqlite3.Row
                yield conn
                
                if not read_only:
                    conn.commit()
                break
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and retry_count < max_retries - 1:
                    retry_count += 1
                    if conn:
                        conn.close()
                    time.sleep(0.5 * retry_count)
                    continue
                else:
                    logger.error(f"Database error in CBChannelFetcher: {e}")
                    raise
            except Exception as e:
                logger.error(f"Database error in CBChannelFetcher: {e}")
                if conn and not read_only:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()

    def fetch_channel_videos(self, cb_key: str, max_results: int = 50) -> List[Dict]:
        """Fetch recent videos from a CB channel"""
        cb_info = self.CB_CHANNELS.get(cb_key)
        if not cb_info or not cb_info['url']:
            return []
        
        ydl_opts = {'quiet': True, 'extract_flat': True, 'playlist_items': f'1-{max_results}'}
        videos = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(f"{cb_info['url']}/videos", download=False)
                if 'entries' in result:
                    for entry in result.get('entries', []):
                        if entry and 'id' in entry and self.is_meeting_video(entry.get('title', '')):
                            videos.append({
                                'video_id': entry['id'], 'title': entry.get('title', ''),
                                'url': f"https://www.youtube.com/watch?v={entry['id']}",
                                'duration': entry.get('duration', 0),
                                'upload_date': entry.get('upload_date', ''),
                                'cb_number': cb_info['number'], 'cb_district': cb_info['district'],
                                'channel_source': cb_key
                            })
        except Exception as e:
            logger.error(f"Failed to fetch videos from {cb_key}: {e}")
        return videos
    
    def is_meeting_video(self, title: str) -> bool:
        """Check if video title suggests it's a meeting"""
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in ['highlights', 'summary', 'clip']): return False
        return any(keyword in title_lower for keyword in ['meeting', 'committee', 'board', 'session', 'hearing'])
    
    def save_video_info(self, video: Dict) -> bool:
        """Save video info to database if not already processed"""
        try:
            with self.get_db_connection() as conn:
                existing = conn.execute('SELECT video_id FROM processed_videos WHERE video_id = ?', (video['video_id'],)).fetchone()
                if existing: return False
                
                upload_date = datetime.strptime(video.get('upload_date'), '%Y%m%d').isoformat() if video.get('upload_date') else None
                conn.execute('''
                    INSERT INTO processed_videos 
                    (video_id, title, url, published_at, cb_number, cb_district, channel_source, duration, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                ''', (
                    video['video_id'], video['title'], video['url'], upload_date,
                    video['cb_number'], video['cb_district'], video['channel_source'], video.get('duration', 0)
                ))
            logger.info(f"Saved new video: {video['title'][:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to save video {video['video_id']}: {e}")
            return False
    
    def get_pending_videos(self, cb_number: Optional[int] = None, limit: int = 10) -> List[Dict]:
        try:
            with self.get_db_connection(read_only=True) as conn:
                # Consider videos stuck if processing for more than 30 minutes
                thirty_minutes_ago = (datetime.now() - timedelta(minutes=30)).isoformat()
                
                query = """
                    SELECT * FROM processed_videos 
                    WHERE (
                        status = 'pending' 
                        OR status = 'queued'
                        OR (status = 'processing' AND processed_at < ?)
                        OR (status = 'failed' AND processing_attempts < 3)
                    )
                    AND processing_attempts < 3
                """
                params = [thirty_minutes_ago]
                
                if cb_number:
                    query += ' AND cb_number = ?'
                    params.append(cb_number)
                
                query += ' ORDER BY published_at DESC LIMIT ?'
                params.append(limit)
                
                rows = conn.execute(query, params).fetchall()
                
                videos = []
                for row in rows:
                    video_dict = dict(row)
                    # Add a flag to indicate if this is a retry
                    if video_dict['status'] == 'processing':
                        video_dict['is_stuck'] = True
                    videos.append(video_dict)
                    
                if videos:
                    logger.info(f"Found {len(videos)} pending/stuck videos to process")
                    
                return videos
        except Exception as e:
            logger.error(f"Failed to get pending videos: {e}")
            return []

    def get_processed_meetings_by_cb(self, cb_number: int, limit: int = 20) -> List[Dict]:
        """Get all meetings for a specific CB, sorted correctly."""
        logger.info(f"Fetching meetings for CB{cb_number} with corrected sorting")
        try:
            with self.get_db_connection(read_only=True) as conn:
                # *** THIS IS THE FIX ***
                # Use COALESCE to sort by meeting_date, falling back to published_at if it's NULL.
                # This ensures a consistent and correct order for all meetings.
                rows = conn.execute('''
                    SELECT 
                        p.video_id, p.title, p.url, p.published_at, p.processed_at,
                        p.status, p.cb_number, p.error_message,
                        m.analysis_json, m.transcript_length, m.meeting_date
                    FROM processed_videos p
                    LEFT JOIN meeting_analysis m ON p.video_id = m.video_id
                    WHERE p.cb_number = ?
                    ORDER BY COALESCE(m.meeting_date, p.published_at) DESC
                    LIMIT ?
                ''', (cb_number, limit)).fetchall()
            
            meetings = []
            for row in rows:
                meeting_dict = dict(row)
                if meeting_dict.get('analysis_json'):
                    try:
                        meeting_dict['analysis'] = json.loads(meeting_dict['analysis_json'])
                    except (json.JSONDecodeError, TypeError):
                        meeting_dict['analysis'] = {'summary': 'Error parsing analysis.'}
                meetings.append(meeting_dict)
            return meetings
        except sqlite3.OperationalError as e:
            logger.error(f"DATABASE LOCKED while fetching for CB{cb_number}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in get_processed_meetings_by_cb: {e}\n{traceback.format_exc()}")
            return []

    def infer_cb_from_title(self, title: str) -> Optional[int]:
        """Try to determine CB number from video title"""
        for pattern in [r'CB\s*(\d+)', r'Community Board\s*(\d+)', r'MCB\s*(\d+)']:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                cb_num = int(match.group(1))
                if 1 <= cb_num <= 12: return cb_num
        return None
