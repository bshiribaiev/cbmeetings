from playwright.sync_api import sync_playwright
import json
import logging
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)

class BrowserHelper:
    @staticmethod
    def get_youtube_cookies_with_browser():
        """Use a real browser to get YouTube cookies"""
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US'
            )
            
            # Add stealth scripts
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = context.new_page()
            
            # Visit YouTube
            page.goto('https://www.youtube.com', wait_until='networkidle')
            page.wait_for_timeout(3000)
            
            # Get cookies
            cookies = context.cookies()
            
            # Convert to Netscape format
            cookie_lines = ["# Netscape HTTP Cookie File\n"]
            for cookie in cookies:
                cookie_line = f"{cookie['domain']}\tTRUE\t{cookie['path']}\t"
                cookie_line += f"{'TRUE' if cookie.get('secure') else 'FALSE'}\t"
                cookie_line += f"{int(cookie.get('expires', 0))}\t"
                cookie_line += f"{cookie['name']}\t{cookie['value']}\n"
                cookie_lines.append(cookie_line)
            
            browser.close()
            
            return ''.join(cookie_lines)
    
    @staticmethod
    def download_with_browser(url: str, output_path: str):
        """Download using browser automation as fallback"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Set to True in production
            page = browser.new_page()
            
            # Go to a YouTube downloader service
            page.goto('https://ytdl-web.app')
            page.fill('input[name="url"]', url)
            page.click('button[type="submit"]')
            
            # Wait for download link
            page.wait_for_selector('a[download]', timeout=30000)
            
            # Get download URL
            download_url = page.get_attribute('a[download]', 'href')
            
            browser.close()
            
            # Download the file
            import requests
            response = requests.get(download_url)
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            return output_path