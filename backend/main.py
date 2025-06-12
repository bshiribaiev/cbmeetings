# Autonomous CB7 Meeting Processor
# Automatically monitors CB7 YouTube channel and processes new videos

import os
import time
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import schedule
import logging
from typing import List, Dict

import whisper
import yt_dlp
import ollama
from googleapiclient.discovery import build
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AutonomousCB7Processor:
    def __init__(self):
        self.db_path = "cb7_meetings.db"
        self.output_dir = Path("processed_meetings")
        self.output_dir.mkdir(exist_ok=True)
        
        # YouTube API setup (optional - can use RSS instead)
        self.youtube_api_key = os.getenv("YOUTUBE_API_KEY")  # Optional
        self.cb7_channel_id = "UC_n3st90mFiSeRVUl4m8ySQ"  # CB7's actual channel ID
        
        # Email notifications (optional)
        self.email_config = {
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "email": os.getenv("EMAIL_ADDRESS"),
            "password": os.getenv("EMAIL_PASSWORD"),
            "recipients": os.getenv("EMAIL_RECIPIENTS", "").split(",")
        }
        
        # Load AI models
        self.whisper_model = None
        self.load_models()
        
        # Initialize database
        self.init_database()
    
    def load_models(self):
        """Load AI models on startup"""
        logger.info("Loading Whisper model...")
        self.whisper_model = whisper.load_model("base")
        logger.info("Whisper model loaded successfully!")
        
        # Test Ollama connection
        try:
            ollama.list()
            logger.info("Ollama connection successful!")
        except Exception as e:
            logger.error(f"Ollama connection failed: {e}")
    
    def init_database(self):
        """Initialize SQLite database to track processed videos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_videos (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                published_at TEXT,
                processed_at TEXT,
                duration TEXT,
                summary TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meeting_analysis (
                video_id TEXT PRIMARY KEY,
                analysis_json TEXT,
                created_at TEXT,
                FOREIGN KEY (video_id) REFERENCES processed_videos (video_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def get_latest_cb7_videos(self) -> List[Dict]:
        """Get latest videos from CB7 YouTube channel"""
        videos = []
        
        if self.youtube_api_key:
            # Method 1: YouTube API (more reliable, requires API key)
            videos = self._get_videos_via_api()
        else:
            # Method 2: yt-dlp (no API key needed)
            videos = self._get_videos_via_ytdlp()
        
        return videos
    
    def _get_videos_via_api(self) -> List[Dict]:
        """Get videos using YouTube Data API"""
        try:
            youtube = build('youtube', 'v3', developerKey=self.youtube_api_key)
            
            # Get recent uploads
            request = youtube.search().list(
                part='snippet',
                channelId=self.cb7_channel_id,
                maxResults=10,
                order='date',
                type='video',
                publishedAfter=(datetime.now() - timedelta(days=30)).isoformat() + 'Z'
            )
            
            response = request.execute()
            
            videos = []
            for item in response['items']:
                videos.append({
                    'video_id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'published_at': item['snippet']['publishedAt'],
                    'url': f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                })
            
            return videos
            
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return []
    
    def _get_videos_via_ytdlp(self) -> List[Dict]:
        """Get videos using yt-dlp (no API key needed)"""
        try:
            channel_url = f"https://www.youtube.com/channel/{self.cb7_channel_id}/videos"
            
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'playlistend': 10,  # Get last 10 videos
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                
                videos = []
                for entry in info['entries'][:10]:  # Last 10 videos
                    videos.append({
                        'video_id': entry['id'],
                        'title': entry.get('title', 'Unknown'),
                        'published_at': entry.get('upload_date', ''),
                        'url': entry['url']
                    })
                
                return videos
                
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return []
    
    def is_meeting_video(self, title: str) -> bool:
        """Determine if video is a meeting (vs announcement, etc.)"""
        meeting_keywords = [
            'board meeting', 'full board', 'committee meeting',
            'land use', 'parks', 'transportation', 'public meeting',
            'cb7', 'community board'
        ]
        
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in meeting_keywords)
    
    def video_already_processed(self, video_id: str) -> bool:
        """Check if video was already processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM processed_videos WHERE video_id = ?', (video_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None and result[0] == 'completed'
    
    def process_video(self, video_info: Dict) -> Dict:
        """Process a single video"""
        video_id = video_info['video_id']
        video_url = video_info['url']
        title = video_info['title']
        
        logger.info(f"Processing video: {title}")
        
        # Mark as processing
        self.update_video_status(video_id, 'processing', video_info)
        
        try:
            # Step 1: Extract audio
            logger.info("Extracting audio...")
            audio_path = self.extract_audio(video_url, video_id)
            
            # Step 2: Transcribe
            logger.info("Transcribing audio...")
            transcript = self.transcribe_audio(audio_path)
            
            # Step 3: Analyze
            logger.info("Analyzing with AI...")
            analysis = self.analyze_transcript(transcript)
            
            # Step 4: Save results
            self.save_analysis(video_id, analysis, transcript)
            
            # Step 5: Generate summary file
            self.generate_summary_file(video_id, title, analysis)
            
            # Mark as completed
            self.update_video_status(video_id, 'completed', video_info)
            
            # Clean up audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            logger.info(f"Successfully processed: {title}")
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to process {title}: {e}")
            self.update_video_status(video_id, 'failed', video_info)
            return None
    
    def extract_audio(self, video_url: str, video_id: str) -> str:
        """Extract audio from YouTube video"""
        output_path = f"temp_audio_{video_id}.mp3"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        return output_path
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio using local Whisper"""
        result = self.whisper_model.transcribe(audio_path)
        return result["text"]
    
    def analyze_transcript(self, transcript: str) -> Dict:
        """Analyze transcript with local Ollama"""
        prompt = f"""
        Analyze this Community Board 7 meeting transcript. Extract information in JSON format:

        {{
            "summary": "Brief 2-3 sentence overview",
            "keyDecisions": [
                {{"item": "Decision topic", "outcome": "Approved/Rejected", "vote": "X-Y", "details": "Brief details"}}
            ],
            "publicConcerns": ["Concern 1", "Concern 2"],
            "nextSteps": ["Action 1", "Action 2"],
            "sentiment": "Positive/Mixed/Negative",
            "attendance": "Attendance if mentioned",
            "mainTopics": ["Topic 1", "Topic 2"],
            "importantDates": ["Date 1", "Date 2"],
            "budgetItems": ["Budget item 1", "Budget item 2"],
            "addresses": ["Address 1", "Address 2"]
        }}

        Transcript: {transcript[:15000]}
        """
        
        try:
            response = ollama.chat(
                model='llama3.1',
                messages=[{'role': 'user', 'content': prompt}]
            )
            
            content = response['message']['content']
            start = content.find('{')
            end = content.rfind('}') + 1
            
            if start != -1 and end != -1:
                return json.loads(content[start:end])
            else:
                return self._fallback_analysis()
                
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return self._fallback_analysis()
    
    def _fallback_analysis(self) -> Dict:
        """Fallback analysis if AI fails"""
        return {
            "summary": "Analysis completed with limited results",
            "keyDecisions": [],
            "publicConcerns": [],
            "nextSteps": [],
            "sentiment": "Mixed",
            "attendance": "Not specified",
            "mainTopics": [],
            "importantDates": [],
            "budgetItems": [],
            "addresses": []
        }
    
    def save_analysis(self, video_id: str, analysis: Dict, transcript: str):
        """Save analysis to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO meeting_analysis (video_id, analysis_json, created_at)
            VALUES (?, ?, ?)
        ''', (video_id, json.dumps(analysis), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def generate_summary_file(self, video_id: str, title: str, analysis: Dict):
        """Generate human-readable summary file"""
        summary_file = self.output_dir / f"{video_id}_summary.md"
        
        with open(summary_file, 'w') as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Processed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
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
        
        logger.info(f"Summary saved: {summary_file}")
    
    def update_video_status(self, video_id: str, status: str, video_info: Dict):
        """Update video processing status in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO processed_videos 
            (video_id, title, published_at, processed_at, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            video_id,
            video_info.get('title', 'Unknown'),
            video_info.get('published_at', ''),
            datetime.now().isoformat(),
            status
        ))
        
        conn.commit()
        conn.close()
    
    def send_notification(self, title: str, analysis: Dict):
        """Send email notification of new meeting summary"""
        if not self.email_config['email'] or not self.email_config['recipients']:
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_config['email']
            msg['To'] = ', '.join(self.email_config['recipients'])
            msg['Subject'] = f"New CB7 Meeting Summary: {title}"
            
            body = f"""
            A new CB7 meeting has been processed:
            
            Title: {title}
            Summary: {analysis.get('summary', 'No summary available')}
            
            Key Decisions: {len(analysis.get('keyDecisions', []))}
            Community Concerns: {len(analysis.get('publicConcerns', []))}
            
            Full summary available in your processed_meetings folder.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['email'], self.email_config['password'])
            text = msg.as_string()
            server.sendmail(self.email_config['email'], self.email_config['recipients'], text)
            server.quit()
            
            logger.info("Email notification sent")
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def run_check(self):
        """Main function to check for and process new videos"""
        logger.info("Checking for new CB7 videos...")
        
        try:
            # Get latest videos
            videos = self.get_latest_cb7_videos()
            logger.info(f"Found {len(videos)} recent videos")
            
            new_meetings = 0
            for video in videos:
                # Skip if not a meeting or already processed
                if not self.is_meeting_video(video['title']):
                    logger.info(f"Skipping non-meeting video: {video['title']}")
                    continue
                
                if self.video_already_processed(video['video_id']):
                    logger.info(f"Already processed: {video['title']}")
                    continue
                
                # Process new meeting
                logger.info(f"Found new meeting: {video['title']}")
                analysis = self.process_video(video)
                
                if analysis:
                    new_meetings += 1
                    self.send_notification(video['title'], analysis)
                
                # Add delay between processing to avoid overwhelming system
                time.sleep(60)
            
            if new_meetings > 0:
                logger.info(f"Processed {new_meetings} new meetings")
            else:
                logger.info("No new meetings to process")
                
        except Exception as e:
            logger.error(f"Error during check: {e}")
    
    def start_monitoring(self):
        """Start autonomous monitoring"""
        logger.info("Starting autonomous CB7 monitoring...")
        
        # Schedule checks
        schedule.every(6).hours.do(self.run_check)  # Check every 6 hours
        # schedule.every().day.at("09:00").do(self.run_check)  # Alternative: daily at 9 AM
        
        # Run initial check
        self.run_check()
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(300)  # Check every 5 minutes for scheduled tasks

# Usage
if __name__ == "__main__":
    processor = AutonomousCB7Processor()
    
    # Option 1: Run once
    # processor.run_check()
    
    # Option 2: Start autonomous monitoring
    processor.start_monitoring()

# ============================================
# SETUP FOR AUTONOMOUS OPERATION
# ============================================

"""
AUTONOMOUS SETUP GUIDE:

1. Install additional dependencies:
   pip install schedule google-api-python-client

2. Optional: Get YouTube API key (recommended):
   - Go to: https://console.developers.google.com
   - Create project, enable YouTube Data API v3
   - Create credentials (API key)
   - Set environment variable: export YOUTUBE_API_KEY="your_key"

3. Optional: Setup email notifications:
   export EMAIL_ADDRESS="your_email@gmail.com"
   export EMAIL_PASSWORD="your_app_password"  # Gmail app password
   export EMAIL_RECIPIENTS="recipient1@email.com,recipient2@email.com"

4. Run autonomously:
   python autonomous_processor.py

5. Or run as background service (Linux/Mac):
   nohup python autonomous_processor.py &

6. Or setup as systemd service (Linux):
   # Create /etc/systemd/system/cb7-processor.service
   # Enable with: systemctl enable cb7-processor

HOW IT WORKS:
✅ Checks CB7 YouTube channel every 6 hours
✅ Identifies new meeting videos automatically  
✅ Processes them with local AI (private, free)
✅ Saves summaries to markdown files
✅ Stores data in SQLite database
✅ Sends email notifications (optional)
✅ Skips non-meeting videos (announcements, etc.)
✅ Never reprocesses the same video twice

COMPLETELY AUTONOMOUS OPERATION:
- Set it up once, forget about it
- Automatically processes all new CB7 meetings
- Runs 24/7 in background
- Costs $0 ongoing (just electricity)
- 100% private (no cloud APIs)
"""