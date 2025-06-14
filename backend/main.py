import tempfile
import shutil
import json
import sqlite3
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import subprocess

# FastAPI and server imports
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# AI and processing imports
import whisper
import yt_dlp

# Optional imports with fallbacks
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Ollama not available - will use basic analysis")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
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
    autonomous_mode: bool

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
        "http://localhost:3000",      # React dev server
        "http://127.0.0.1:3000",
        "http://localhost:3001",      # Alternative React port
        "http://127.0.0.1:3001",
        "http://localhost:5173",      # Vite dev server (if using Vite)
        "http://127.0.0.1:5173",
        "*"  # TEMPORARY - allows all origins for testing
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global variables
whisper_model = None
db_path = Path("backend/cb_meetings.db")
output_dir = Path("processed_meetings")
autonomous_running = False

# Processor class for cb meetings
class CBProcessor:
    def __init__(self):
        self.setup_directories()
        self.init_database()
        self.load_models()
    
    def setup_directories(self):
        output_dir.mkdir(exist_ok=True)
    
    # Database for tracking processed meetings
    def init_database(self):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create tables
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
                    error_message TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS meeting_analysis (
                    video_id TEXT PRIMARY KEY,
                    analysis_json TEXT,
                    transcript_length INTEGER,
                    processing_time REAL,
                    created_at TEXT,
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
    
    # Load AI models
    def load_models(self):
        global whisper_model
        
        try:
            logger.info("Loading Whisper model...")
            whisper_model = whisper.load_model("medium")  
            logger.info("Whisper model loaded successfully")
            
            # Test Ollama if available
            if OLLAMA_AVAILABLE:
                try:
                    models = ollama.list()
                    available_models = [model['name'] for model in models.get('models', [])]
                    if not ('llama3.1' in available_models or any('llama' in model for model in available_models)):
                        logger.warning("No suitable Ollama models found. Run: ollama pull llama3.1")
                except Exception as e:
                    logger.warning(f"Ollama connection issue: {e}")
            
        except Exception as e:
            logger.error(f"Model loading failed: {e}")
            return False
        
        return True
    
    def check_ffmpeg(self) -> bool:
        return shutil.which("ffmpeg") is not None
    
    # Extracting video info with link 
    def extract_video_info(self, url: str) -> Dict:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
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
    
    # Determine if it is a cb meeting
    def is_meeting_video(self, title: str, description: str = "") -> bool:
        meeting_keywords = [
            'board meeting', 'full board', 'committee meeting',
            'land use', 'parks', 'transportation', 'public meeting',
            'cb', 'community board', 'housing', 'zoning'
        ]
        
        combined_text = f"{title} {description}".lower()
        return any(keyword in combined_text for keyword in meeting_keywords)
    
    # Extract audio from yt video
    def extract_audio_from_youtube(self, url: str, output_path: str) -> tuple:
        try:
            logger.info(f"Extracting audio from: {url}")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{output_path}/audio.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': False,  # Show progress
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
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
        """Extract audio from uploaded video file"""
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
            
            logger.info(f"✅ Audio extracted from video: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"❌ Audio extraction from file failed: {e}")
            raise Exception(f"Audio extraction failed: {str(e)}")
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio using local Whisper"""
        try:
            if not whisper_model:
                raise Exception("Whisper model not loaded")
            
            logger.info(f"🎙️  Transcribing audio: {audio_path}")
            
            # Transcribe with Whisper
            result = whisper_model.transcribe(
                audio_path,
                language="en",  # Assume English for CB7 meetings
                task="transcribe"
            )
            
            transcript = result["text"].strip()
            word_count = len(transcript.split())
            
            logger.info(f"✅ Transcription complete: {word_count} words")
            return transcript
            
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            raise Exception(f"Transcription failed: {str(e)}")
    
    def analyze_with_ollama(self, transcript: str) -> Dict:
        """Analyze transcript with local Ollama"""
        if not OLLAMA_AVAILABLE:
            return self.create_basic_analysis(transcript)
        
        try:
            logger.info("🧠 Analyzing transcript with local AI...")
            
            # Choose the best available model
            models = ollama.list()
            available_models = []
            for model in models.get('models', []):
                if 'name' in model:
                    available_models.append(model['name'])
                elif 'model' in model:
                    available_models.append(model['model'])
                else:
                # Debug: see what keys are actually available
                    print(f"Debug - Model keys: {model.keys()}")
            
            # Preferred model order
            preferred_models = ['llama3.1', 'llama3', 'mistral', 'codellama']
            selected_model = 'llama3.1:latest'
            
            for model in preferred_models:
                if any(model in available for available in available_models):
                    selected_model = next(available for available in available_models if model in available)
                    break
            
            if not selected_model:
                logger.warning("⚠️  No suitable AI model found")
                return self.create_basic_analysis(transcript)
            
            # Create analysis prompt
            prompt = f"""
            Analyze this Community Board 7 meeting transcript. Extract information in this exact JSON format:

            {{
                "summary": "Brief 2-3 sentence overview of the meeting",
                "keyDecisions": [
                    {{"item": "Decision topic", "outcome": "Approved/Rejected/Tabled/Supported", "vote": "X-Y or Unanimous", "details": "Brief explanation of the decision"}}
                ],
                "publicConcerns": ["Community concern or complaint raised by residents"],
                "nextSteps": ["Specific action items or follow-up tasks mentioned"],
                "sentiment": "Positive/Generally Positive/Mixed/Cautiously Optimistic/Negative",
                "attendance": "Number of board members and community members if mentioned",
                "mainTopics": ["Major topics discussed like Transportation, Housing, Parks, etc."],
                "importantDates": ["Any important dates or deadlines mentioned"],
                "budgetItems": ["Budget amounts or financial items discussed"],
                "addresses": ["Specific addresses or locations mentioned"]
            }}

            Focus on concrete decisions, voting results, and actionable items. If information is not available, use empty arrays or appropriate defaults.

            Transcript (first 15000 characters):
            {transcript[:15000]}
            """
            
            # Get analysis from Ollama
            response = ollama.chat(
                model='llama3.1:latest',
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
            
            content = response['message']['content']
            
            # Try to extract JSON from response
            start = content.find('{')
            end = content.rfind('}') + 1
            
            if start != -1 and end != -1:
                json_str = content[start:end]
                analysis = json.loads(json_str)
                logger.info("✅ AI analysis completed successfully")
                return analysis
            else:
                logger.warning("⚠️  Could not parse AI response as JSON")
                return self.create_basic_analysis(transcript)
        
        except Exception as e:
            logger.error(f"❌ AI analysis failed: {e}")
            return self.create_basic_analysis(transcript)
    
    def create_basic_analysis(self, transcript: str) -> Dict:
        """Create basic analysis without AI (fallback)"""
        words = transcript.lower().split()
        word_count = len(words)
        
        # Simple keyword detection
        decision_keywords = ['approve', 'approved', 'reject', 'rejected', 'vote', 'motion', 'support', 'oppose']
        concern_keywords = ['concern', 'problem', 'issue', 'complaint', 'worried', 'traffic', 'noise']
        topic_keywords = {
            'Transportation': ['traffic', 'bike', 'bus', 'subway', 'parking', 'street'],
            'Housing': ['housing', 'apartment', 'rent', 'affordable', 'development'],
            'Parks': ['park', 'playground', 'tree', 'garden', 'recreation'],
            'Zoning': ['zoning', 'building', 'construction', 'permit']
        }
        
        decision_count = sum(1 for word in words if word in decision_keywords)
        concern_count = sum(1 for word in words if word in concern_keywords)
        
        # Detect main topics
        main_topics = []
        for topic, keywords in topic_keywords.items():
            if any(keyword in words for keyword in keywords):
                main_topics.append(topic)
        
        return {
            "summary": f"Community Board 7 meeting with {word_count} words of discussion. {decision_count} potential decisions and {concern_count} concerns identified through keyword analysis.",
            "keyDecisions": [
                {
                    "item": "Meeting Analysis", 
                    "outcome": "Basic analysis completed", 
                    "vote": "N/A", 
                    "details": "Full AI analysis requires Ollama installation with llama3.1 model"
                }
            ],
            "publicConcerns": ["Install Ollama for detailed concern analysis"],
            "nextSteps": ["Install Ollama and run 'ollama pull llama3.1' for full AI analysis"],
            "sentiment": "Mixed",
            "attendance": "Not analyzed without AI",
            "mainTopics": main_topics if main_topics else ["Community Board Meeting"],
            "importantDates": [],
            "budgetItems": [],
            "addresses": []
        }
    
    def save_analysis(self, video_id: str, analysis: Dict, transcript: str, processing_time: float):
        """Save analysis results to database"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO meeting_analysis 
                (video_id, analysis_json, transcript_length, processing_time, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                video_id,
                json.dumps(analysis),
                len(transcript),
                processing_time,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Analysis saved for video: {video_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save analysis: {e}")
    
    def generate_summary_file(self, video_id: str, title: str, analysis: Dict):
        """Generate human-readable summary file"""
        try:
            summary_file = output_dir / f"{video_id}_summary.md"
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n")
                f.write(f"**Processed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**Video ID:** {video_id}\n\n")
                
                f.write(f"## Summary\n{analysis.get('summary', 'No summary available')}\n\n")
                
                if analysis.get('keyDecisions'):
                    f.write("## Key Decisions\n")
                    for decision in analysis['keyDecisions']:
                        f.write(f"- **{decision.get('item', 'Unknown')}**: {decision.get('outcome', 'Unknown')} ({decision.get('vote', 'No vote recorded')})\n")
                        if decision.get('details'):
                            f.write(f"  - {decision['details']}\n")
                    f.write("\n")
                
                if analysis.get('publicConcerns'):
                    f.write("## Community Concerns\n")
                    for concern in analysis['publicConcerns']:
                        f.write(f"- {concern}\n")
                    f.write("\n")
                
                if analysis.get('nextSteps'):
                    f.write("## Next Steps\n")
                    for step in analysis['nextSteps']:
                        f.write(f"- {step}\n")
                    f.write("\n")
                
                if analysis.get('mainTopics'):
                    f.write("## Main Topics\n")
                    f.write(f"{', '.join(analysis['mainTopics'])}\n\n")
                
                f.write(f"**Meeting Sentiment:** {analysis.get('sentiment', 'Unknown')}\n")
                f.write(f"**Attendance:** {analysis.get('attendance', 'Not specified')}\n")
            
            logger.info(f"✅ Summary file saved: {summary_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to generate summary file: {e}")

# Initialize processor
processor = CBProcessor()

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("🚀 CB7 Meeting Processor starting up...")
    logger.info("✅ Server ready for processing requests")

@app.get("/")
async def root():
    """Root endpoint with basic info"""
    return {
        "message": "CB7 Meeting Processor API",
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
    """Comprehensive health check"""
    try:
        # Test database connection
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        db_status = True
    except:
        db_status = False
    
    # Test Ollama if available
    ollama_status = False
    if OLLAMA_AVAILABLE:
        try:
            ollama.list()
            ollama_status = True
        except:
            ollama_status = False
    
    status = HealthStatus(
        whisper=whisper_model is not None,
        ollama=ollama_status,
        ffmpeg=processor.check_ffmpeg(),
        yt_dlp=True,  # Already imported successfully
        database=db_status,
    )
    
    return status

@app.post("/process-youtube")
async def process_youtube_video(request: ProcessRequest):
    """Process a YouTube video URL"""
    start_time = time.time()
    
    try:
        logger.info(f"🎬 Processing YouTube video: {request.url}")
        
        # Extract video info
        video_info = processor.extract_video_info(request.url)
        video_id = video_info['video_id']
        title = video_info['title']
        
        # Check if it looks like a meeting
        if not processor.is_meeting_video(title, video_info.get('description', '')):
            logger.warning(f"⚠️  Video may not be a meeting: {title}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Step 1: Extract audio
            audio_path, extracted_title = processor.extract_audio_from_youtube(request.url, temp_dir)
            
            # Step 2: Transcribe
            transcript = processor.transcribe_audio(audio_path)
            
            # Step 3: Analyze
            analysis = processor.analyze_with_ollama(transcript)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Step 4: Save results
            processor.save_analysis(video_id, analysis, transcript, processing_time)
            processor.generate_summary_file(video_id, title, analysis)
            
            logger.info(f"✅ Processing completed in {processing_time:.1f} seconds")
            
            return {
                "success": True,
                "video_id": video_id,
                "title": title,
                "analysis": analysis,
                "processingTime": f"{processing_time:.1f} seconds",
                "transcriptLength": len(transcript),
                "wordCount": len(transcript.split())
            }
            
    except Exception as e:
        logger.error(f"❌ YouTube processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-file")
async def process_uploaded_file(file: UploadFile = File(...)):
    """Process an uploaded audio/video file"""
    start_time = time.time()
    
    try:
        logger.info(f"📁 Processing uploaded file: {file.filename}")
        
        # Validate file type
        if not file.content_type or not (
            file.content_type.startswith('video/') or 
            file.content_type.startswith('audio/')
        ):
            raise HTTPException(status_code=400, detail="Please upload a video or audio file")
        
        # Check file size (limit to 2GB)
        if hasattr(file, 'size') and file.size and file.size > 2 * 1024 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 2GB")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            file_path = Path(temp_dir) / file.filename
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            logger.info(f"📁 File saved: {file_path} ({len(content)} bytes)")
            
            # Step 1: Extract audio
            audio_path = processor.extract_audio_from_file(str(file_path), temp_dir)
            
            # Step 2: Transcribe
            transcript = processor.transcribe_audio(audio_path)
            
            # Step 3: Analyze
            analysis = processor.analyze_with_ollama(transcript)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Generate a video ID for the file
            video_id = f"file_{int(start_time)}"
            
            # Step 4: Save results
            processor.save_analysis(video_id, analysis, transcript, processing_time)
            processor.generate_summary_file(video_id, file.filename, analysis)
            
            logger.info(f"✅ File processing completed in {processing_time:.1f} seconds")
            
            return {
                "success": True,
                "video_id": video_id,
                "title": file.filename,
                "analysis": analysis,
                "processingTime": f"{processing_time:.1f} seconds",
                "transcriptLength": len(transcript),
                "wordCount": len(transcript.split())
            }
            
    except Exception as e:
        logger.error(f"❌ File processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meetings")
async def get_processed_meetings():
    """Get list of all processed meetings"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.video_id, p.title, p.processed_at, p.status, 
                   m.analysis_json, m.processing_time
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
                "processing_time": row[5]
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
        logger.error(f"❌ Failed to get meetings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos")
async def get_recent_cb7_videos():
    """Get recent CB7 videos from YouTube (for autonomous mode)"""
    try:
        channel_url = "https://www.youtube.com/channel/UC_n3st90mFiSeRVUl4m8ySQ/videos"
        
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'playlistend': 10,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            
            videos = []
            for entry in info['entries'][:10]:
                videos.append({
                    'video_id': entry['id'],
                    'title': entry.get('title', 'Unknown'),
                    'url': entry['url'],
                    'upload_date': entry.get('upload_date', ''),
                    'is_meeting': processor.is_meeting_video(entry.get('title', ''))
                })
            
            return {"videos": videos}
            
    except Exception as e:
        logger.error(f"❌ Failed to get CB7 videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Development and debugging endpoints
@app.get("/logs")
async def get_recent_logs():
    """Get recent system logs"""
    try:
        with open('cb7_processor.log', 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-100:]  # Last 100 lines
            return {"logs": recent_lines}
    except FileNotFoundError:
        return {"logs": ["No log file found"]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {str(e)}"]}

@app.post("/debug/test-whisper")
async def test_whisper():
    """Test Whisper model with a short audio sample"""
    try:
        if not whisper_model:
            raise Exception("Whisper model not loaded")
        
        # This would need a test audio file
        return {"status": "Whisper model loaded and ready"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/debug/test-ollama")
async def test_ollama():
    """Test Ollama connection"""
    try:
        if not OLLAMA_AVAILABLE:
            raise Exception("Ollama not available")
        
        models = ollama.list()
        return {"status": "Ollama available", "models": models}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting CB7 Meeting Processor Server")
    logger.info("📊 Server will be available at: http://localhost:8000")
    logger.info("🔍 Health check: http://localhost:8000/health")
    logger.info("📚 API docs: http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False  # Set to True for development
    )

def check_for_new_meetings():
    """Check for new CB7 meetings (autonomous mode)"""
    # Implementation would go here
    # This would check YouTube, identify new meetings, and process them
    pass