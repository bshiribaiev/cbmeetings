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

# AI and processing imports
import whisper
import yt_dlp

# FastAPI and server imports
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from analyzer import CBAnalyzer
from fetch_videos import CBChannelFetcher
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict
from db_handler import DBHandler

# Import the summarization modules
from summarize import summarize_transcript
from render_md import md_from_summary

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('cb_processor.log')
    ]
)

logger = logging.getLogger(__name__)

# Pydantic models
class ProcessRequest(BaseModel):
    url: str

class HealthStatus(BaseModel):
    whisper: bool
    ffmpeg: bool
    yt_dlp: bool
    database: bool

class MeetingAnalysis(BaseModel):
    summary: str
    keyDecisions: List[Dict]
    publicConcerns: List[str]
    nextSteps: List[str]
    sentiment: str
    attendance: str
    mainTopics: List[str]
    importantDates: List[str] = []
    budgetItems: List[str] = []
    addresses: List[str] = []

# FastAPI App Configuration
app = FastAPI(
    title="CB Meeting Processor",
    description="AI-powered Community Board Meetings analysis system",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "*"  # temporary
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global variables
whisper_model = None
db_path = Path("cb_meetings.db")
output_dir = Path("processed_meetings")

class CBProcessor:
    def __init__(self):
        self.setup_directories()
        self.init_database()
        self.load_models()

    def setup_directories(self):
        output_dir.mkdir(exist_ok=True)

    # Getting database connection with concurrent read and write
    def get_db_connection(self):
        conn = sqlite3.connect(db_path, timeout=30.0)  # 30 second timeout
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
        conn.execute("PRAGMA busy_timeout=5000")  # 5 second busy timeout
        return conn
    
    # Initializing a database
    def init_database(self):
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            self.create_processed(cursor)
            self.create_meet_analysis(cursor)
            self.create_system_logs(cursor)

            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    # Creating a table in database
    def create_processed(self, cursor):
        cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_videos (
                    video_id TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    published_at TEXT,
                    processed_at TEXT,
                    duration TEXT,
                    file_size INTEGER,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    processing_attempts INTEGER DEFAULT 0
                )
            ''')
    
    # Creating a table in database
    def create_meet_analysis(self, cursor):
        cursor.execute('''
                CREATE TABLE IF NOT EXISTS meeting_analysis (
                    video_id TEXT PRIMARY KEY,
                    analysis_json TEXT,
                    transcript_length INTEGER,
                    processing_time REAL,
                    created_at TEXT,
                    analysis_method TEXT,
                    FOREIGN KEY (video_id) REFERENCES processed_videos (video_id)
                )
            ''')
    
    # Creating a table in database
    def create_system_logs(self, cursor):
        cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    message TEXT,
                    data TEXT
                )
            ''')

    # Load Whisper AI
    def load_models(self):
        global whisper_model

        try:
            logger.info("Loading Whisper model...")
            whisper_model = whisper.load_model("medium")
            logger.info("Whisper model loaded successfully")

        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            raise

    
    def check_ffmpeg(self) -> bool:
        return shutil.which("ffmpeg") is not None

    # Get clean video url
    def clean_youtube_url(self, url: str) -> str:
        match = re.search(r'[?&]v=([^&]+)', url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"
        return url

    # Get video info
    def extract_video_info(self, url: str) -> Dict:
        try:
            clean_url = self.clean_youtube_url(url)
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)

                return {
                    'video_id': info.get('id', 'unknown'),
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration', 0),
                    'upload_date': info.get('upload_date', ''),
                    'uploader': info.get('uploader', ''),
                    'description': info.get('description', '')
                    }

        except Exception as e:
            logger.error(f"Failed to extract video info: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to extract video info: {str(e)}")

    # Determine if it is a real meeting
    def is_meeting_video(self, title: str, description: str = "") -> bool:
        meeting_keywords = [
            'board meeting', 'full board', 'committee meeting',
            'land use', 'parks', 'transportation', 'public meeting',
            'cb', 'community board', 'housing', 'zoning',
            'cb1', 'cb2', 'cb3', 'cb4', 'cb5', 'cb6', 'cb7', 'cb8', 'cb9', 'cb10', 'cb11', 'cb12'
        ]

        combined_text = f"{title} {description}".lower()
        return any(keyword in combined_text for keyword in meeting_keywords)

    def extract_audio_from_youtube(self, url: str, output_path: str) -> tuple:
        try:
            clean_url = self.clean_youtube_url(url)
            logger.info(f"🎬 Extracting audio from: {url}")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{output_path}/audio.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=True)
                title = info.get('title', 'Unknown')

                # Find the downloaded audio file
                for file in Path(output_path).glob("audio.*"):
                    if file.suffix in ['.mp3', '.m4a', '.webm']:
                        logger.info(f"Audio extracted: {file}")
                        return str(file), title

            raise Exception("No audio file found after extraction")

        except Exception as e:
            error_msg = str(e)
            if "ffmpeg" in error_msg.lower():
                error_msg += "\n\nFix: Install ffmpeg with 'brew install ffmpeg' (Mac) or visit https://ffmpeg.org"
            logger.error(f"Audio extraction failed: {error_msg}")
            raise Exception(error_msg)

    def extract_audio_from_file(self, file_path: str, output_path: str) -> str:
        try:
            file_path = Path(file_path)
            output_file = Path(output_path) / f"audio_{file_path.stem}.mp3"

            # If it's already an audio file, just copy it
            if file_path.suffix.lower() in ['.mp3', '.wav', '.m4a', '.flac']:
                shutil.copy2(file_path, output_file)
                logger.info(f"Audio file copied: {output_file}")
                return str(output_file)

            # Extract audio from video file using ffmpeg
            cmd = [
                'ffmpeg', '-i', str(file_path),
                '-vn', '-acodec', 'mp3', '-ar', '22050', '-ac', '1',
                str(output_file), '-y'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"FFmpeg failed: {result.stderr}")

            logger.info(f"Audio extracted from video: {output_file}")
            return str(output_file)

        except Exception as e:
            logger.error(f"Audio extraction from file failed: {e}")
            raise Exception(f"Audio extraction failed: {str(e)}")

    def optimize_audio_for_transcription(self, audio_path: str) -> str:
        try:
            output_path = str(Path(audio_path).with_suffix('.optimized.wav'))

            cmd = [
                'ffmpeg', '-i', audio_path,
                '-ar', '16000',
                '-ac', '1',
                '-af',
                'highpass=f=80,'
                'lowpass=f=8000,'
                'volume=1.5,'
                'compand=attacks=0.3:decays=0.8:points=-70/-70|-60/-20|-20/-5|-5/-5',
                '-acodec', 'pcm_s16le',
                '-f', 'wav',
                output_path, '-y', '-v', 'quiet'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and Path(output_path).exists():
                logger.info("Audio optimized for better transcription")
                return output_path
            else:
                logger.warning("Audio optimization failed, using original")
                return audio_path

        except Exception as e:
            logger.warning(f"Audio optimization failed: {e}")
            return audio_path

    def transcribe_audio(self, audio_path: str) -> str:
        try:
            if not whisper_model:
                raise Exception("Whisper model not loaded")

            optimized_path = self.optimize_audio_for_transcription(audio_path)
            logger.info(f"Transcribing audio: {optimized_path}")

            # Transcribe with Whisper
            result = whisper_model.transcribe(
                optimized_path,
                language="en",
                task="transcribe",
                temperature=0.0,
                fp16=False,
                verbose=False,
                word_timestamps=False,
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                logprob_threshold=-1.0,
                no_speech_threshold=0.6,
            )

            transcript = result["text"].strip()
            word_count = len(transcript.split())

            logger.info(f"Transcription complete: {word_count:,} words")
            return transcript

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise Exception(f"Transcription failed: {str(e)}")

    def identify_meeting_type(self, title: str, topics: List[str]) -> str:
        """Identify the type of meeting from title and topics"""
        title_lower = title.lower() if title else ""
        topics_lower = ' '.join(topics).lower()
        
        # Check title first
        if 'parks' in title_lower and 'environment' in title_lower:
            return "Parks & Environment Committee meeting"
        elif 'business' in title_lower:
            return "Business & Consumer Issues Committee meeting"
        elif 'housing' in title_lower:
            return "Housing Committee meeting"
        elif 'transportation' in title_lower:
            return "Transportation Committee meeting"
        elif 'land use' in title_lower:
            return "Land Use Committee meeting"
        elif 'budget' in title_lower:
            return "Budget Committee meeting"
        elif 'full board' in title_lower:
            return "Full Board meeting"
        
        # Check topics if title doesn't help
        if 'parks' in topics_lower or 'environment' in topics_lower:
            return "Parks & Environment Committee meeting"
        elif 'business' in topics_lower or 'restaurant' in topics_lower:
            return "Business Committee meeting"
        elif 'budget' in topics_lower or 'fiscal' in topics_lower:
            return "Budget Committee meeting"
        elif 'housing' in topics_lower or 'development' in topics_lower:
            return "Housing & Development Committee meeting"
        
        return "Community Board meeting"
    
    def format_attendance_string(self, attendance: Dict) -> str:
        """Format attendance dict into a readable string"""
        if not attendance:
            return "Not specified"
        
        parts = []
        for key, value in attendance.items():
            readable_key = key.replace('_', ' ').title()
            parts.append(f"{readable_key}: {value}")
        
        return ", ".join(parts)

    def extract_meeting_date(self, title: str, transcript: str) -> str:
        """Extract meeting date from title or transcript"""
        import re
        
        # Common date patterns to look for
        date_patterns = [
            # Month DD, YYYY format
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
            # MM/DD/YYYY or MM-DD-YYYY
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
            # YYYY-MM-DD
            r'(\d{4})-(\d{2})-(\d{2})',
        ]
        
        # Month name to number mapping
        months = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        
        # Try to find date in title first
        for pattern in date_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                if pattern == date_patterns[0]:  # Month name format
                    month_name = match.group(1).lower()
                    month = months.get(month_name, '01')
                    day = match.group(2).zfill(2)
                    year = match.group(3)
                    return f"{year}-{month}-{day}"
                elif pattern == date_patterns[1]:  # MM/DD/YYYY
                    month = match.group(1).zfill(2)
                    day = match.group(2).zfill(2)
                    year = match.group(3)
                    return f"{year}-{month}-{day}"
                elif pattern == date_patterns[2]:  # YYYY-MM-DD
                    return match.group(0)
        
        # If not in title, check first 500 chars of transcript
        transcript_start = transcript[:500] if len(transcript) > 500 else transcript
        for pattern in date_patterns:
            match = re.search(pattern, transcript_start, re.IGNORECASE)
            if match:
                if pattern == date_patterns[0]:  # Month name format
                    month_name = match.group(1).lower()
                    month = months.get(month_name, '01')
                    day = match.group(2).zfill(2)
                    year = match.group(3)
                    return f"{year}-{month}-{day}"
                elif pattern == date_patterns[1]:  # MM/DD/YYYY
                    month = match.group(1).zfill(2)
                    day = match.group(2).zfill(2)
                    year = match.group(3)
                    return f"{year}-{month}-{day}"
                elif pattern == date_patterns[2]:  # YYYY-MM-DD
                    return match.group(0)
        
        return None

    def summarize_with_gemini(self, transcript: str, meeting_date: str):
        """Use the new summarization logic with Pydantic models"""
        summary_obj = summarize_transcript(transcript, meeting_date)
        summary_md  = md_from_summary(summary_obj)
        return summary_obj, summary_md

    def analyze_with_gemini(self, transcript: str, title: str = None) -> Dict:
        try:
            transcript_length = len(transcript)
            word_count = len(transcript.split())
            
            logger.info(f"Analyzing transcript with Gemini: {transcript_length:,} chars, {word_count:,} words")
            
            # Use enhanced analyzer with Gemini
            analyzer = CBAnalyzer()
            
            # Perform analysis with Gemini (model parameter is ignored as Gemini is configured in the analyzer)
            result = analyzer.analyze_cb_meeting(transcript, model='gemini', title=title)
            
            # Validate and enhance result
            if self.validate_analysis_result(result):
                logger.info("Gemini analysis completed successfully")
                # Add metadata
                if '_metadata' not in result:
                    result['_metadata'] = {}
                result['_metadata'].update({
                    'transcript_length': transcript_length,
                    'word_count': word_count,
                    'analysis_method': 'enhanced-gemini',
                    'model_used': 'gemini-1.5-flash'
                })
                return result
            else:
                logger.warning("Gemini analysis validation failed, using fallback")
                return self.create_enhanced_analysis(transcript)

        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return self.create_enhanced_analysis(transcript)

    def validate_analysis_result(self, result: Dict) -> bool:
        if not isinstance(result, dict):
            return False

        required_fields = ['summary', 'keyDecisions', 'publicConcerns', 'nextSteps', 'mainTopics']
        for field in required_fields:
            if field not in result:
                return False

        # Check for meaningful content - more lenient for chunked analysis
        has_content = (
            len(str(result.get('summary', ''))) > 30 or
            len(result.get('keyDecisions', [])) > 0 or
            len(result.get('publicConcerns', [])) > 0 or
            len(result.get('nextSteps', [])) > 0 or
            len(result.get('mainTopics', [])) > 0
        )

        # Log validation details
        if has_content:
            decisions = len(result.get('keyDecisions', []))
            concerns = len(result.get('publicConcerns', []))
            topics = len(result.get('mainTopics', []))
            logger.info(f"Validation passed: {decisions} decisions, {concerns} concerns, {topics} topics")
        else:
            logger.warning("Validation failed: insufficient content")

        return has_content

    def create_enhanced_analysis(self, transcript: str) -> Dict:
        words = transcript.lower().split()
        word_count = len(words)

        # Enhanced keyword detection
        decision_keywords = ['approve', 'approved', 'reject', 'rejected', 'vote', 'motion', 'resolution']
        concern_keywords = ['concern', 'problem', 'issue', 'complaint', 'worried']
        
        decision_count = sum(1 for word in words if word in decision_keywords)
        concern_count = sum(1 for word in words if word in concern_keywords)

        # Extract potential topics
        topic_keywords = {
            'Housing & Development': ['housing', 'apartment', 'development', 'residential', 'affordable'],
            'Transportation': ['traffic', 'bike', 'bus', 'subway', 'parking', 'street'],
            'Parks & Recreation': ['park', 'playground', 'tree', 'garden', 'recreation'],
            'Zoning & Land Use': ['zoning', 'building', 'construction', 'permit', 'land use'],
            'Budget & Finance': ['budget', 'funding', 'money', 'cost', 'expense']
        }

        main_topics = []
        for topic, keywords in topic_keywords.items():
            if any(keyword in transcript.lower() for keyword in keywords):
                main_topics.append(topic)

        # Try to extract specific decisions
        decisions = []
        decision_patterns = [
            r'motion.*?(?:to\s+)?(?:approve|support|adopt|pass).*?(?:resolution|proposal|amendment)',
            r'(?:approve|support|adopt|pass).*?(?:resolution|motion|proposal)',
            r'vote.*?(?:\d+-\d+|unanimous|all in favor)'
        ]

        import re
        for pattern in decision_patterns:
            matches = re.findall(pattern, transcript.lower())
            for match in matches[:3]:
                decisions.append({
                    "item": match.strip().capitalize(),
                    "outcome": "Discussed",
                    "vote": "Not specified",
                    "details": "Item identified through text analysis"
                })

        # Extract concerns
        concerns = []
        concern_patterns = [
            r'concern.*?(?:about|regarding|with)\s+([^.]{10,50})',
            r'problem.*?(?:with|about)\s+([^.]{10,50})',
            r'issue.*?(?:with|about|regarding)\s+([^.]{10,50})'
        ]

        for pattern in concern_patterns:
            matches = re.findall(pattern, transcript.lower())
            for match in matches[:5]:
                concerns.append(match.strip().capitalize())

        return {
            "summary": f"Community Board meeting with {word_count:,} words of discussion covering {len(main_topics)} main topic areas. Analysis identified {decision_count} decision-related items and {concern_count} community concerns through enhanced keyword detection.",
            "keyDecisions": decisions if decisions else [
                {
                    "item": "Meeting Analysis Completed",
                    "outcome": "Processed",
                    "vote": "N/A",
                    "details": f"Enhanced analysis processed {word_count:,} words with {decision_count} decision indicators"
                }
            ],
            "publicConcerns": concerns if concerns else [
                f"Enhanced analysis detected {concern_count} concern-related discussions requiring detailed review"
            ],
            "nextSteps": [
                "Review detailed transcript for specific action items",
                "Follow up on identified concerns and decisions",
                "Consider manual review for complex discussions"
            ],
            "sentiment": "Mixed",
            "attendance": f"Meeting transcript: {word_count:,} words analyzed",
            "mainTopics": main_topics if main_topics else ["Community Board Meeting"],
            "importantDates": [],
            "budgetItems": [],
            "addresses": []
        }

    def save_analysis(self, video_id: str, analysis: Dict, transcript: str, processing_time: float, method: str = "enhanced"):
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO meeting_analysis 
                (video_id, analysis_json, transcript_length, processing_time, created_at, analysis_method)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                video_id,
                json.dumps(analysis, indent=2),
                len(transcript),
                processing_time,
                datetime.now().isoformat(),
                method
            ))

            conn.commit()
            conn.close()
            logger.info(f"Analysis saved for video: {video_id}")

        except Exception as e:
            logger.error(f"Failed to save analysis: {e}")

    def save_full_transcript(self, video_id: str, transcript: str):
        try:
            output_dir.mkdir(exist_ok=True)
            transcript_file = output_dir / f"{video_id}_transcript.txt"
            
            formatted_transcript = self.format_transcript_for_readability(transcript)

            with open(transcript_file, 'w', encoding='utf-8') as f:
                f.write(formatted_transcript)

            # Update database
            conn = self.get_db_connection()
            cursor = conn.cursor()

            try:
                cursor.execute('ALTER TABLE meeting_analysis ADD COLUMN full_transcript TEXT')
            except sqlite3.OperationalError:
                pass

            cursor.execute('''
                UPDATE meeting_analysis 
                SET full_transcript = ? 
                WHERE video_id = ?
            ''', (transcript, video_id))

            conn.commit()
            conn.close()

            logger.info(f"Full transcript saved for {video_id}")

        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")

    def format_transcript_for_readability(self, transcript: str) -> str:
        try:
            import re
            
            formatted = f"# CB Meeting Transcript\n"
            formatted += f"# Processed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            formatted += f"# Word Count: {len(transcript.split()):,}\n"
            formatted += f"# Character Count: {len(transcript):,}\n\n"
            formatted += "=" * 60 + "\n\n"
            
            # Split into sentences and add line breaks
            sentences = re.split(r'(?<=[.!?])\s+', transcript)
            
            current_paragraph = []
            line_count = 0
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                current_paragraph.append(sentence)
                line_count += 1
                
                # Create new paragraph every 3-4 sentences or at natural breaks
                if (line_count >= 3 and 
                    (any(marker in sentence.lower() for marker in 
                    ['chair:', 'member:', 'motion', 'vote', 'resolution', 'next item', 'thank you']) or
                    line_count >= 4)):
                    
                    formatted += ' '.join(current_paragraph) + '\n\n'
                    current_paragraph = []
                    line_count = 0
            
            # Add any remaining sentences
            if current_paragraph:
                formatted += ' '.join(current_paragraph) + '\n\n'
            
            return formatted
            
        except Exception as e:
            logger.warning(f"Transcript formatting failed: {e}")
            return transcript.replace('. ', '.\n\n')

    def generate_summary_file(self, video_id: str, title: str, markdown: str) -> Path:
        """
        Save a pre-rendered Markdown summary to disk and return its Path.
        """
        try:
            summary_file = output_dir / f"{video_id}_summary.md"
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            logger.info(f"Summary file saved: {summary_file}")
            return summary_file
        except Exception as e:
            logger.error(f"Failed to generate summary file: {e}")
            raise

