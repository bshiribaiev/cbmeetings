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

# AI and processing imports
import whisper
import yt_dlp

# FastAPI and server imports
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from analyzer import CBAnalyzer
from fetch_videos import CBChannelFetcher
from typing import Optional
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Import the summarization modules
from summarize import summarize_transcript, MeetingSummary
from render_md import md_from_summary

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProcessRequest(BaseModel): 
    url: str
    cb_number: Optional[int] = None

app = FastAPI(title="CB Meeting Processor", version="1.5.5") # Version bump
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

whisper_model = None
db_path = Path("cb_meetings.db")
output_dir = Path("processed_meetings")

class CBProcessor:
    def __init__(self):
        output_dir.mkdir(exist_ok=True)
        self.init_database()
        self.load_models()

    @contextlib.contextmanager
    def get_db_connection(self, read_only=False):
        conn = None
        try:
            db_uri = f"file:{db_path}?mode=ro" if read_only else str(db_path)
            conn = sqlite3.connect(db_uri, uri=True, timeout=15.0, check_same_thread=False)
            if not read_only:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=10000")
            conn.row_factory = sqlite3.Row
            yield conn
            if not read_only: conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            if conn and not read_only: conn.rollback()
            raise
        finally:
            if conn: conn.close()

    def init_database(self):
        try:
            with self.get_db_connection() as conn:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS processed_videos (
                        video_id TEXT PRIMARY KEY, title TEXT, url TEXT, published_at TEXT,
                        processed_at TEXT, duration TEXT, status TEXT DEFAULT 'pending', 
                        error_message TEXT, processing_attempts INTEGER DEFAULT 0, 
                        cb_number INTEGER, cb_district TEXT
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
                        video_id TEXT PRIMARY KEY, transcript_text TEXT,
                        FOREIGN KEY (video_id) REFERENCES processed_videos (video_id)
                    );
                ''')
                try:
                    conn.execute("ALTER TABLE meeting_analysis ADD COLUMN meeting_date TEXT;")
                except sqlite3.OperationalError:
                    pass
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def load_models(self):
        global whisper_model
        try:
            whisper_model = whisper.load_model("medium")
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            raise

    def check_ffmpeg(self) -> bool: return shutil.which("ffmpeg") is not None

    def clean_youtube_url(self, url: str) -> str:
        match = re.search(r'[?&]v=([^&]+)', url)
        return f"https://www.youtube.com/watch?v={match.group(1)}" if match else url

    def extract_video_info(self, url: str) -> Dict:
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(self.clean_youtube_url(url), download=False)
                return {'video_id': info.get('id'), 'title': info.get('title'), 'upload_date': info.get('upload_date')}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

    def extract_audio(self, source_path: str, temp_dir: str, is_file: bool) -> str:
        if is_file:
            output_file = Path(temp_dir) / f"audio_{Path(source_path).stem}.mp3"
            cmd = ['ffmpeg', '-i', source_path, '-vn', '-acodec', 'mp3', '-ar', '16000', '-ac', '1', str(output_file), '-y']
            subprocess.run(cmd, check=True, capture_output=True)
            return str(output_file)
        else: # Is URL
            ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f'{temp_dir}/audio.%(ext)s', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}], 'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.clean_youtube_url(source_path)])
                for file in Path(temp_dir).glob("audio.*"):
                    return str(file)
            raise Exception("Audio extraction failed")

    def transcribe_audio(self, audio_path: str) -> str:
        if not whisper_model: raise Exception("Whisper model not loaded")
        result = whisper_model.transcribe(audio_path, language="en", fp16=False)
        return result["text"].strip()

    # *** THIS IS THE FIX ***
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
cb_fetcher = CBChannelFetcher()

def core_video_processing_logic(video_id: str, title: str, url: str):
    start_time = time.time()
    try:
        with processor.get_db_connection() as conn:
            conn.execute("UPDATE processed_videos SET status = 'processing', processing_attempts = processing_attempts + 1, processed_at = ? WHERE video_id = ?", (datetime.now().isoformat(), video_id))
        
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = processor.extract_audio(url, temp_dir, is_file=False)
            transcript = processor.transcribe_audio(audio_path)
        
        meeting_date = processor.extract_meeting_date(title, transcript)
        analysis, summary_obj = processor.summarize_and_analyze(transcript, title, meeting_date)
        
        processor.save_results(video_id, analysis, transcript, time.time() - start_time, meeting_date)
        
        with processor.get_db_connection() as conn:
            conn.execute("UPDATE processed_videos SET status = 'completed' WHERE video_id = ?", (video_id,))
        logger.info(f"BACKGROUND: Processing for {video_id} completed.")
    except Exception as e:
        logger.error(f"BACKGROUND: Processing failed for {video_id}: {e}\n{traceback.format_exc()}")
        with processor.get_db_connection() as conn:
            conn.execute("UPDATE processed_videos SET status = 'failed', error_message = ? WHERE video_id = ?", (str(e)[:500], video_id))

@app.get("/health")
async def health_check():
    db_ok = False
    try:
        with processor.get_db_connection(read_only=True) as conn: conn.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        logger.error(f"Health check DB error: {e}")
    class HealthStatus(BaseModel): whisper: bool; ffmpeg: bool; database: bool
    return HealthStatus(whisper=whisper_model is not None, ffmpeg=processor.check_ffmpeg(), database=db_ok)

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["*.log", "*.db*"]
    )