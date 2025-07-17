import tempfile
import shutil
import json
import sqlite3
import time
import logging
import subprocess
import traceback
import re
import asyncio
import contextlib
import os
import uvicorn
import yt_dlp
import requests

# FastAPI and server imports
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from analyzer import CBAnalyzer
from fetch_videos import CBChannelFetcher
from typing import Optional
from datetime import datetime
from pathlib import Path
from typing import Dict
from openai import OpenAI
from config import USE_OPENAI_WHISPER, OPENAI_API_KEY
from googleapiclient.discovery import build

# Import the summarization modules
from summarize import summarize_transcript, MeetingSummary
from render_md import md_from_summary

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProcessRequest(BaseModel): 
    url: str
    cb_number: Optional[int] = None

app = FastAPI(title="CB Meeting Processor", version="1.5.5") # Version bump
app.add_middleware(
    CORSMiddleware, 
    allow_origins=[
        "https://cbmeetings-git-master-bshiribaievs-projects.vercel.app",
        "https://cbmeetings.vercel.app",
        "https://cbmeetings.onrender.com",
        "http://localhost:3000",
        "http://localhost:5174"
        ], 
    allow_credentials=True, 
    allow_methods=["*"], allow_headers=["*"])

whisper_model = None
db_path = Path("cb_meetings.db")
output_dir = Path("processed_meetings")

