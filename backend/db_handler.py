import sqlite3
import time
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
import threading
import json

logger = logging.getLogger(__name__)

class DBHandler:
    """Enhanced database handler with better concurrency support"""
    
    def __init__(self, db_path: str = "cb_meetings.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        
    def get_connection(self, readonly: bool = False) -> sqlite3.Connection:
        """Get a database connection with optimal settings"""
        if readonly:
            # Open database in read-only mode with URI
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=30.0)
        else:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")  # 10 second timeout
        
        # Additional optimizations for read operations
        if readonly:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA temp_store=MEMORY")
        
        conn.row_factory = sqlite3.Row
        return conn
    
    @contextmanager
    def get_db(self, readonly: bool = False):
        """Context manager for database connections"""
        conn = None
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                conn = self.get_connection(readonly)
                yield conn
                conn.commit()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise
            finally:
                if conn:
                    conn.close()
    
    def execute_with_retry(self, query: str, params: tuple = (), readonly: bool = True) -> List[Dict]:
        """Execute a query with automatic retry logic"""
        with self.get_db(readonly=readonly) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if readonly:
                # Convert rows to dictionaries
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            else:
                return []
    
    def save_analysis_incremental(self, video_id: str, analysis_data: Dict, 
                                 transcript: str = None, processing_time: float = None):
        """Save analysis data incrementally to avoid long locks"""
        
        # First, update the video status quickly
        with self.get_db(readonly=False) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_videos 
                SET status = 'processing', processed_at = datetime('now')
                WHERE video_id = ?
            """, (video_id,))
        
        # If we have a transcript, save it separately
        if transcript:
            with self.get_db(readonly=False) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO meeting_analysis 
                    (video_id, transcript_length, created_at)
                    VALUES (?, ?, datetime('now'))
                """, (video_id, len(transcript)))
        
        # Save the analysis results
        if analysis_data:
            with self.get_db(readonly=False) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE meeting_analysis 
                    SET analysis_json = ?, 
                        processing_time = ?,
                        analysis_method = ?
                    WHERE video_id = ?
                """, (
                    json.dumps(analysis_data),
                    processing_time,
                    analysis_data.get('_metadata', {}).get('analysis_method', 'unknown'),
                    video_id
                ))
        
        # Finally, mark as completed
        with self.get_db(readonly=False) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_videos 
                SET status = 'completed'
                WHERE video_id = ?
            """, (video_id,))
    
    def get_meetings_cached(self, cb_number: int, limit: int = 20) -> List[Dict]:
        """Get meetings with caching to reduce database hits during processing"""
        
        # Try to get from cache first (you could implement Redis here)
        cache_key = f"meetings_cb{cb_number}_{limit}"
        
        # For now, just use direct database access with read-only connection
        query = """
            SELECT 
                p.video_id, p.title, p.url, p.published_at, p.processed_at,
                p.status, p.cb_number, m.analysis_json, m.transcript_length
            FROM processed_videos p
            LEFT JOIN meeting_analysis m ON p.video_id = m.video_id
            WHERE p.cb_number = ?
            ORDER BY p.published_at DESC
            LIMIT ?
        """
        
        try:
            return self.execute_with_retry(query, (cb_number, limit), readonly=True)
        except Exception as e:
            logger.error(f"Failed to fetch meetings: {e}")
            # Return empty list instead of raising to keep UI responsive
            return []