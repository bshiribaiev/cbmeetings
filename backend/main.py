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
import random
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

# Import the summarization modules
from summarize import summarize_transcript, MeetingSummary
from render_md import md_from_summary

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProcessRequest(BaseModel):
    url: str
    cb_number: Optional[int] = None


app = FastAPI(title="CB Meeting Processor", version="1.5.5")  # Version bump
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


class ProxyVideoProcessor:
    def __init__(self):
        self.proxy_url = os.getenv('PROXY_URL')
        if self.proxy_url:
            match = re.match(r'http://brd-customer-(.+?)-zone-(.+?):(.+?)@(.+?):(\d+)', self.proxy_url)
            if match:
                self.account_id = match.group(1)
                self.zone_name = match.group(2)
                self.password = match.group(3)
                self.proxy_host = match.group(4)
                self.proxy_port = match.group(5)
                logger.info(f"Parsed procy - Account: {self.account_id}, Zone: {self.zone_name}")
            else:
                logger.error("Could not parse PROXY_URL")
                self.account_id = None
        else:
            logger.warning("No PROXY_URL set, downloads might fail on Render")
            self.account_id = None
    
    def generate_session_id(self):
        return random.randint(10000000, 999999999)
    
    def build_proxy_url(self, session_id):
        if not self.account_id:
            return self.proxy_url
        
        return f"http://brd-customer-{self.account_id}-zone-{self.zone_name}-session-{session_id}:{self.password}@{self.proxy_host}:{self.proxy_port}"
    
    def download_audio_with_proxy(self, url: str, temp_dir: str) -> str:
        output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
        
        # Generate unique session ID for this download
        session_id = self.generate_session_id()
        proxy_with_session = self.build_proxy_url(session_id)
        
        logger.info(f"Using Web Unlocker with session ID: {session_id}")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'outtmpl': output_template,
            'quiet': False,
            'verbose': True,
            'proxy': proxy_with_session,
            'nocheckcertificate': True,  # Required for Web Unlocker
            'concurrent_fragment_downloads': 1,  # Equivalent to -N 1
            'http_chunk_size': 2097152,  # 2MB chunks as recommended
            'abort_on_unavailable_fragments': True,  # Fail fast to retry with new session
            'continuedl': True,  # Continue download if interrupted
            # Additional recommended settings
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': False,
            # User agent
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Generate new session ID for retry
                    session_id = self.generate_session_id()
                    proxy_with_session = self.build_proxy_url(session_id)
                    ydl_opts['proxy'] = proxy_with_session
                    logger.info(f"Retry {attempt + 1} with new session ID: {session_id}")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info(f"Downloading audio from: {url}")
                    info = ydl.extract_info(url, download=True)
                    
                    # Get the actual output filename
                    filename = ydl.prepare_filename(info)
                    audio_file = filename.rsplit('.', 1)[0] + '.mp3'
                    
                    if os.path.exists(audio_file):
                        file_size_mb = os.path.getsize(audio_file) / (1024 * 1024)
                        logger.info(f"Downloaded successfully: {file_size_mb:.1f}MB")
                        return audio_file
                    else:
                        raise Exception("Audio file not found after download")
                        
            except Exception as e:
                last_error = e
                logger.error(f"Download attempt {attempt + 1} failed: {str(e)}")
                
                # Check if it's a chunk error that might benefit from a new session
                if "fragment" in str(e).lower() or "403" in str(e) or "unavailable" in str(e).lower():
                    continue  # Try with new session
                else:
                    # For other errors, no point retrying with new session
                    break
        
        raise Exception(f"All download attempts failed. Last error: {last_error}")
    
    def test_proxy_connection(self):
        
        if not self.account_id:
            return False, "No proxy configured"
        
        # Generate session for test
        session_id = self.generate_session_id()
        proxy_url = self.build_proxy_url(session_id)
        
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        try:
            # Test with YouTube directly
            response = requests.get(
                'https://www.youtube.com',
                proxies=proxies,
                timeout=30,
                verify=False  # Web Unlocker requires this
            )
            
            if response.status_code == 200:
                logger.info(f"Web Unlocker test successful!")
                return True, "Connected to YouTube successfully via Web Unlocker"
            else:
                return False, f"YouTube returned status: {response.status_code}"
                
        except Exception as e:
            return False, f"Web Unlocker test failed: {str(e)}"

