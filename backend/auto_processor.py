"""
Autonomous CB Meeting Video Processor
Periodically checks for new videos and processes them
"""

import asyncio
import logging
import time
from datetime import datetime
import requests
from fetch_videos import CBChannelFetcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AutonomousProcessor:
    def __init__(self, api_base_url="http://localhost:8000"):
        self.api_base_url = api_base_url
        self.fetcher = CBChannelFetcher()
        
    def check_backend_health(self):
        """Check if the backend API is running"""
        try:
            response = requests.get(f"{self.api_base_url}/health")
            return response.ok
        except:
            return False
    
    async def fetch_new_videos(self, cb_key="cb7"):
        """Fetch new videos from YouTube for a specific CB"""
        logger.info(f"Fetching new videos for {cb_key}")
        try:
            response = requests.post(
                f"{self.api_base_url}/api/cb/{cb_key}/fetch-videos",
                params={"max_results": 20}
            )
            if response.ok:
                data = response.json()
                logger.info(f"Found {data['videos_found']} videos, {data['new_videos']} are new")
                return data['new_videos']
            else:
                logger.error(f"Failed to fetch videos: {response.text}")
                return 0
        except Exception as e:
            logger.error(f"Error fetching videos: {e}")
            return 0
    
    async def get_pending_videos(self, cb_number=None):
        """Get list of videos pending processing"""
        try:
            params = {"limit": 5}
            if cb_number:
                params["cb_number"] = cb_number
                
            response = requests.post(
                f"{self.api_base_url}/api/cb/process-pending",
                params=params
            )
            if response.ok:
                data = response.json()
                return data['processing']
            else:
                logger.error(f"Failed to get pending videos: {response.text}")
                return []
        except Exception as e:
            logger.error(f"Error getting pending videos: {e}")
            return []
    
    async def process_video(self, video_id):
        """Process a single video"""
        logger.info(f"Processing video: {video_id}")
        try:
            response = requests.post(
                f"{self.api_base_url}/api/cb/process-video/{video_id}"
            )
            if response.ok:
                data = response.json()
                logger.info(f"Successfully processed: {data['title']}")
                return True
            else:
                logger.error(f"Failed to process video {video_id}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error processing video {video_id}: {e}")
            return False
    
    async def process_cycle(self):
        """Run one processing cycle"""
        logger.info("Starting processing cycle")
        
        # 1. Fetch new videos from CB7 (you can expand this to other boards)
        new_videos = await self.fetch_new_videos("cb7")
        
        # 2. Get pending videos
        pending = await self.get_pending_videos(cb_number=7)
        
        if not pending:
            logger.info("No videos pending processing")
            return
        
        # 3. Process each video
        for video in pending:
            logger.info(f"Processing: {video['title']}")
            success = await self.process_video(video['video_id'])
            
            if success:
                logger.info(f"✓ Completed: {video['title']}")
            else:
                logger.error(f"✗ Failed: {video['title']}")
            
            # Wait between videos to avoid overloading
            await asyncio.sleep(30)
    
    async def run_autonomous(self, interval_minutes=60):
        """Run autonomous processing loop"""
        logger.info(f"Starting autonomous processor (checking every {interval_minutes} minutes)")
        
        while True:
            try:
                # Check backend health
                if not self.check_backend_health():
                    logger.error("Backend API is not available. Waiting...")
                    await asyncio.sleep(60)
                    continue
                
                # Run processing cycle
                await self.process_cycle()
                
                # Wait for next cycle
                logger.info(f"Cycle complete. Next check in {interval_minutes} minutes")
                await asyncio.sleep(interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("Shutting down autonomous processor")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(60)

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Autonomous CB Meeting Processor')
    parser.add_argument('--interval', type=int, default=60, 
                       help='Check interval in minutes (default: 60)')
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit')
    parser.add_argument('--api-url', default='http://localhost:8000',
                       help='Backend API URL')
    
    args = parser.parse_args()
    
    processor = AutonomousProcessor(args.api_url)
    
    if args.once:
        # Run single cycle
        await processor.process_cycle()
    else:
        # Run continuous loop
        await processor.run_autonomous(args.interval)

if __name__ == "__main__":
    asyncio.run(main())