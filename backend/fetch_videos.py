import yt_dlp
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import re
import traceback

logger = logging.getLogger(__name__)

class CBChannelFetcher:
    """Fetch and track videos from Community Board YouTube channels"""
    
    CB_CHANNELS = {
        'cb7': {
            'name': 'Manhattan CB7',
            'url': 'https://www.youtube.com/@manhattancbseven4610',
            'channel_id': '@manhattancbseven4610',
            'district': 'Manhattan',
            'number': 7
        },
        # Add more boards here as needed
        'cb1': {'name': 'Manhattan CB1', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 1},
        'cb2': {'name': 'Manhattan CB2', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 2},
        'cb3': {'name': 'Manhattan CB3', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 3},
        'cb4': {'name': 'Manhattan CB4', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 4},
        'cb5': {'name': 'Manhattan CB5', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 5},
        'cb6': {'name': 'Manhattan CB6', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 6},
        'cb8': {'name': 'Manhattan CB8', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 8},
        'cb9': {'name': 'Manhattan CB9', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 9},
        'cb10': {'name': 'Manhattan CB10', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 10},
        'cb11': {'name': 'Manhattan CB11', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 11},
        'cb12': {'name': 'Manhattan CB12', 'url': '', 'channel_id': '', 'district': 'Manhattan', 'number': 12},
    }
    
    def __init__(self, db_path: str = "cb_meetings.db"):
        self.db_path = db_path
        # Configure SQLite for better concurrency
        self.setup_database()
    
    def get_db_connection(self):
        """Get a database connection with optimal settings for concurrent access"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)  # 30 second timeout
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
        conn.execute("PRAGMA busy_timeout=5000")  # 5 second busy timeout
        return conn
    
    def setup_database(self):
        """Extended database schema to track CB affiliation"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Add cb_number column to existing tables if not present
        try:
            cursor.execute('ALTER TABLE processed_videos ADD COLUMN cb_number INTEGER')
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        try:
            cursor.execute('ALTER TABLE processed_videos ADD COLUMN cb_district TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        try:
            cursor.execute('ALTER TABLE processed_videos ADD COLUMN channel_source TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
            
        try:
            cursor.execute('ALTER TABLE processed_videos ADD COLUMN processing_attempts INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Create index for faster CB queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cb_number 
            ON processed_videos(cb_number, processed_at DESC)
        ''')
        
        conn.commit()
        conn.close()
    
    def fetch_channel_videos(self, cb_key: str, max_results: int = 50) -> List[Dict]:
        """Fetch recent videos from a CB channel"""
        cb_info = self.CB_CHANNELS.get(cb_key)
        if not cb_info or not cb_info['url']:
            logger.warning(f"No channel URL for {cb_key}")
            return []
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'force_generic_extractor': False,
            'playlist_items': f'1-{max_results}',
        }
        
        videos = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get channel videos
                result = ydl.extract_info(f"{cb_info['url']}/videos", download=False)
                
                if 'entries' in result:
                    for entry in result['entries']:
                        if entry and 'id' in entry:
                            video_data = {
                                'video_id': entry['id'],
                                'title': entry.get('title', ''),
                                'url': f"https://www.youtube.com/watch?v={entry['id']}",
                                'duration': entry.get('duration', 0),
                                'upload_date': entry.get('upload_date', ''),
                                'cb_number': cb_info['number'],
                                'cb_district': cb_info['district'],
                                'channel_source': cb_key
                            }
                            
                            # Check if it's likely a meeting video
                            if self.is_meeting_video(video_data['title']):
                                videos.append(video_data)
                
                logger.info(f"Found {len(videos)} meeting videos from {cb_info['name']}")
                
        except Exception as e:
            logger.error(f"Failed to fetch videos from {cb_key}: {e}")
        
        return videos
    
    def is_meeting_video(self, title: str) -> bool:
        """Check if video title suggests it's a meeting"""
        meeting_keywords = [
            'meeting', 'committee', 'board', 'session', 'hearing',
            'full board', 'land use', 'parks', 'transportation',
            'business', 'housing', 'budget', 'public'
        ]
        
        title_lower = title.lower()
        
        # Exclude non-meeting content
        exclude_keywords = ['highlights', 'summary', 'clip', 'excerpt', 'interview']
        if any(keyword in title_lower for keyword in exclude_keywords):
            return False
        
        # Check for meeting keywords
        return any(keyword in title_lower for keyword in meeting_keywords)
    
    def save_video_info(self, video: Dict) -> bool:
        """Save video info to database if not already processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Check if video already exists
            cursor.execute('SELECT video_id, status FROM processed_videos WHERE video_id = ?', 
                          (video['video_id'],))
            existing = cursor.fetchone()
            
            if existing:
                logger.info(f"Video {video['video_id']} already in database (status: {existing[1]})")
                return False
            
            # Parse upload date
            upload_date = None
            if video.get('upload_date'):
                try:
                    upload_date = datetime.strptime(video['upload_date'], '%Y%m%d').isoformat()
                except:
                    upload_date = datetime.now().isoformat()
            
            # Insert new video
            cursor.execute('''
                INSERT INTO processed_videos 
                (video_id, title, url, published_at, cb_number, cb_district, 
                 channel_source, duration, status, processing_attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)
            ''', (
                video['video_id'],
                video['title'],
                video['url'],
                upload_date,
                video['cb_number'],
                video['cb_district'],
                video['channel_source'],
                video.get('duration', 0)
            ))
            
            conn.commit()
            logger.info(f"Saved new video: {video['title'][:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save video {video['video_id']}: {e}")
            return False
        finally:
            conn.close()
    
    def get_pending_videos(self, cb_number: Optional[int] = None, limit: int = 10) -> List[Dict]:
        """Get videos that need processing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT video_id, title, url, cb_number, cb_district, duration
            FROM processed_videos 
            WHERE status = 'pending' AND processing_attempts < 3
        '''
        
        params = []
        if cb_number:
            query += ' AND cb_number = ?'
            params.append(cb_number)
        
        query += ' ORDER BY published_at DESC LIMIT ?'
        params.append(limit)
        
        cursor.execute(query, params)
        
        videos = []
        for row in cursor.fetchall():
            videos.append({
                'video_id': row[0],
                'title': row[1],
                'url': row[2],
                'cb_number': row[3],
                'cb_district': row[4],
                'duration': row[5]
            })
        
        conn.close()
        return videos
    
    def mark_video_processed(self, video_id: str, status: str = 'completed'):
        """Update video processing status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE processed_videos 
            SET status = ?, processed_at = ?, processing_attempts = processing_attempts + 1
            WHERE video_id = ?
        ''', (status, datetime.now().isoformat(), video_id))
        
        conn.commit()
        conn.close()
    
    # The issue is likely in the fetch_videos.py file where the connection isn't being closed properly
# or there's an exception that's not being caught.

# In fetch_videos.py, update the get_processed_meetings_by_cb method:

    def get_processed_meetings_by_cb(self, cb_number: int, limit: int = 20) -> List[Dict]:
        """Get all meetings for a specific CB (all statuses)"""
        logger.info(f"Starting to fetch meetings for CB{cb_number}")
        
        meetings = []
        conn = None
        
        try:
            # Use read-only connection with shorter timeout
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Set pragmas for read-only optimization
            cursor.execute("PRAGMA query_only = ON")
            cursor.execute("PRAGMA temp_store = MEMORY")
            
            logger.info(f"Database connected, executing query for CB{cb_number}")
            
            # Modified query to handle processing status better
            cursor.execute('''
                SELECT 
                    p.video_id, p.title, p.url, p.published_at, p.processed_at,
                    p.status, p.cb_number, 
                    CASE 
                        WHEN p.status = 'processing' THEN NULL 
                        ELSE m.analysis_json 
                    END as analysis_json,
                    m.transcript_length
                FROM processed_videos p
                LEFT JOIN meeting_analysis m ON p.video_id = m.video_id
                WHERE p.cb_number = ?
                ORDER BY p.published_at DESC
                LIMIT ?
            ''', (cb_number, limit))
            
            rows = cursor.fetchall()
            logger.info(f"Query complete, found {len(rows)} meetings")
            
            for row in rows:
                try:
                    meeting = {
                        'video_id': row['video_id'],
                        'title': row['title'],
                        'url': row['url'],
                        'published_at': row['published_at'],
                        'processed_at': row['processed_at'],
                        'status': row['status'],
                        'cb_number': row['cb_number'] if 'cb_number' in row.keys() else None,
                        'analysis': row['analysis_json'],
                        'transcript_length': row['transcript_length']
                    }
                    meetings.append(meeting)
                except Exception as e:
                    logger.error(f"Error processing row: {e}")
                    continue
            
            logger.info(f"Successfully processed {len(meetings)} meetings")
            return meetings
        
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in get_processed_meetings_by_cb: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
        finally:
            if conn:
                try:
                    conn.close()
                    logger.info("Database connection closed")
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")

    def update_existing_video_cb(self, video_id: str, cb_number: int, cb_district: str = 'Manhattan'):
        """Update CB info for existing videos based on title analysis"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE processed_videos 
            SET cb_number = ?, cb_district = ?
            WHERE video_id = ? AND cb_number IS NULL
        ''', (cb_number, cb_district, video_id))
        
        conn.commit()
        conn.close()
    
    def infer_cb_from_title(self, title: str) -> Optional[int]:
        """Try to determine CB number from video title"""
        patterns = [
            r'CB\s*(\d+)',                           # CB7, CB 7
            r'Community Board\s*(\d+)',              # Community Board 7
            r'MCB\s*(\d+)',                         # MCB7 (Manhattan Community Board)
            r'Board\s*(\d+)',                       # Board 7
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                cb_num = int(match.group(1))
                if 1 <= cb_num <= 12:  # Valid Manhattan CB numbers
                    return cb_num
        
        return None