class CBProcessor:
    def __init__(self):
        # Define instance attributes
        self.db_path = Path("cb_meetings.db")
        self.output_dir = Path("processed_meetings")
        # Initialize
        self.output_dir.mkdir(exist_ok=True)
        self.init_database()
        self.load_models()
        self.proxy_processor = ProxyVideoProcessor()

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
                    conn = sqlite3.connect(
                        str(self.db_path), timeout=30.0, isolation_level='IMMEDIATE')
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
                    conn.execute(
                        "ALTER TABLE meeting_analysis ADD COLUMN meeting_date TEXT;")
                except sqlite3.OperationalError:
                    pass

                try:
                    conn.execute(
                        "ALTER TABLE processed_videos ADD COLUMN channel_source TEXT;")
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
                    raise Exception(
                        "OPENAI_API_KEY environment variable not set")
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
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        cookies_data = os.getenv('YOUTUBE_COOKIES')
        with tempfile.TemporaryDirectory() as temp_dir:
            if cookies_data:
                cookies_file_path = Path(temp_dir) / 'cookies.txt'
                cookies_file_path.write_text(cookies_data)
                ydl_opts['cookiefile'] = str(cookies_file_path)
                logger.info("Using YouTube cookies for video info extraction.")

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        self.clean_youtube_url(url), download=False)
                    return {'video_id': info.get('id'), 'title': info.get('title'), 'upload_date': info.get('upload_date')}
            except Exception as e:
                error_detail = str(e)
                logger.error(f"Failed to extract video info: {error_detail}")
                raise HTTPException(
                    status_code=400, detail=f"Failed to extract video info: {error_detail}")

    def extract_audio(self, source_path: str, temp_dir: str, is_file: bool) -> str:
        if is_file:
            output_file = Path(temp_dir) / \
                f"audio_{Path(source_path).stem}.mp3"
            cmd = ['ffmpeg', '-i', source_path, '-vn', '-acodec', 'mp3',
                   '-ar', '16000', '-ac', '1', str(output_file), '-y']
            subprocess.run(cmd, check=True, capture_output=True)
            return str(output_file)
        else:
            cookies = os.getenv('YOUTUBE_COOKIES')
            return self.extract_with_ytdlp(source_path, temp_dir, cookies=cookies)

    def extract_with_ytdlp(self, url: str, temp_dir: str, cookies: str = None) -> str:
        output_template = Path(temp_dir) / 'audio.%(ext)s'

        # Enhanced options to avoid detection
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(output_template),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }],
            'quiet': False,  # Set to False to see errors
            'no_warnings': False,
            # Add these options
            'extract_flat': False,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'prefer_insecure': True,
            # Headers to appear more like a browser
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
        }

        cookies_file = None
        try:
            if cookies:
                cookies_file = Path(temp_dir) / 'cookies.txt'
                cookies_file.write_text(cookies)
                ydl_opts['cookiefile'] = str(cookies_file)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            mp3_file = Path(temp_dir) / 'audio.mp3'
            if mp3_file.exists() and mp3_file.stat().st_size > 0:
                return str(mp3_file)
            else:
                for file in Path(temp_dir).glob("audio.*"):
                    if file.exists() and file.stat().st_size > 0:
                        return str(file)
                raise Exception(
                    "Audio extraction failed: No valid audio file was produced")

        except Exception as e:
            logger.error(f"yt-dlp download failed: {e}")
            raise Exception(f"yt-dlp download failed: {e}")
        finally:
            if cookies_file and cookies_file.exists():
                try:
                    os.remove(cookies_file)
                except:
                    pass

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

    def download_and_transcribe(self, url: str) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Download audio using proxy
                audio_path = self.proxy_processor.download_audio_with_proxy(
                    url, temp_dir)

                # Transcribe with OpenAI Whisper API
                transcript = self.transcribe_audio(audio_path)

                return transcript

            except Exception as e:
                logger.error(f"Download/transcribe failed: {e}")
                raise

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
                        if len(m3) == 4:
                            return f"{m3}-{m1.zfill(2)}-{m2.zfill(2)}"
                        elif len(m1) == 4:
                            return f"{m1}-{m2.zfill(2)}-{m3.zfill(2)}"
            return None

        # 1. Check title first
        date = find_date_in_text(title)
        if date:
            return date

        # 2. Check the start of the transcript
        date = find_date_in_text(transcript[:1000])
        if date:
            return date

        # 3. Check the entire transcript as a last resort
        date = find_date_in_text(transcript)
        if date:
            return date

        logger.warning(
            f"Could not extract meeting date for: {title}. Defaulting to today.")
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
            conn.execute(
                'INSERT OR REPLACE INTO transcripts (video_id, transcript_text) VALUES (?, ?)', (video_id, transcript))
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
                audio_path = processor.proxy_processor.download_audio_with_proxy(
                    url, temp_dir)
            except Exception as e:
                raise Exception(f"Audio extraction failed: {str(e)}")

            # Stage 2: Transcription
            current_stage = "transcription"
            logger.info(f"Stage: {current_stage} for {video_id}")

            try:
                transcript = processor.transcribe_audio(audio_path)
                if not transcript or len(transcript.strip()) < 100:
                    raise Exception(
                        "Transcription produced insufficient content")
            except Exception as e:
                raise Exception(f"Transcription failed: {str(e)}")

        # Stage 3: Analysis
        current_stage = "analysis"
        logger.info(f"Stage: {current_stage} for {video_id}")

        meeting_date = processor.extract_meeting_date(title, transcript)
        analysis, summary_obj = processor.summarize_and_analyze(
            transcript, title, meeting_date)

        # Stage 4: Saving results
        current_stage = "saving_results"
        processor.save_results(
            video_id, analysis, transcript, time.time() - start_time, meeting_date)

        # Final status update
        with processor.get_db_connection() as conn:
            conn.execute("""
                UPDATE processed_videos 
                SET status = 'completed', 
                    error_message = NULL 
                WHERE video_id = ?
            """, (video_id,))

        logger.info(
            f"BACKGROUND: Processing for {video_id} completed successfully in {time.time() - start_time:.2f}s")

    except Exception as e:
        error_msg = f"Failed at stage '{current_stage}': {str(e)}"
        logger.error(
            f"BACKGROUND: Processing failed for {video_id} - {error_msg}")
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
            existing = conn.execute(
                "SELECT status FROM processed_videos WHERE video_id = ?", (video_id,)).fetchone()

            if existing and existing['status'] == 'completed':
                response_message = "This video has been processed before. It is being queued again for re-processing."

            cb_number = request.cb_number if request.cb_number is not None else cb_fetcher.infer_cb_from_title(
                title)

            conn.execute('INSERT OR REPLACE INTO processed_videos (video_id, title, url, published_at, status, cb_number) VALUES (?, ?, ?, ?, ?, ?)',
                         (video_id, title, request.url, video_info.get('upload_date'), 'queued', cb_number))

        background_tasks.add_task(
            core_video_processing_logic, video_id, title, request.url)

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

        audio_path = processor.extract_audio(
            str(file_path), temp_dir, is_file=True)
        transcript = processor.transcribe_audio(audio_path)
        meeting_date = processor.extract_meeting_date(
            file.filename, transcript)
        analysis, summary_obj = processor.summarize_and_analyze(
            transcript, file.filename, meeting_date)

        processor.save_results(
            video_id, analysis, transcript, time.time() - start_time, meeting_date)
        with processor.get_db_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_videos (video_id, title, status) VALUES (?, ?, 'completed')", (video_id, file.filename))

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
        new_count = sum(
            1 for video in videos if cb_fetcher.save_video_info(video))
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
            video_info = conn.execute(
                'SELECT url, title FROM processed_videos WHERE video_id = ?', (video_id,)).fetchone()

        if not video_info:
            raise HTTPException(
                status_code=404, detail="Video not found in database.")

        background_tasks.add_task(
            core_video_processing_logic, video_id, video_info['title'], video_info['url'])

        return {"success": True, "message": f"Queued video {video_id} for processing."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/test-unlocker")
async def test_unlocker():
    import urllib.request
    import ssl
    
    proxy_url = os.getenv('PROXY_URL')
    if not proxy_url:
        return {"error": "No PROXY_URL configured"}
    
    url = 'https://geo.brdtest.com/welcome.txt?product=unlocker&method=native'
    
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({'https': proxy_url, 'http': proxy_url}),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
    )
    
    try:
        response = opener.open(url).read().decode()
        return {
            "success": True,
            "response": response,
            "message": "Web Unlocker is working!"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

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