class CBProcessor:
    def __init__(self):
        # Define instance attributes
        self.db_path = Path("cb_meetings.db")
        self.output_dir = Path("processed_meetings")
        
        # Initialize
        self.output_dir.mkdir(exist_ok=True)
        self.init_database()
        self.load_models()

    @contextlib.contextmanager
    def get_db_connection(self, read_only=False):
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
                    time.sleep(0.5 * retry_count)  # Exponential backoff
                    continue
                else:
                    raise
            except Exception:
                if conn and not read_only:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()

    def init_database(self):
        try:
            with self.get_db_connection() as conn:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS processed_videos (
                        video_id TEXT PRIMARY KEY, 
                        title TEXT, 
                        url TEXT, 
                        published_at TEXT,
                        processed_at TEXT, 
                        duration TEXT, 
                        status TEXT DEFAULT 'pending', 
                        error_message TEXT, 
                        processing_attempts INTEGER DEFAULT 0, 
                        cb_number INTEGER, 
                        cb_district TEXT,
                        channel_source TEXT
                    );
                    CREATE TABLE IF NOT EXISTS meeting_analysis (
                        video_id TEXT PRIMARY KEY, 
                        analysis_json TEXT, 
                        transcript_length INTEGER,
                        processing_time REAL, 
                        created_at TEXT, 
                        analysis_method TEXT,
                        meeting_date TEXT,
                        FOREIGN KEY (video_id) REFERENCES processed_videos (video_id)
                    );
                    CREATE TABLE IF NOT EXISTS transcripts (
                        video_id TEXT PRIMARY KEY, 
                        transcript_text TEXT,
                        FOREIGN KEY (video_id) REFERENCES processed_videos (video_id)
                    );
                ''')
                
                # Add any missing columns
                try:
                    conn.execute("ALTER TABLE meeting_analysis ADD COLUMN meeting_date TEXT;")
                except sqlite3.OperationalError:
                    pass
                    
                try:
                    conn.execute("ALTER TABLE processed_videos ADD COLUMN channel_source TEXT;")
                except sqlite3.OperationalError:
                    pass
                    
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def load_models(self):
        global whisper_model
        try:
            if USE_OPENAI_WHISPER:
                if not OPENAI_API_KEY:
                    raise Exception("OPENAI_API_KEY environment variable not set")
                whisper_model = "openai_api"  
                logger.info("Using OpenAI Whisper API")

        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            raise
        
    def check_ffmpeg(self) -> bool: return shutil.which("ffmpeg") is not None

    def clean_youtube_url(self, url: str) -> str:
        match = re.search(r'[?&]v=([^&]+)', url)
        return f"https://www.youtube.com/watch?v={match.group(1)}" if match else url
    
    def extract_video_info(self, url: str) -> Dict:
        # Get YouTube API Key from environment
        api_key = os.getenv('YOUTUBE_API_KEY')
        if not api_key:
            raise Exception("YOUTUBE_API_KEY environment variable not set.")

        # Extract video ID from URL with regex
        video_id = None
        regex = r"(?:v=|\/|youtu\.be\/|embed\/|watch\?v=)([^#\&\?]{11})"
        match = re.search(regex, url)
        if match:
            video_id = match.group(1)
        
        if not video_id:
            raise HTTPException(status_code=400, detail="Could not parse YouTube video ID from URL.")

        # Call the official YouTube Data API
        try:
            youtube = build('youtube', 'v3', developerKey=api_key)
            request = youtube.videos().list(
                part="snippet",
                id=video_id
            )
            response = request.execute()

            if not response.get('items'):
                raise Exception("Video not found or API error.")

            snippet = response['items'][0]['snippet']
            return {
                'video_id': video_id,
                'title': snippet.get('title'),
                'upload_date': snippet.get('publishedAt') 
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"YouTube API request failed: {e}")
    def extract_audio(self, source_path: str, temp_dir: str, is_file: bool) -> str:
        if is_file:
            output_file = Path(temp_dir) / f"audio_{Path(source_path).stem}.mp3"
            cmd = ['ffmpeg', '-i', source_path, '-vn', '-acodec', 'mp3', '-ar', '16000', '-ac', '1', str(output_file), '-y']
            subprocess.run(cmd, check=True, capture_output=True)
            return str(output_file)
        else:
            logger.info("Using Cobalt API to get direct audio URL...")
            try:
                # Ask Cobalt for a direct download link
                cobalt_api_url = "https://co.wuk.sh/api/json"
                payload = {
                    "url": source_path,
                    "aFormat": "mp3",
                    "isAudioOnly": True
                }
                response = requests.post(cobalt_api_url, json=payload, timeout=30)
                response.raise_for_status()  # Raise an exception for bad status codes

                data = response.json()
                if data.get('status') != 'stream':
                    raise Exception(f"Cobalt API returned an error: {data.get('text', 'Unknown error')}")

                audio_download_url = data.get('url')
                if not audio_download_url:
                    raise Exception("Cobalt API did not return a download URL.")

                # Download the audio file from the direct link
                logger.info(f"Downloading audio from direct URL...")
                output_path = Path(temp_dir) / 'audio.mp3'
                
                with requests.get(audio_download_url, stream=True, timeout=300) as r:
                    r.raise_for_status()
                    with open(output_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                
                if not output_path.exists() or output_path.stat().st_size == 0:
                    raise Exception("Downloaded audio file is empty.")

                return str(output_path)

            except Exception as e:
                logger.error(f"Audio extraction via Cobalt failed: {e}")
                raise Exception(f"Audio extraction via Cobalt failed: {e}")
                        
    def transcribe_audio(self, audio_path: str) -> str:    
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"
                )
            
            return transcript.text.strip()
            
        except Exception as e:
            raise Exception(f"OpenAI Whisper API failed: {str(e)}")

    def extract_meeting_date(self, title: str, transcript: str) -> str:
        """
        More robustly extracts a meeting date by checking title, then the start of the transcript,
        and finally the entire transcript before defaulting.
        """
        date_patterns = [
            r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})',
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
            r'(\d{4})-(\d{2})-(\d{2})'
        ]
        months = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }

        def find_date_in_text(text: str):
            for pattern in date_patterns:
                match = re.search(pattern, text.lower())
                if match:
                    if 'january' in pattern.lower():
                        month_name = match.group(1).lower()
                        month = months.get(month_name, '01')
                        day = match.group(2).zfill(2)
                        year = match.group(3)
                        return f"{year}-{month}-{day}"
                    elif len(match.groups()) == 3 and ('/' in pattern or '-' in pattern):
                        m1, m2, m3 = match.groups()
                        if len(m3) == 4: return f"{m3}-{m1.zfill(2)}-{m2.zfill(2)}"
                        elif len(m1) == 4: return f"{m1}-{m2.zfill(2)}-{m3.zfill(2)}"
            return None

        # 1. Check title first
        date = find_date_in_text(title)
        if date: return date

        # 2. Check the start of the transcript
        date = find_date_in_text(transcript[:1000])
        if date: return date

        # 3. Check the entire transcript as a last resort
        date = find_date_in_text(transcript)
        if date: return date
        
        logger.warning(f"Could not extract meeting date for: {title}. Defaulting to today.")
        return datetime.now().strftime('%Y-%m-%d')

    def summarize_and_analyze(self, transcript: str, title: str, meeting_date: str) -> tuple[dict, MeetingSummary]:
        summary_obj = summarize_transcript(transcript, meeting_date, title)
        analysis = {
            "summary": summary_obj.executive_summary,
            "keyDecisions": [d.model_dump() for d in summary_obj.key_decisions],
            "publicConcerns": summary_obj.public_concerns,
            "nextSteps": [f"{ai.task} (Owner: {ai.owner}, Due: {ai.due})" for t in summary_obj.topics for ai in t.action_items],
            "sentiment": summary_obj.overall_sentiment.title(),
            "attendance": ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in summary_obj.attendance.items()]) or "N/A",
            "mainTopics": [t.title for t in summary_obj.topics],
            "summary_markdown": md_from_summary(summary_obj),
            "summary_data": summary_obj.model_dump(mode="json")
        }
        return analysis, summary_obj

    def save_results(self, video_id: str, analysis: Dict, transcript: str, processing_time: float, meeting_date: str):
        with self.get_db_connection() as conn:
            conn.execute('INSERT OR REPLACE INTO meeting_analysis (video_id, analysis_json, transcript_length, processing_time, created_at, meeting_date) VALUES (?, ?, ?, ?, ?, ?)',
                         (video_id, json.dumps(analysis), len(transcript), processing_time, datetime.now().isoformat(), meeting_date))
            conn.execute('INSERT OR REPLACE INTO transcripts (video_id, transcript_text) VALUES (?, ?)', (video_id, transcript))
        logger.info(f"Analysis and transcript saved for {video_id}")

processor = CBProcessor()
cb_fetcher = CBChannelFetcher(str(processor.db_path))

def core_video_processing_logic(video_id: str, title: str, url: str):
    start_time = time.time()
    current_stage = "starting"
    
    try:
        # Update status with more granular information
        with processor.get_db_connection() as conn:
            conn.execute("""
                UPDATE processed_videos 
                SET status = 'processing', 
                    processing_attempts = processing_attempts + 1, 
                    processed_at = ?,
                    error_message = 'Stage: starting'
                WHERE video_id = ?
            """, (datetime.now().isoformat(), video_id))
        
        # Stage 1: Audio extraction
        current_stage = "audio_extraction"
        logger.info(f"Stage: {current_stage} for {video_id}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                audio_path = processor.extract_audio(url, temp_dir, is_file=False)
            except Exception as e:
                raise Exception(f"Audio extraction failed: {str(e)}")
            
            # Stage 2: Transcription
            current_stage = "transcription"
            logger.info(f"Stage: {current_stage} for {video_id}")
            
            try:
                transcript = processor.transcribe_audio(audio_path)
                if not transcript or len(transcript.strip()) < 100:
                    raise Exception("Transcription produced insufficient content")
            except Exception as e:
                raise Exception(f"Transcription failed: {str(e)}")
        
        # Stage 3: Analysis
        current_stage = "analysis"
        logger.info(f"Stage: {current_stage} for {video_id}")
        
        meeting_date = processor.extract_meeting_date(title, transcript)
        analysis, summary_obj = processor.summarize_and_analyze(transcript, title, meeting_date)
        
        # Stage 4: Saving results
        current_stage = "saving_results"
        processor.save_results(video_id, analysis, transcript, time.time() - start_time, meeting_date)
        
        # Final status update
        with processor.get_db_connection() as conn:
            conn.execute("""
                UPDATE processed_videos 
                SET status = 'completed', 
                    error_message = NULL 
                WHERE video_id = ?
            """, (video_id,))
        
        logger.info(f"BACKGROUND: Processing for {video_id} completed successfully in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        error_msg = f"Failed at stage '{current_stage}': {str(e)}"
        logger.error(f"BACKGROUND: Processing failed for {video_id} - {error_msg}")
        logger.error(traceback.format_exc())
        
        with processor.get_db_connection() as conn:
            conn.execute("""
                UPDATE processed_videos 
                SET status = 'failed', 
                    error_message = ? 
                WHERE video_id = ?
            """, (error_msg[:500], video_id))

@app.get("/health")
async def health_check():
    db_ok = False
    whisper_ok = False
    
    try:
        with processor.get_db_connection(read_only=True) as conn: 
            conn.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
    
    try:
        from config import USE_OPENAI_WHISPER, OPENAI_API_KEY
        if USE_OPENAI_WHISPER:
            whisper_ok = bool(OPENAI_API_KEY)
        else:
            whisper_ok = whisper_model is not None
    except Exception:
        whisper_ok = False
    
    class HealthStatus(BaseModel): 
        whisper: bool
        ffmpeg: bool
        database: bool
        
    return HealthStatus(
        whisper=whisper_ok, 
        ffmpeg=processor.check_ffmpeg(), 
        database=db_ok
    )

@app.post("/process-youtube-async")
async def process_youtube_video_async(request: ProcessRequest, background_tasks: BackgroundTasks):
    try:
        video_info = processor.extract_video_info(request.url)
        video_id, title = video_info['video_id'], video_info['title']

        response_message = "Video queued for processing. Check the meeting list for updates."

        with processor.get_db_connection() as conn:
            existing = conn.execute("SELECT status FROM processed_videos WHERE video_id = ?", (video_id,)).fetchone()
            
            if existing and existing['status'] == 'completed':
                response_message = "This video has been processed before. It is being queued again for re-processing."

            cb_number = request.cb_number if request.cb_number is not None else cb_fetcher.infer_cb_from_title(title)
            
            conn.execute('INSERT OR REPLACE INTO processed_videos (video_id, title, url, published_at, status, cb_number) VALUES (?, ?, ?, ?, ?, ?)',
                         (video_id, title, request.url, video_info.get('upload_date'), 'queued', cb_number))
        
        background_tasks.add_task(core_video_processing_logic, video_id, title, request.url)
        
        return {"success": True, "message": response_message, "video_id": video_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-file")
async def process_file(file: UploadFile = File(...)):
    start_time = time.time()
    video_id = f"file_{int(start_time)}"
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / file.filename
        file_path.write_bytes(await file.read())
        
        audio_path = processor.extract_audio(str(file_path), temp_dir, is_file=True)
        transcript = processor.transcribe_audio(audio_path)
        meeting_date = processor.extract_meeting_date(file.filename, transcript)
        analysis, summary_obj = processor.summarize_and_analyze(transcript, file.filename, meeting_date)
        
        processor.save_results(video_id, analysis, transcript, time.time() - start_time, meeting_date)
        with processor.get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO processed_videos (video_id, title, status) VALUES (?, ?, 'completed')", (video_id, file.filename))

        return {"success": True, "title": file.filename, "analysis": analysis}

@app.get("/api/cb/{cb_number}/meetings")
async def get_cb_meetings(cb_number: int, limit: int = 20):
    try:
        meetings = await asyncio.to_thread(cb_fetcher.get_processed_meetings_by_cb, cb_number, limit)
        return {"cb_number": cb_number, "meetings": meetings, "total": len(meetings)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cb/{cb_key}/fetch-videos")
async def fetch_cb_videos(cb_key: str, max_results: int = 20):
    try:
        videos = await asyncio.to_thread(cb_fetcher.fetch_channel_videos, cb_key, max_results)
        new_count = sum(1 for video in videos if cb_fetcher.save_video_info(video))
        return {"cb_key": cb_key, "videos_found": len(videos), "new_videos": new_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cb/process-pending")
async def get_pending_videos(cb_number: Optional[int] = None, limit: int = 5):
    try:
        pending_videos = await asyncio.to_thread(cb_fetcher.get_pending_videos, cb_number, limit)
        return {"videos": pending_videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cb/process-video/{video_id}")
async def process_single_pending_video(video_id: str, background_tasks: BackgroundTasks):
    try:
        with processor.get_db_connection(read_only=True) as conn:
            video_info = conn.execute('SELECT url, title FROM processed_videos WHERE video_id = ?', (video_id,)).fetchone()
        
        if not video_info:
            raise HTTPException(status_code=404, detail="Video not found in database.")
        
        background_tasks.add_task(core_video_processing_logic, video_id, video_info['title'], video_info['url'])
        
        return {"success": True, "message": f"Queued video {video_id} for processing."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# local 
# if __name__ == "__main__":
#     uvicorn.run(
#         app,
#         host="0.0.0.0",
#         port=8000,
#         log_level="info",
#         reload=False)

# Deployment
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)