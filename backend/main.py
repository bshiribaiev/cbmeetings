import tempfile
import shutil
import json
import sqlite3
import time
import logging
import datetime
from pathlib import Path
from typing import List, Dict
import subprocess
import traceback

# FastAPI and server imports
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from enhanced_analyzer import EnhancedCBAnalyzer, VoteRecord
from audio_utils import chunk_on_silence
from diarize import transcribe_whisper
from cleanup import clean_transcript
from summarize import summarize_transcript
from render_md import md_from_summary

# AI and processing imports
# import whisper
import yt_dlp

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
    ollama: bool
    ffmpeg: bool
    yt_dlp: bool
    database: bool
    ollama_models: List[str] = []

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
        "*"  # TEMPORARY - for development
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

    def setup_directories(self):
        output_dir.mkdir(exist_ok=True)

    def init_database(self):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Create tables with better error handling
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

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    message TEXT,
                    data TEXT
                )
            ''')

            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def check_ffmpeg(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def clean_youtube_url(self, url: str) -> str:
        import re
        match = re.search(r'[?&]v=([^&]+)', url)
        if match:
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"
        return url

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
        segments = chunk_on_silence(Path(audio_path))
        merged = {"segments": []}
        for seg in segments:
            merged["segments"].extend(transcribe_whisper(seg)["segments"])

        seg_df, low_df = clean_transcript(merged)
        transcript = " ".join(seg_df.text.tolist())
        # optional: low_df.to_csv("review_needed.csv", index=False)
        return transcript
    
    def summarize_with_gemini(self, transcript: str, meeting_date: str):
        summary_obj = summarize_transcript(transcript, meeting_date)
        summary_md  = md_from_summary(summary_obj)
        return summary_obj, summary_md

    def analyze_with_gemini(self, transcript: str, title: str = None) -> Dict:
        try:
            transcript_length = len(transcript)
            word_count = len(transcript.split())
            
            logger.info(f"Analyzing transcript with Gemini: {transcript_length:,} chars, {word_count:,} words")
            
            # Use enhanced analyzer with Gemini
            analyzer = EnhancedCBAnalyzer()
            
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
            conn = sqlite3.connect(db_path)
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
            conn = sqlite3.connect(db_path)
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
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        db_status = True
    except:
        db_status = False

    ollama_status = False
    ollama_models = []

    status = HealthStatus(
        whisper=True,
        ollama=ollama_status,
        ffmpeg=processor.check_ffmpeg(),
        yt_dlp=True,
        database=db_status,
        ollama_models=ollama_models
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

        # Check if it looks like a meeting
        if not processor.is_meeting_video(title, video_info.get('description', '')):
            logger.warning(f"Video may not be a meeting: {title}")

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Step 1: Extract audio
                logger.info("Extracting audio...")
                audio_path, extracted_title = processor.extract_audio_from_youtube(
                    request.url, temp_dir)

                # Step 2: Transcribe
                logger.info("Transcribing audio...")
                transcript = processor.transcribe_audio(audio_path)
                processor.save_full_transcript(video_id, transcript)

                # Step 3: Analyze
                logger.info("Analyzing transcript with Gemini...")
                summary_obj, summary_md = processor.summarize_with_gemini(
                    transcript,
                    meeting_date=datetime.date.today().isoformat()
)

                # Calculate processing time
                summary_json = summary_obj.model_dump(mode="json")
                processing_time = time.time() - start_time

                # Step 4: Persist & render
                processor.save_analysis(video_id, summary_json, transcript,
                                        processing_time, method="gemini-summary")
                processor.generate_summary_file(video_id, title, summary_md)
                return {
                    "success": True,
                    "video_id": video_id,
                    "title": title,
                    "summary_json": summary_json,
                    "summary_markdown": summary_md,
                    "processingTime": f"{processing_time:.1f} seconds",
                    "transcriptLength": len(transcript),
                    "wordCount": len(transcript.split())
                }

            except Exception as e:
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

            # Analyze
            summary_obj, summary_md = processor.summarize_with_gemini(
                    transcript,
                    meeting_date=datetime.date.today().isoformat()
)

                # Calculate processing time
            summary_json = summary_obj.model_dump(mode="json")
            processing_time = time.time() - start_time

            # Step 4: Persist & render
            processor.save_analysis(video_id, summary_json, transcript,
                                    processing_time, method="gemini-summary")
            processor.generate_summary_file(video_id, file.filename, summary_md)
            return {
                "success": True,
                "video_id": video_id,
                "title": file.filename,
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
        conn = sqlite3.connect(db_path)
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
        analyzer = EnhancedCBAnalyzer()  
        
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