# Initialize processor
processor = CBProcessor()
cb_fetcher = CBChannelFetcher()
executor = ThreadPoolExecutor(max_workers=2)
db_handler = DBHandler()

# API Endpoints
@app.on_event("startup")
async def startup_event():
    logger.info("CB Meeting Processor starting up...")
    logger.info("Server ready for processing requests")

@app.get("/")
async def root():
    return {
        "message": "CB Meeting Processor API",
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "process_youtube": "/process-youtube",
            "process_file": "/process-file",
            "recent_videos": "/videos",
            "processed_meetings": "/meetings"
        }
    }

@app.get("/health")
async def health_check():
    try:
        conn = processor.get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_status = True
    except:
        db_status = False

    status = HealthStatus(
        whisper=whisper_model is not None,
        ffmpeg=processor.check_ffmpeg(),
        yt_dlp=True,
        database=db_status,
    )

    return status

@app.post("/process-youtube")
async def process_youtube_video(request: ProcessRequest):
    start_time = time.time()

    try:
        logger.info(f"Processing YouTube video: {request.url}")

        # Extract video info
        video_info = processor.extract_video_info(request.url)
        video_id = video_info['video_id']
        title = video_info['title']
        cb_number = cb_fetcher.infer_cb_from_title(video_info['title'])
        
        if cb_number:
            logger.info(f"Detected CB{cb_number} from title: {title}")
            
        # Check if it looks like a meeting
        if not processor.is_meeting_video(title, video_info.get('description', '')):
            logger.warning(f"Video may not be a meeting: {title}")

        # Mark as processing immediately
        with db_handler.get_db(readonly=False) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO processed_videos 
                (video_id, title, url, published_at, processed_at, status, cb_number, cb_district)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                video_id,
                title,
                request.url,
                video_info.get('upload_date', datetime.now().isoformat()),
                datetime.now().isoformat(),
                'processing',
                cb_number,
                'Manhattan' if cb_number else None
            ))

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Step 1: Extract audio
                logger.info("Extracting audio...")
                audio_path, extracted_title = processor.extract_audio_from_youtube(
                    request.url, temp_dir)

                # Step 2: Transcribe
                logger.info("Transcribing audio...")
                transcript = processor.transcribe_audio(audio_path)
                
                # Save transcript immediately (quick operation)
                processor.save_full_transcript(video_id, transcript)
                
                # Update database with transcript info
                db_handler.save_analysis_incremental(video_id, {}, transcript)

                # Step 3: Summarize with new logic
                logger.info("Summarizing transcript with Gemini...")
                
                # Try to extract meeting date from title or transcript
                meeting_date = processor.extract_meeting_date(title, transcript)
                if not meeting_date:
                    meeting_date = date.today().isoformat()
                    logger.warning(f"Could not extract meeting date, using today's date: {meeting_date}")
                
                summary_obj, summary_md = processor.summarize_with_gemini(
                    transcript,
                    meeting_date=meeting_date
                )

                # Convert summary object to the expected format
                summary_json = summary_obj.model_dump(mode="json")
                
                # Transform to match the expected API response format
                summary_parts = []

                # First paragraph: Meeting type and overview
                topic_titles = [t.title for t in summary_obj.topics]
                meeting_type = processor.identify_meeting_type(title, topic_titles)
                summary_parts.append(f"{meeting_type} held on {summary_obj.meeting_date} with {len(summary_obj.topics)} main topics discussed.")

                # Second paragraph: Key topics with details
                if summary_obj.topics:
                    topic_details = []
                    for topic in summary_obj.topics[:3]:  # First 3 topics
                        detail = f"{topic.title}"
                        if topic.speakers:
                            detail += f" (presented by {', '.join(topic.speakers[:2])})"
                        topic_details.append(detail)
                    summary_parts.append(f"The meeting covered: {'; '.join(topic_details)}.")

                # Third paragraph: Key outcomes
                total_decisions = sum(len(t.decisions) for t in summary_obj.topics)
                total_actions = sum(len(t.action_items) for t in summary_obj.topics)

                outcomes = []
                if total_decisions > 0:
                    outcomes.append(f"{total_decisions} decisions were made")
                if total_actions > 0:
                    outcomes.append(f"{total_actions} action items were assigned")

                # Add specific examples
                if summary_obj.topics and summary_obj.topics[0].decisions:
                    first_decision = summary_obj.topics[0].decisions[0]
                    outcomes.append(f"including {first_decision}")

                if outcomes:
                    summary_parts.append(f"Key outcomes: {', '.join(outcomes)}.")

                # Extract concerns from topic summaries
                concerns = []
                for topic in summary_obj.topics:
                    # Look for concern-related words in summaries
                    if any(word in topic.summary.lower() for word in ['concern', 'issue', 'problem', 'worry']):
                        # Extract the concern from the summary
                        concern_match = re.search(r'(?:concern|issue|problem|worry)(?:s|ed)?\s+(?:about|regarding|with)\s+([^.]+)', topic.summary, re.IGNORECASE)
                        if concern_match:
                            concerns.append(concern_match.group(1).strip())

                # NOW CREATE THE ANALYSIS DICTIONARY:
                analysis = {
                    "summary": " ".join(summary_parts),
                    "keyDecisions": [],
                    "publicConcerns": concerns[:10],  # Limit to 10 concerns
                    "nextSteps": [],
                    "sentiment": summary_obj.overall_sentiment.title(),
                    "attendance": processor.format_attendance_string(summary_obj.attendance),
                    "mainTopics": [topic.title for topic in summary_obj.topics],
                    "importantDates": [],
                    "budgetItems": [],
                    "addresses": [],
                    "summary_markdown": summary_md
                }

                # Extract decisions and action items from topics
                for topic in summary_obj.topics:
                    for decision in topic.decisions:
                        analysis["keyDecisions"].append({
                            "item": f"{topic.title}: {decision}",
                            "outcome": "Decided",
                            "vote": "See transcript",
                            "details": f"Part of {topic.title} discussion"
                        })
                    
                    for action_item in topic.action_items:
                        analysis["nextSteps"].append(
                            f"{action_item.task} (Owner: {action_item.owner}, Due: {action_item.due})"
                        )

                # Calculate processing time
                processing_time = time.time() - start_time

                # Step 4: Save results incrementally
                db_handler.save_analysis_incremental(
                    video_id, 
                    analysis, 
                    processing_time=processing_time
                )
                
                # Also save using the original method for compatibility
                processor.save_analysis(video_id, analysis, transcript, processing_time, method="gemini-summary")
                processor.generate_summary_file(video_id, title, summary_md)
                
                # Mark as completed - this is important!
                with db_handler.get_db(readonly=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE processed_videos 
                        SET status = 'completed'
                        WHERE video_id = ?
                    """, (video_id,))
                
                logger.info(f"Processing completed in {processing_time:.1f} seconds")

                return {
                    "success": True,
                    "video_id": video_id,
                    "title": title,
                    "analysis": analysis,
                    "summary_json": summary_json,
                    "summary_markdown": summary_md,
                    "processingTime": f"{processing_time:.1f} seconds",
                    "transcriptLength": len(transcript),
                    "wordCount": len(transcript.split())
                }

            except Exception as e:
                # Mark as failed
                with db_handler.get_db(readonly=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE processed_videos 
                        SET status = 'failed', error_message = ?
                        WHERE video_id = ?
                    """, (str(e), video_id))
                
                logger.error(f"Processing error: {e}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    except Exception as e:
        logger.error(f"YouTube processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-file")
async def process_uploaded_file(file: UploadFile = File(...)):
    start_time = time.time()

    try:
        logger.info(f"Processing uploaded file: {file.filename}")

        # Validate file type
        if not file.content_type or not (
            file.content_type.startswith('video/') or
            file.content_type.startswith('audio/')
        ):
            raise HTTPException(
                status_code=400, detail="Please upload a video or audio file")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            file_path = Path(temp_dir) / file.filename
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

            logger.info(f"File saved: {file_path} ({len(content)} bytes)")

            # Extract audio
            audio_path = processor.extract_audio_from_file(str(file_path), temp_dir)

            # Transcribe
            transcript = processor.transcribe_audio(audio_path)

            # Generate a video ID for the file
            video_id = f"file_{int(start_time)}"
            processor.save_full_transcript(video_id, transcript)

            # Summarize with new logic
            logger.info("Summarizing transcript with Gemini...")
            summary_obj, summary_md = processor.summarize_with_gemini(
                transcript,
                meeting_date=date.today().isoformat()
            )

            # Convert summary object to the expected format
            summary_json = summary_obj.model_dump(mode="json")
            
            # Transform to match the expected API response format
            # Create a detailed summary from the topics
            summary_parts = []
            
            # First paragraph: Meeting type and overview
            topic_titles = [t.title for t in summary_obj.topics]
            meeting_type = processor.identify_meeting_type(file.filename, topic_titles)
            summary_parts.append(f"{meeting_type} held on {summary_obj.meeting_date} with {len(summary_obj.topics)} main topics discussed.")
            
            # Second paragraph: Key topics with details
            if summary_obj.topics:
                topic_details = []
                for topic in summary_obj.topics[:3]:  # First 3 topics
                    detail = f"{topic.title}"
                    if topic.speakers:
                        detail += f" (presented by {', '.join(topic.speakers[:2])})"
                    topic_details.append(detail)
                summary_parts.append(f"The meeting covered: {'; '.join(topic_details)}.")
            
            # Third paragraph: Key outcomes
            total_decisions = sum(len(t.decisions) for t in summary_obj.topics)
            total_actions = sum(len(t.action_items) for t in summary_obj.topics)
            
            outcomes = []
            if total_decisions > 0:
                outcomes.append(f"{total_decisions} decisions were made")
            if total_actions > 0:
                outcomes.append(f"{total_actions} action items were assigned")
            
            # Add specific examples
            if summary_obj.topics and summary_obj.topics[0].decisions:
                first_decision = summary_obj.topics[0].decisions[0]
                outcomes.append(f"including {first_decision}")
            
            if outcomes:
                summary_parts.append(f"Key outcomes: {', '.join(outcomes)}.")
            
            # Extract concerns from topic summaries
            concerns = []
            for topic in summary_obj.topics:
                # Look for concern-related words in summaries
                if any(word in topic.summary.lower() for word in ['concern', 'issue', 'problem', 'worry']):
                    # Extract the concern from the summary
                    import re
                    concern_match = re.search(r'(?:concern|issue|problem|worry)(?:s|ed)?\s+(?:about|regarding|with)\s+([^.]+)', topic.summary, re.IGNORECASE)
                    if concern_match:
                        concerns.append(concern_match.group(1).strip())
            
            analysis = {
                "summary": " ".join(summary_parts),
                "keyDecisions": [],
                "publicConcerns": concerns[:10],  # Limit to 10 concerns
                "nextSteps": [],
                "sentiment": summary_obj.overall_sentiment.title(),
                "attendance": processor.format_attendance_string(summary_obj.attendance),
                "mainTopics": [topic.title for topic in summary_obj.topics],
                "importantDates": [],
                "budgetItems": [],
                "addresses": [],
                "summary_markdown": summary_md 
            }

            # Extract decisions and action items from topics
            for topic in summary_obj.topics:
                for decision in topic.decisions:
                    analysis["keyDecisions"].append({
                        "item": f"{topic.title}: {decision}",
                        "outcome": "Decided",
                        "vote": "See transcript",
                        "details": f"Part of {topic.title} discussion"
                    })
                
                for action_item in topic.action_items:
                    analysis["nextSteps"].append(
                        f"{action_item.task} (Owner: {action_item.owner}, Due: {action_item.due})"
                    )

            # Calculate processing time
            processing_time = time.time() - start_time

            # Save results
            processor.save_analysis(video_id, analysis, transcript, processing_time, method="gemini-summary")
            processor.generate_summary_file(video_id, file.filename, summary_md)
            
            logger.info(f"File processing completed in {processing_time:.1f} seconds")

            return {
                "success": True,
                "video_id": video_id,
                "title": file.filename,
                "analysis": analysis,
                "summary_json": summary_json,
                "summary_markdown": summary_md,
                "processingTime": f"{processing_time:.1f} seconds",
                "transcriptLength": len(transcript),
                "wordCount": len(transcript.split())
            }

    except Exception as e:
        logger.error(f"File processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meetings")
async def get_processed_meetings():
    try:
        conn = processor.get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT p.video_id, p.title, p.processed_at, p.status, 
                   m.analysis_json, m.processing_time, m.analysis_method
            FROM processed_videos p
            LEFT JOIN meeting_analysis m ON p.video_id = m.video_id
            ORDER BY p.processed_at DESC
            LIMIT 50
        ''')

        meetings = []
        for row in cursor.fetchall():
            meeting = {
                "video_id": row[0],
                "title": row[1],
                "processed_at": row[2],
                "status": row[3],
                "processing_time": row[5],
                "analysis_method": row[6] or "basic"
            }

            if row[4]:  # analysis_json exists
                try:
                    meeting["analysis"] = json.loads(row[4])
                except:
                    pass

            meetings.append(meeting)

        conn.close()
        return {"meetings": meetings}

    except Exception as e:
        logger.error(f"Failed to get meetings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analyze-transcript/{video_id}")
async def analyze_existing_transcript(video_id: str):
    try:
        # Load transcript from file
        transcript_file = output_dir / f"{video_id}_transcript.txt"
        if not transcript_file.exists():
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        with open(transcript_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Skip header if present
            if '============' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if '============' in line and i < len(lines) - 1:
                        content = '\n'.join(lines[i + 1:])
                        break
    
        # Enhanced analyzer
        analyzer = CBAnalyzer()  
        
        # Quick analysis without full AI processing
        vote_records = analyzer.extract_all_votes(content)
        
        # Convert to response format
        decisions = []
        for vote in vote_records:
            decisions.append({
                "item": vote.item,
                "outcome": vote.outcome,
                "vote": vote.vote_count,
                "type": vote.vote_type,
                "confidence": vote.confidence
            })
        
        return {
            "video_id": video_id,
            "vote_count": len(decisions),
            "decisions": decisions,
            "transcript_length": len(content)
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

@app.get("/api/cb/list")
async def get_cb_list():
    """Get list of all community boards"""
    boards = []
    for key, info in CBChannelFetcher.CB_CHANNELS.items():
        boards.append({
            "key": key,
            "number": info['number'],
            "name": info['name'],
            "district": info['district'],
            "has_channel": bool(info['url'])
        })
    
    boards.sort(key=lambda x: x['number'])
    return {"boards": boards}

@app.get("/api/cb/{cb_number}/meetings")
async def get_cb_meetings(cb_number: int, limit: int = 20):
    """Get processed meetings for a specific CB"""
    logger.info(f"API called: get_cb_meetings for CB{cb_number}")
    
    try:
        # Add asyncio timeout to prevent hanging
        import asyncio
        
        # Run the database operation in a thread pool with timeout
        loop = asyncio.get_event_loop()
        meetings = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                cb_fetcher.get_processed_meetings_by_cb, 
                cb_number, 
                limit
            ),
            timeout=10.0  # 10 second timeout
        )
        
        logger.info(f"Got {len(meetings)} meetings from database")
        
        # Parse the analysis JSON
        for meeting in meetings:
            if meeting.get('analysis'):
                try:
                    meeting['analysis'] = json.loads(meeting['analysis'])
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for {meeting.get('video_id')}: {e}")
                    meeting['analysis'] = None
                except Exception as e:
                    logger.error(f"Unexpected error parsing JSON: {e}")
                    meeting['analysis'] = None
        
        response_data = {
            "cb_number": cb_number,
            "meetings": meetings,
            "total": len(meetings)
        }
        
        logger.info(f"Returning response with {len(meetings)} meetings")
        return response_data
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching meetings for CB{cb_number}")
        return JSONResponse(
            status_code=504,
            content={
                "error": "Database query timed out",
                "cb_number": cb_number,
                "meetings": [],
                "total": 0
            }
        )
    except Exception as e:
        logger.error(f"Failed to get CB{cb_number} meetings: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "details": str(e),
                "cb_number": cb_number,
                "meetings": [],
                "total": 0
            }
        )

@app.post("/api/cb/{cb_key}/fetch-videos")
async def fetch_cb_videos(cb_key: str, max_results: int = 30):
    """Fetch new videos from a CB channel"""
    try:
        # Run in background to avoid blocking
        loop = asyncio.get_event_loop()
        videos = await loop.run_in_executor(
            executor, 
            cb_fetcher.fetch_channel_videos, 
            cb_key, 
            max_results
        )
        
        # Save new videos
        new_count = 0
        for video in videos:
            if cb_fetcher.save_video_info(video):
                new_count += 1
        
        return {
            "cb_key": cb_key,
            "videos_found": len(videos),
            "new_videos": new_count
        }
    except Exception as e:
        logger.error(f"Failed to fetch videos for {cb_key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cb/process-pending")
async def process_pending_videos(cb_number: Optional[int] = None, limit: int = 5):
    """Process pending videos (can be called periodically)"""
    try:
        pending = cb_fetcher.get_pending_videos(cb_number, limit)
        
        processing_tasks = []
        for video in pending:
            # Mark as processing
            cb_fetcher.mark_video_processed(video['video_id'], 'processing')
            
            # Add to processing queue
            processing_tasks.append({
                "video_id": video['video_id'],
                "title": video['title'],
                "url": video['url'],
                "cb_number": video['cb_number']
            })
        
        return {
            "pending_count": len(pending),
            "processing": processing_tasks
        }
    except Exception as e:
        logger.error(f"Failed to get pending videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cb/process-video/{video_id}")
async def process_cb_video(video_id: str):
    """Process a specific video from the queue"""
    try:
        # Get video info
        conn = processor.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT url, title, cb_number FROM processed_videos WHERE video_id = ?', 
            (video_id,)
        )
        video_info = cursor.fetchone()
        conn.close()
        
        if not video_info:
            raise HTTPException(status_code=404, detail="Video not found")
        
        url, title, cb_number = video_info
        
        # Process the video using existing logic
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract audio
            audio_path, _ = processor.extract_audio_from_youtube(url, temp_dir)
            
            # Transcribe
            transcript = processor.transcribe_audio(audio_path)
            processor.save_full_transcript(video_id, transcript)
            
            # Analyze with Gemini
            meeting_date = processor.extract_meeting_date(title, transcript)
            if not meeting_date:
                meeting_date = datetime.now().date().isoformat()
            
            summary_obj, summary_md = processor.summarize_with_gemini(transcript, meeting_date)
            
            # Convert to analysis format
            analysis = {
                "summary": summary_obj.model_dump()["topics"][0]["summary"] if summary_obj.topics else "",
                "keyDecisions": [],
                "publicConcerns": [],
                "nextSteps": [],
                "sentiment": summary_obj.overall_sentiment,
                "attendance": processor.format_attendance_string(summary_obj.attendance),
                "mainTopics": [t.title for t in summary_obj.topics],
                "cb_number": cb_number,
                "summary_markdown": summary_md 
            }
            
            # Extract decisions and actions
            for topic in summary_obj.topics:
                for decision in topic.decisions:
                    analysis["keyDecisions"].append({
                        "item": f"{topic.title}: {decision}",
                        "outcome": "Decided",
                        "vote": "See transcript",
                        "details": f"Part of {topic.title} discussion"
                    })
                
                for action in topic.action_items:
                    analysis["nextSteps"].append(
                        f"{action.task} (Owner: {action.owner}, Due: {action.due})"
                    )
            
            # Save analysis
            processor.save_analysis(video_id, analysis, transcript, 0, "auto-process")
            
            # Mark as completed
            cb_fetcher.mark_video_processed(video_id, 'completed')
            
            return {
                "success": True,
                "video_id": video_id,
                "title": title,
                "cb_number": cb_number,
                "analysis": analysis
            }
            
    except Exception as e:
        logger.error(f"Failed to process video {video_id}: {e}")
        # Mark as failed
        cb_fetcher.mark_video_processed(video_id, 'failed')
        raise HTTPException(status_code=500, detail=str(e))

# Add a simpler test endpoint to verify the database is accessible:
@app.get("/api/test/cb/{cb_number}/count")
async def test_cb_count(cb_number: int):
    """Simple test to count meetings without complex queries"""
    try:
        conn = sqlite3.connect(cb_fetcher.db_path, timeout=2.0)
        cursor = conn.cursor()
        
        # Simple count query
        cursor.execute(
            "SELECT COUNT(*) FROM processed_videos WHERE cb_number = ?", 
            (cb_number,)
        )
        count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "cb_number": cb_number,
            "count": count,
            "status": "ok"
        }
    except Exception as e:
        return {
            "cb_number": cb_number,
            "error": str(e),
            "status": "error"
        }

# temporary debug endpoint to your main.py to test

@app.get("/api/cb/{cb_number}/meetings-debug")
async def get_cb_meetings_debug(cb_number: int, limit: int = 20):
    """Debug version with better error handling"""
    logger.info(f"Debug: Fetching meetings for CB{cb_number}")
    
    try:
        # Test 1: Can we connect to the database?
        conn = processor.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_videos WHERE cb_number = ?", (cb_number,))
        total_count = cursor.fetchone()[0]
        logger.info(f"Debug: Found {total_count} total videos for CB{cb_number}")
        conn.close()
        
        # Test 2: Try the actual query
        meetings = cb_fetcher.get_processed_meetings_by_cb(cb_number, limit)
        logger.info(f"Debug: Retrieved {len(meetings)} meetings")
        
        # Test 3: Parse the analysis JSON
        for meeting in meetings:
            if meeting.get('analysis'):
                try:
                    meeting['analysis'] = json.loads(meeting['analysis'])
                    logger.info(f"Debug: Parsed analysis for {meeting['video_id']}")
                except Exception as e:
                    logger.error(f"Debug: Failed to parse analysis for {meeting['video_id']}: {e}")
                    meeting['analysis'] = None
        
        return {
            "cb_number": cb_number,
            "meetings": meetings,
            "total": len(meetings),
            "debug": {
                "total_in_db": total_count,
                "retrieved": len(meetings),
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Debug endpoint failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            "cb_number": cb_number,
            "meetings": [],
            "total": 0,
            "error": str(e),
            "debug": {
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        }

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting CB Meeting Processor Server")
    logger.info("Server will be available at: http://localhost:8000")
    logger.info("Health check: http://localhost:8000/health")
    logger.info("API docs: http://localhost:8000/docs")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False
    )