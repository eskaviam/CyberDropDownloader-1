from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionFailure
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext, log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class PixelDrainBypassCrawler(Crawler):
    def __init__(self, manager: Manager):
        super().__init__(manager, "pd.cybar.xyz", "PixelDrain Bypass")
        self.request_limiter = AsyncLimiter(15, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Process the bypassed pixeldrain URL"""
        task_id = await self.scraping_progress.add_task(scrape_item.url)
        
        # Extract the file ID from the URL
        file_id = scrape_item.url.parts[-1]
        
        # Log the process
        await log(f"Processing bypassed pixeldrain URL: {scrape_item.url}", 10)
        
        # First, get the headers to extract the filename from Content-Disposition
        async with self.request_limiter:
            # Follow redirects to get the actual CDN URL
            cdn_url = await self.client.get_redirect(self.domain, scrape_item.url)
            
            # Get the response headers
            response = await self.client.get_response(self.domain, cdn_url)
            
            # Extract filename from Content-Disposition header
            content_disposition = response.headers.get('Content-Disposition', '')
            filename = None
            
            # Try to extract filename using regex pattern
            if 'filename=' in content_disposition:
                # Match filename="something.ext" or filename=something.ext
                match = re.search(r'filename=(?:"([^"]+)"|([^;]+))', content_disposition)
                if match:
                    # Get the matched group (either quoted or unquoted)
                    filename = match.group(1) if match.group(1) else match.group(2)
                    await log(f"Extracted filename from Content-Disposition: {filename}", 10)
            
            # If no filename found in headers, use the file ID
            if not filename:
                # Try to determine extension from Content-Type
                content_type = response.headers.get('Content-Type', '')
                ext = "bin"  # Default extension
                
                if '/' in content_type:
                    mime_type = content_type.split('/')[1].split(';')[0].strip()
                    if mime_type:
                        ext = mime_type
                        
                filename = f"{file_id}.{ext}"
                await log(f"Using generated filename: {filename}", 10)
            
            # Extract filename and extension
            try:
                filename_clean, ext = await get_filename_and_ext(filename)
            except NoExtensionFailure:
                # If we still can't determine the extension, use the file ID with a generic extension
                filename_clean = file_id
                ext = "bin"
                await log(f"No extension found, using default: {filename_clean}.{ext}", 10)
        
        # Get current timestamp for the file date
        current_time = datetime.datetime.now()
        timestamp = calendar.timegm(current_time.timetuple())
        
        # Create a new scrape item for the download
        new_scrape_item = await self.create_scrape_item(scrape_item, cdn_url, "", False, None, timestamp)
        
        # Handle the file download with the extracted filename
        await self.handle_file(cdn_url, new_scrape_item, filename_clean, ext)
        
        await self.scraping_progress.remove_task(task_id) 